"""Integration coverage for BE-015 durable dispatcher, lease, retry, and deduplication."""

from __future__ import annotations

from collections.abc import Iterator
import os
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, make_url

from openlibrary.infrastructure.sqlserver.migrate import (
    bootstrap_database_identities,
    connect,
    database_url_for,
    run_migrations,
)
from openlibrary.modules.core.infrastructure.organizations import set_tenant_context
from openlibrary.modules.core.infrastructure.tenancy import SqlServerTenantContext


class SqlServerUrls(dict[str, str]):
    """Credential-bearing integration settings with a safe pytest representation."""

    def __repr__(self) -> str:
        return "SqlServerUrls(redacted)"


@pytest.fixture(scope="module")
def database_urls() -> SqlServerUrls:
    """Return SQL Server URLs supplied by the integration environment or local instance."""
    required_names = (
        "DATABASE_BOOTSTRAP_URL",
        "DATABASE_MIGRATION_URL",
        "DATABASE_RUNTIME_URL",
    )
    missing = [name for name in required_names if not os.environ.get(name, "").strip()]
    if missing:
        pytest.skip(f"SQL Server integration requires: {', '.join(missing)}")
    return SqlServerUrls({name: os.environ[name] for name in required_names})


@pytest.fixture(scope="module")
def clean_database_urls(database_urls: SqlServerUrls) -> Iterator[SqlServerUrls]:
    """Create one isolated database and least-privilege identities for this module."""
    database_name = f"openlibrary_be015_{uuid4().hex}"
    bootstrap_url = database_urls["DATABASE_BOOTSTRAP_URL"]

    with connect(bootstrap_url, database="master") as connection:
        connection.execute(f"CREATE DATABASE [{database_name}]")

    urls = SqlServerUrls(
        {
            name: database_url_for(url, database_name)
            for name, url in database_urls.items()
        }
    )
    migration_login = f"be015_migrator_{uuid4().hex}"
    runtime_login = f"be015_runtime_{uuid4().hex}"
    urls["DATABASE_MIGRATION_URL"] = (
        make_url(urls["DATABASE_MIGRATION_URL"])
        .set(username=migration_login)
        .render_as_string(hide_password=False)
    )
    urls["DATABASE_RUNTIME_URL"] = (
        make_url(urls["DATABASE_RUNTIME_URL"])
        .set(username=runtime_login)
        .render_as_string(hide_password=False)
    )
    try:
        yield urls
    finally:
        with connect(bootstrap_url, database="master") as connection:
            connection.execute(
                "ALTER DATABASE "
                f"[{database_name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE"
            )
            connection.execute(f"DROP DATABASE [{database_name}]")
            connection.execute(f"DROP LOGIN [{runtime_login}]")
            connection.execute(f"DROP LOGIN [{migration_login}]")


@pytest.fixture(scope="module")
def seeded_database_urls(clean_database_urls: SqlServerUrls) -> SqlServerUrls:
    """Migrate an isolated database and seed two distinct organizations."""
    identities = bootstrap_database_identities(
        bootstrap_url=clean_database_urls["DATABASE_BOOTSTRAP_URL"],
        migration_url=clean_database_urls["DATABASE_MIGRATION_URL"],
        runtime_url=clean_database_urls["DATABASE_RUNTIME_URL"],
    )
    run_migrations(
        clean_database_urls["DATABASE_MIGRATION_URL"],
        runtime_login=identities.runtime_login,
    )
    organization_a = uuid4()
    organization_b = uuid4()
    with connect(clean_database_urls["DATABASE_BOOTSTRAP_URL"]) as connection:
        connection.execute(
            "INSERT INTO core.organizations "
            "(organization_id, name, slug, organization_type, status, timezone, settings_json) "
            "VALUES "
            f"('{organization_a}', N'Campus Alpha', 'campus-alpha', 'education', 'active', 'UTC', N'{{}}'), "
            f"('{organization_b}', N'Campus Beta', 'campus-beta', 'education', 'active', 'UTC', N'{{}}')"
        )
    clean_database_urls["ORGANIZATION_A"] = str(organization_a)
    clean_database_urls["ORGANIZATION_B"] = str(organization_b)
    return clean_database_urls


def _insert_outbox_event(
    runtime_url: str,
    organization_id: UUID,
    event_type: str = "book.reserved",
    aggregate_type: str = "reservation",
    aggregate_id: UUID | None = None,
    payload_version: int = 1,
    payload: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> UUID:
    """Insert one durable outbox event inside tenant context."""
    from openlibrary.modules.ops.application.persistence import (
        AuditEvent,
        OutboxEvent,
    )
    from openlibrary.modules.ops.infrastructure.sqlserver import (
        SqlServerAuditedTransaction,
    )

    event_id = uuid4()
    agg_id = aggregate_id or uuid4()
    key = idempotency_key or f"key-{event_id.hex}"
    event_payload = payload if payload is not None else {"book_id": str(uuid4())}

    engine = create_engine(runtime_url)
    with engine.connect() as connection:
        set_tenant_context(connection, organization_id)
        connection.commit()
        writer = SqlServerAuditedTransaction()
        writer.run(
            connection,
            mutation=lambda conn: None,
            audit_event=AuditEvent(
                action=f"{event_type}.created",
                entity_type=aggregate_type,
                entity_id=agg_id,
                payload=event_payload,
                correlation_id=uuid4(),
            ),
            outbox_events=[
                OutboxEvent(
                    event_type=event_type,
                    aggregate_type=aggregate_type,
                    aggregate_id=agg_id,
                    payload_version=payload_version,
                    payload=event_payload,
                    correlation_id=uuid4(),
                    idempotency_key=key,
                    event_id=event_id,
                )
            ],
        )
        connection.commit()
    engine.dispose()
    return event_id


def test_dispatcher_classes_exist() -> None:
    """The dispatcher, claim store, and consumer deduplication ports must be importable."""
    from openlibrary.modules.ops.application.dispatcher import (
        ConsumerDeduplicationPort,
        OutboxClaimStore,
        OutboxDispatcherService,
    )
    from openlibrary.modules.ops.infrastructure.dispatcher import (
        SqlServerConsumerDeduplicationStore,
        SqlServerOutboxClaimStore,
    )

    assert OutboxDispatcherService is not None
    assert OutboxClaimStore is not None
    assert ConsumerDeduplicationPort is not None
    assert SqlServerOutboxClaimStore is not None
    assert SqlServerConsumerDeduplicationStore is not None


def test_dispatcher_single_claim_and_delivery(
    seeded_database_urls: SqlServerUrls,
) -> None:
    """Atomically claim one event with a lease and server-derived organization context."""
    from openlibrary.modules.ops.application.dispatcher import OutboxDispatcherService
    from openlibrary.modules.ops.application.persistence import ClaimedOutboxEvent
    from openlibrary.modules.ops.infrastructure.dispatcher import (
        SqlServerConsumerDeduplicationStore,
        SqlServerOutboxClaimStore,
    )

    org_id = UUID(seeded_database_urls["ORGANIZATION_A"])
    event_id = _insert_outbox_event(
        seeded_database_urls["DATABASE_RUNTIME_URL"],
        organization_id=org_id,
        event_type="test.single_claim",
    )

    claim_store = SqlServerOutboxClaimStore(
        seeded_database_urls["DATABASE_RUNTIME_URL"]
    )
    dedup_store = SqlServerConsumerDeduplicationStore()
    tenant_context = SqlServerTenantContext(
        seeded_database_urls["DATABASE_RUNTIME_URL"]
    )

    received_events: list[ClaimedOutboxEvent] = []
    received_tenants: list[UUID] = []

    def handler(conn: Connection, event: ClaimedOutboxEvent) -> None:
        tenant_in_db = conn.execute(
            text("SELECT CAST(SESSION_CONTEXT(N'organization_id') AS uniqueidentifier)")
        ).scalar()
        received_tenants.append(UUID(str(tenant_in_db)))
        received_events.append(event)

    dispatcher = OutboxDispatcherService(
        claim_store=claim_store,
        deduplication_port=dedup_store,
        tenant_context=tenant_context,
        lease_duration_seconds=30,
    )
    dispatcher.register_handler("test.single_claim", handler, max_payload_version=1)

    dispatched = dispatcher.dispatch_one()
    assert dispatched is True
    assert len(received_events) == 1
    assert received_events[0].event_id == event_id
    assert received_events[0].organization_id == org_id
    assert received_tenants == [org_id]

    # Verify event is delivered in database
    engine = create_engine(seeded_database_urls["DATABASE_RUNTIME_URL"])
    with engine.connect() as conn:
        set_tenant_context(conn, org_id)
        row = conn.execute(
            text(
                "SELECT delivered_at, lease_token, attempts "
                "FROM ops.outbox_events WHERE event_id = :event_id"
            ),
            {"event_id": str(event_id)},
        ).fetchone()
        assert row is not None
        assert row.delivered_at is not None
        assert row.lease_token is None
        assert row.attempts == 1

        # Verify job record is created and completed
        job_row = conn.execute(
            text(
                "SELECT status, attempts, payload_version "
                "FROM ops.job_records WHERE outbox_event_id = :event_id"
            ),
            {"event_id": str(event_id)},
        ).fetchone()
        assert job_row is not None
        assert job_row.status == "completed"
        assert job_row.attempts == 1
    engine.dispose()


def test_worker_crash_after_claim_does_not_lose_event(
    seeded_database_urls: SqlServerUrls,
) -> None:
    """A worker crash after claim does not lose an event; lease expiry enables reclamation."""
    from openlibrary.modules.ops.application.dispatcher import OutboxDispatcherService
    from openlibrary.modules.ops.application.persistence import ClaimedOutboxEvent
    from openlibrary.modules.ops.infrastructure.dispatcher import (
        SqlServerConsumerDeduplicationStore,
        SqlServerOutboxClaimStore,
    )

    org_id = UUID(seeded_database_urls["ORGANIZATION_B"])
    event_id = _insert_outbox_event(
        seeded_database_urls["DATABASE_RUNTIME_URL"],
        organization_id=org_id,
        event_type="test.crash_reclaim",
    )

    claim_store = SqlServerOutboxClaimStore(
        seeded_database_urls["DATABASE_RUNTIME_URL"]
    )
    dedup_store = SqlServerConsumerDeduplicationStore()
    tenant_context = SqlServerTenantContext(
        seeded_database_urls["DATABASE_RUNTIME_URL"]
    )

    # Worker 1 claims event with lease duration of 1 second then "crashes" (does not deliver)
    worker_1_token = uuid4()
    claimed = claim_store.claim_next_event(
        lease_token=worker_1_token,
        lease_duration_seconds=1,
    )
    assert claimed is not None
    assert claimed.event_id == event_id
    assert claimed.attempts == 1

    # While lease is active, another worker cannot claim it
    worker_2_token = uuid4()
    active_claim = claim_store.claim_next_event(
        lease_token=worker_2_token,
        lease_duration_seconds=30,
    )
    # Since only one event exists and its lease is active, None is returned
    assert active_claim is None

    # Wait or expire the lease manually in database to simulate lease timeout
    engine = create_engine(seeded_database_urls["DATABASE_RUNTIME_URL"])
    with engine.connect() as conn:
        set_tenant_context(conn, org_id)
        conn.execute(
            text(
                "UPDATE ops.outbox_events "
                "SET lease_expires_at = DATEADD(second, -5, SYSUTCDATETIME()) "
                "WHERE event_id = :event_id"
            ),
            {"event_id": str(event_id)},
        )
        conn.commit()
    engine.dispose()

    # Now Worker 2 reclaims the expired event
    reclaimed_events: list[ClaimedOutboxEvent] = []

    def handler(conn: Connection, event: ClaimedOutboxEvent) -> None:
        reclaimed_events.append(event)

    dispatcher_2 = OutboxDispatcherService(
        claim_store=claim_store,
        deduplication_port=dedup_store,
        tenant_context=tenant_context,
        lease_duration_seconds=30,
    )
    dispatcher_2.register_handler("test.crash_reclaim", handler, max_payload_version=1)

    dispatched = dispatcher_2.dispatch_one()
    assert dispatched is True
    assert len(reclaimed_events) == 1
    assert reclaimed_events[0].event_id == event_id
    assert reclaimed_events[0].attempts == 2

    # Verify event is delivered and not lost
    engine = create_engine(seeded_database_urls["DATABASE_RUNTIME_URL"])
    with engine.connect() as conn:
        set_tenant_context(conn, org_id)
        row = conn.execute(
            text(
                "SELECT delivered_at, attempts "
                "FROM ops.outbox_events WHERE event_id = :event_id"
            ),
            {"event_id": str(event_id)},
        ).fetchone()
        assert row is not None
        assert row.delivered_at is not None
        assert row.attempts == 2
    engine.dispose()


def test_bounded_retry_and_dead_letter_visibility(
    seeded_database_urls: SqlServerUrls,
) -> None:
    """Retries are bounded and exhausted events are visible in a dead-letter state."""
    from openlibrary.modules.ops.application.dispatcher import OutboxDispatcherService
    from openlibrary.modules.ops.application.persistence import ClaimedOutboxEvent
    from openlibrary.modules.ops.infrastructure.dispatcher import (
        SqlServerConsumerDeduplicationStore,
        SqlServerOutboxClaimStore,
    )

    org_id = UUID(seeded_database_urls["ORGANIZATION_A"])
    event_id = _insert_outbox_event(
        seeded_database_urls["DATABASE_RUNTIME_URL"],
        organization_id=org_id,
        event_type="test.failing_event",
    )

    claim_store = SqlServerOutboxClaimStore(
        seeded_database_urls["DATABASE_RUNTIME_URL"]
    )
    dedup_store = SqlServerConsumerDeduplicationStore()
    tenant_context = SqlServerTenantContext(
        seeded_database_urls["DATABASE_RUNTIME_URL"]
    )

    fail_count = 0

    def failing_handler(conn: Connection, event: ClaimedOutboxEvent) -> None:
        nonlocal fail_count
        fail_count += 1
        raise RuntimeError("Transient provider outage")

    dispatcher = OutboxDispatcherService(
        claim_store=claim_store,
        deduplication_port=dedup_store,
        tenant_context=tenant_context,
        lease_duration_seconds=30,
        max_retries=3,
        base_backoff_seconds=0,  # 0 delay for immediate test retry
    )
    dispatcher.register_handler(
        "test.failing_event", failing_handler, max_payload_version=1
    )

    # Attempt 1: fails, scheduled for retry
    assert dispatcher.dispatch_one() is True
    assert fail_count == 1

    # Attempt 2: fails, scheduled for retry
    assert dispatcher.dispatch_one() is True
    assert fail_count == 2

    # Attempt 3: fails, exceeds max_retries -> dead-letter
    assert dispatcher.dispatch_one() is True
    assert fail_count == 3

    # Attempt 4: no available events to claim because it is dead-lettered
    assert dispatcher.dispatch_one() is False

    # Check dead-letter visibility in DB
    engine = create_engine(seeded_database_urls["DATABASE_RUNTIME_URL"])
    with engine.connect() as conn:
        set_tenant_context(conn, org_id)
        row = conn.execute(
            text(
                "SELECT delivered_at, dead_lettered_at, attempts, last_error "
                "FROM ops.outbox_events WHERE event_id = :event_id"
            ),
            {"event_id": str(event_id)},
        ).fetchone()
        assert row is not None
        assert row.delivered_at is None
        assert row.dead_lettered_at is not None
        assert row.attempts == 3
        assert "Transient provider outage" in str(row.last_error)

        job_row = conn.execute(
            text(
                "SELECT status, attempts, last_error "
                "FROM ops.job_records WHERE outbox_event_id = :event_id"
            ),
            {"event_id": str(event_id)},
        ).fetchone()
        assert job_row is not None
        assert job_row.status == "dead_letter"
        assert job_row.attempts == 3
    engine.dispose()


def test_replayed_delivery_does_not_execute_consumer_side_effect_twice(
    seeded_database_urls: SqlServerUrls,
) -> None:
    """Replayed delivery does not execute a consumer side effect twice (consumer deduplication)."""
    from openlibrary.modules.ops.application.dispatcher import (
        OutboxDispatcherService,
    )
    from openlibrary.modules.ops.application.persistence import ClaimedOutboxEvent
    from openlibrary.modules.ops.infrastructure.dispatcher import (
        SqlServerConsumerDeduplicationStore,
        SqlServerOutboxClaimStore,
    )

    org_id = UUID(seeded_database_urls["ORGANIZATION_B"])
    event_id = _insert_outbox_event(
        seeded_database_urls["DATABASE_RUNTIME_URL"],
        organization_id=org_id,
        event_type="test.idempotent_consumer",
    )

    claim_store = SqlServerOutboxClaimStore(
        seeded_database_urls["DATABASE_RUNTIME_URL"]
    )
    dedup_store = SqlServerConsumerDeduplicationStore()
    tenant_context = SqlServerTenantContext(
        seeded_database_urls["DATABASE_RUNTIME_URL"]
    )

    side_effect_count = 0

    def idempotent_consumer(conn: Connection, event: ClaimedOutboxEvent) -> None:
        nonlocal side_effect_count
        job_type = "send_email_notification"
        # Consumer checks deduplication before side effect
        if dedup_store.is_processed(
            conn,
            organization_id=event.organization_id,
            outbox_event_id=event.event_id,
            job_type=job_type,
        ):
            return

        # Execute side effect
        side_effect_count += 1

        # Record consumer completion in the same tenant transaction
        dedup_store.record_processed(
            conn,
            organization_id=event.organization_id,
            outbox_event_id=event.event_id,
            job_type=job_type,
            payload_version=event.payload_version,
        )

    dispatcher = OutboxDispatcherService(
        claim_store=claim_store,
        deduplication_port=dedup_store,
        tenant_context=tenant_context,
        lease_duration_seconds=30,
    )
    dispatcher.register_handler(
        "test.idempotent_consumer", idempotent_consumer, max_payload_version=1
    )

    # First delivery
    assert dispatcher.dispatch_one() is True
    assert side_effect_count == 1

    # Simulate replay: clear delivered_at so event becomes available again
    engine = create_engine(seeded_database_urls["DATABASE_RUNTIME_URL"])
    with engine.connect() as conn:
        set_tenant_context(conn, org_id)
        conn.execute(
            text(
                "UPDATE ops.outbox_events "
                "SET delivered_at = NULL, lease_token = NULL, lease_expires_at = NULL, "
                "available_at = SYSUTCDATETIME() "
                "WHERE event_id = :event_id"
            ),
            {"event_id": str(event_id)},
        )
        conn.commit()
    engine.dispose()

    # Second delivery (replay)
    assert dispatcher.dispatch_one() is True
    # Crucial assertion: Side effect count is STILL 1!
    assert side_effect_count == 1


def test_unsupported_payload_version_dead_letters(
    seeded_database_urls: SqlServerUrls,
) -> None:
    """Event with payload version exceeding supported max is immediately dead-lettered."""
    from openlibrary.modules.ops.application.dispatcher import OutboxDispatcherService
    from openlibrary.modules.ops.application.persistence import ClaimedOutboxEvent
    from openlibrary.modules.ops.infrastructure.dispatcher import (
        SqlServerConsumerDeduplicationStore,
        SqlServerOutboxClaimStore,
    )

    org_id = UUID(seeded_database_urls["ORGANIZATION_A"])
    event_id = _insert_outbox_event(
        seeded_database_urls["DATABASE_RUNTIME_URL"],
        organization_id=org_id,
        event_type="test.v2_event",
        payload_version=2,
    )

    claim_store = SqlServerOutboxClaimStore(
        seeded_database_urls["DATABASE_RUNTIME_URL"]
    )
    dedup_store = SqlServerConsumerDeduplicationStore()
    tenant_context = SqlServerTenantContext(
        seeded_database_urls["DATABASE_RUNTIME_URL"]
    )

    executed = False

    def v1_consumer(conn: Connection, event: ClaimedOutboxEvent) -> None:
        nonlocal executed
        executed = True

    dispatcher = OutboxDispatcherService(
        claim_store=claim_store,
        deduplication_port=dedup_store,
        tenant_context=tenant_context,
        lease_duration_seconds=30,
    )
    # Register handler only supporting v1
    dispatcher.register_handler("test.v2_event", v1_consumer, max_payload_version=1)

    assert dispatcher.dispatch_one() is True
    assert not executed

    # Check dead-letter in DB
    engine = create_engine(seeded_database_urls["DATABASE_RUNTIME_URL"])
    with engine.connect() as conn:
        set_tenant_context(conn, org_id)
        row = conn.execute(
            text(
                "SELECT dead_lettered_at, last_error "
                "FROM ops.outbox_events WHERE event_id = :event_id"
            ),
            {"event_id": str(event_id)},
        ).fetchone()
        assert row is not None
        assert row.dead_lettered_at is not None
        assert "Unsupported payload version" in str(row.last_error)
    engine.dispose()


def test_tenant_isolation_in_consumer(
    seeded_database_urls: SqlServerUrls,
) -> None:
    """Consumer execution runs strictly within server-derived tenant boundary under RLS."""
    from openlibrary.modules.ops.application.dispatcher import OutboxDispatcherService
    from openlibrary.modules.ops.application.persistence import ClaimedOutboxEvent
    from openlibrary.modules.ops.infrastructure.dispatcher import (
        SqlServerConsumerDeduplicationStore,
        SqlServerOutboxClaimStore,
    )

    org_a = UUID(seeded_database_urls["ORGANIZATION_A"])
    org_b = UUID(seeded_database_urls["ORGANIZATION_B"])

    _insert_outbox_event(
        seeded_database_urls["DATABASE_RUNTIME_URL"],
        organization_id=org_a,
        event_type="test.tenant_boundary",
    )

    claim_store = SqlServerOutboxClaimStore(
        seeded_database_urls["DATABASE_RUNTIME_URL"]
    )
    dedup_store = SqlServerConsumerDeduplicationStore()
    tenant_context = SqlServerTenantContext(
        seeded_database_urls["DATABASE_RUNTIME_URL"]
    )

    cross_tenant_rows: list[Any] = []

    def consumer_attempting_cross_tenant(
        conn: Connection, event: ClaimedOutboxEvent
    ) -> None:
        # In tenant A context, attempts to select tenant B outbox events should return nothing
        rows = conn.execute(
            text(
                "SELECT event_id FROM ops.outbox_events WHERE organization_id = :org_b"
            ),
            {"org_b": str(org_b)},
        ).fetchall()
        cross_tenant_rows.extend(rows)

    dispatcher = OutboxDispatcherService(
        claim_store=claim_store,
        deduplication_port=dedup_store,
        tenant_context=tenant_context,
        lease_duration_seconds=30,
    )
    dispatcher.register_handler(
        "test.tenant_boundary", consumer_attempting_cross_tenant, max_payload_version=1
    )

    assert dispatcher.dispatch_one() is True
    # RLS must completely filter out Tenant B rows
    assert cross_tenant_rows == []
