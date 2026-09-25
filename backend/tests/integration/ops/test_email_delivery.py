"""Integration coverage for BE-026: Email delivery consumer, bounded retry, and worker observability."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
import json
import os
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from openlibrary.infrastructure.sqlserver.migrate import (
    bootstrap_database_identities,
    connect,
    database_url_for,
    run_migrations,
)
from openlibrary.modules.core.infrastructure.tenancy import SqlServerTenantContext
from openlibrary.modules.ops.application.dispatcher import (
    OutboxDispatcherService,
)
from openlibrary.modules.ops.application.email import (
    DevelopmentEmailSink,
    EmailDeliveryError,
    EmailDeliveryResult,
    EmailMessage,
    EmailPort,
)
from openlibrary.modules.ops.application.email_consumer import (
    EmailDeliveryConsumer,
    SUPPORTED_EMAIL_EVENT_TYPES,
    register_email_consumers,
)
from openlibrary.modules.ops.application.metrics import (
    FailedJobDetail,
    QueueMetrics,
    QueueMetricsStore,
)
from openlibrary.modules.ops.application.persistence import ClaimedOutboxEvent
from openlibrary.modules.ops.application.worker_lifecycle import (
    WorkerGracefulShutdown,
    WorkerHealthService,
    WorkerHealthStatus,
    WorkerReconnectPolicy,
)
from openlibrary.modules.ops.infrastructure.dispatcher import (
    SqlServerConsumerDeduplicationStore,
    SqlServerOutboxClaimStore,
)
from openlibrary.modules.ops.infrastructure.metrics import (
    SqlServerQueueMetricsStore,
)


class SqlServerUrls(dict[str, str]):
    """Credential-bearing integration settings with a safe pytest representation."""

    def __repr__(self) -> str:
        return "SqlServerUrls(redacted)"


@pytest.fixture(scope="module")
def database_urls() -> SqlServerUrls:
    """Return SQL Server URLs supplied only by the dedicated integration environment."""
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
def seeded_database_urls(database_urls: SqlServerUrls) -> Iterator[SqlServerUrls]:
    """Create disposable database, run migrations, and seed tenants/users."""
    database_name = f"openlibrary_be026_{uuid4().hex}"
    bootstrap_url = database_urls["DATABASE_BOOTSTRAP_URL"]
    with connect(bootstrap_url, database="master") as connection:
        connection.execute(f"CREATE DATABASE [{database_name}]")

    urls = SqlServerUrls(
        {
            name: database_url_for(url, database_name)
            for name, url in database_urls.items()
        }
    )
    migration_login = f"be026_migrator_{uuid4().hex}"
    runtime_login = f"be026_runtime_{uuid4().hex}"
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

    identities = bootstrap_database_identities(
        bootstrap_url=urls["DATABASE_BOOTSTRAP_URL"],
        migration_url=urls["DATABASE_MIGRATION_URL"],
        runtime_url=urls["DATABASE_RUNTIME_URL"],
    )
    run_migrations(
        urls["DATABASE_MIGRATION_URL"],
        runtime_login=identities.runtime_login,
    )

    org_a = uuid4()
    org_b = uuid4()
    user_a1 = uuid4()
    user_b1 = uuid4()

    with connect(urls["DATABASE_BOOTSTRAP_URL"]) as connection:
        connection.execute(
            "INSERT INTO core.organizations "
            "(organization_id, name, slug, organization_type, status, timezone, settings_json) "
            f"VALUES ('{org_a}', N'Alpha Library', 'alpha-library', 'education', 'active', 'UTC', N'{{}}'), "
            f"('{org_b}', N'Beta Library', 'beta-library', 'education', 'active', 'UTC', N'{{}}')"
        )
        connection.execute(
            "INSERT INTO core.users (user_id, organization_id, email, password_hash, status) "
            f"VALUES ('{user_a1}', '{org_a}', 'alice@alpha.example', 'hash1', 'active'), "
            f"('{user_b1}', '{org_b}', 'bob@beta.example', 'hash2', 'active')"
        )

    urls["ORG_A_ID"] = str(org_a)
    urls["ORG_B_ID"] = str(org_b)
    urls["USER_A1_ID"] = str(user_a1)
    urls["USER_B1_ID"] = str(user_b1)

    try:
        yield urls
    finally:
        with connect(bootstrap_url, database="master") as connection:
            connection.execute(
                f"ALTER DATABASE [{database_name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE"
            )
            connection.execute(f"DROP DATABASE [{database_name}]")
            connection.execute(f"DROP LOGIN [{runtime_login}]")
            connection.execute(f"DROP LOGIN [{migration_login}]")


def _create_claimed_event(
    *,
    organization_id: UUID,
    event_type: str,
    payload: dict[str, Any],
    event_id: UUID | None = None,
    aggregate_id: UUID | None = None,
    aggregate_type: str = "loan",
    payload_version: int = 1,
    attempts: int = 1,
) -> ClaimedOutboxEvent:
    ev_id = event_id or uuid4()
    agg_id = aggregate_id or uuid4()
    now = datetime.now(timezone.utc)
    return ClaimedOutboxEvent(
        event_id=ev_id,
        organization_id=organization_id,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=agg_id,
        payload_version=payload_version,
        payload_json=json.dumps(payload),
        correlation_id=uuid4(),
        idempotency_key=f"idemp-{ev_id}",
        attempts=attempts,
        lease_token=uuid4(),
        lease_expires_at=now,
        created_at=now,
    )


def _persist_outbox_event(connection: Any, event: ClaimedOutboxEvent) -> None:
    connection.execute(
        text(
            "INSERT INTO ops.outbox_events ("
            "  event_id, organization_id, event_type, aggregate_type, aggregate_id, "
            "  payload_version, payload_json, correlation_id, idempotency_key, "
            "  attempts, created_at, available_at, delivered_at"
            ") VALUES ("
            "  :event_id, :org_id, :event_type, :aggregate_type, :aggregate_id, "
            "  :payload_version, :payload_json, :corr_id, :idemp_key, 1, SYSUTCDATETIME(), SYSUTCDATETIME(), SYSUTCDATETIME()"
            ")"
        ),
        {
            "event_id": str(event.event_id),
            "org_id": str(event.organization_id),
            "event_type": event.event_type,
            "aggregate_type": event.aggregate_type,
            "aggregate_id": str(event.aggregate_id),
            "payload_version": event.payload_version,
            "payload_json": event.payload_json,
            "corr_id": str(event.correlation_id),
            "idemp_key": event.idempotency_key,
        },
    )


def test_email_delivery_classes_exist() -> None:
    """Verify all BE-026 contract components exist and are importable."""
    assert EmailMessage is not None
    assert EmailDeliveryResult is not None
    assert EmailPort is not None
    assert EmailDeliveryError is not None
    assert DevelopmentEmailSink is not None
    assert EmailDeliveryConsumer is not None
    assert register_email_consumers is not None
    assert SUPPORTED_EMAIL_EVENT_TYPES is not None
    assert QueueMetrics is not None
    assert FailedJobDetail is not None
    assert QueueMetricsStore is not None
    assert SqlServerQueueMetricsStore is not None
    assert WorkerHealthStatus is not None
    assert WorkerHealthService is not None
    assert WorkerGracefulShutdown is not None
    assert WorkerReconnectPolicy is not None


def test_development_email_sink_deterministic_delivery() -> None:
    """Development sink records delivered emails in memory deterministically."""
    sink = DevelopmentEmailSink()
    assert len(sink.get_deliveries()) == 0

    message = EmailMessage(
        to_address="reader@example.com",
        subject="Loan Approved",
        body_text="Your loan for 'Design Patterns' has been approved.",
        organization_id=uuid4(),
        event_id=uuid4(),
    )

    result = sink.send(message)
    assert result.success is True
    assert result.message_id is not None
    assert result.error_message is None
    assert len(sink.get_deliveries()) == 1
    assert sink.get_deliveries()[0].to_address == "reader@example.com"
    assert len(sink.get_deliveries_for("reader@example.com")) == 1
    assert len(sink.get_deliveries_for("other@example.com")) == 0

    sink.clear()
    assert len(sink.get_deliveries()) == 0


def test_development_email_sink_configurable_failure() -> None:
    """Development sink can be configured to simulate transient provider failure."""
    sink = DevelopmentEmailSink()
    sink.simulate_failure(count=1, error=EmailDeliveryError("SMTP connection timeout"))

    message = EmailMessage(
        to_address="reader@example.com",
        subject="Overdue Notice",
        body_text="Your book is overdue.",
    )

    with pytest.raises(EmailDeliveryError, match="SMTP connection timeout"):
        sink.send(message)

    # Subsequent send succeeds after failure count exhausted
    result = sink.send(message)
    assert result.success is True
    assert len(sink.get_deliveries()) == 1


def test_email_consumer_handles_events_and_sends_email(
    seeded_database_urls: SqlServerUrls,
) -> None:
    """Email consumer resolves user email and delivers message via email adapter."""
    org_id = UUID(seeded_database_urls["ORG_A_ID"])
    user_id = UUID(seeded_database_urls["USER_A1_ID"])
    tenant_context = SqlServerTenantContext(
        seeded_database_urls["DATABASE_RUNTIME_URL"]
    )
    sink = DevelopmentEmailSink()
    dedup = SqlServerConsumerDeduplicationStore()
    consumer = EmailDeliveryConsumer(email_port=sink, deduplication_port=dedup)

    event = _create_claimed_event(
        organization_id=org_id,
        event_type="circulation.loan_approved",
        payload={
            "loan_id": str(uuid4()),
            "organization_id": str(org_id),
            "copy_id": str(uuid4()),
            "borrower_user_id": str(user_id),
            "book_title": "Domain-Driven Design",
        },
    )

    with tenant_context.connection(org_id) as connection:
        _persist_outbox_event(connection, event)
        consumer.handle_event(connection, event)
        connection.commit()

    assert len(sink.get_deliveries()) == 1
    delivered = sink.get_deliveries()[0]
    assert delivered.to_address == "alice@alpha.example"
    assert "Loan Approved" in delivered.subject
    assert "Domain-Driven Design" in delivered.body_text


def test_provider_failure_does_not_rollback_originating_loan_or_payment_transaction(
    seeded_database_urls: SqlServerUrls,
) -> None:
    """A provider failure during email dispatch does NOT roll back originating transaction."""
    org_id = UUID(seeded_database_urls["ORG_A_ID"])
    user_id = UUID(seeded_database_urls["USER_A1_ID"])
    tenant_context = SqlServerTenantContext(
        seeded_database_urls["DATABASE_RUNTIME_URL"]
    )
    claim_store = SqlServerOutboxClaimStore(
        seeded_database_urls["DATABASE_RUNTIME_URL"]
    )
    dedup = SqlServerConsumerDeduplicationStore()

    # 1. Simulate originating transaction that creates a loan and writes outbox event
    loan_id = uuid4()
    event_id = uuid4()
    with tenant_context.connection(org_id) as connection:
        # Originating mutation committed
        connection.execute(
            text(
                "INSERT INTO ops.outbox_events ("
                "  event_id, organization_id, event_type, aggregate_type, aggregate_id, "
                "  payload_version, payload_json, correlation_id, idempotency_key, "
                "  attempts, created_at, available_at"
                ") VALUES ("
                "  :event_id, :org_id, 'circulation.loan_checked_out', 'loan', :loan_id, "
                "  1, :payload_json, :corr_id, :idemp_key, 0, SYSUTCDATETIME(), SYSUTCDATETIME()"
                ")"
            ),
            {
                "event_id": str(event_id),
                "org_id": str(org_id),
                "loan_id": str(loan_id),
                "payload_json": json.dumps(
                    {
                        "loan_id": str(loan_id),
                        "borrower_user_id": str(user_id),
                        "book_title": "Clean Architecture",
                    }
                ),
                "corr_id": str(uuid4()),
                "idemp_key": f"loan-{loan_id}",
            },
        )
        connection.commit()

    # 2. Configure failing email adapter
    sink = DevelopmentEmailSink()
    sink.simulate_failure(count=1, error=EmailDeliveryError("Connection reset by peer"))
    consumer = EmailDeliveryConsumer(email_port=sink, deduplication_port=dedup)

    dispatcher = OutboxDispatcherService(
        claim_store=claim_store,
        deduplication_port=dedup,
        tenant_context=tenant_context,
        max_retries=3,
        base_backoff_seconds=2,
    )
    dispatcher.register_handler(
        "circulation.loan_checked_out",
        consumer.handle_event,
        max_payload_version=1,
    )

    # 3. Dispatch claims event and encounters provider failure
    claimed = dispatcher.dispatch_one()
    assert claimed is True

    # 4. Verify originating outbox event is NOT dropped or lost; scheduled for retry
    with tenant_context.connection(org_id) as connection:
        row = connection.execute(
            text(
                "SELECT attempts, delivered_at, dead_lettered_at, last_error "
                "FROM ops.outbox_events WHERE event_id = :event_id"
            ),
            {"event_id": str(event_id)},
        ).fetchone()

        assert row is not None
        assert row.attempts == 1
        assert row.delivered_at is None
        assert row.dead_lettered_at is None
        assert "Connection reset by peer" in str(row.last_error)


def test_bounded_retry_and_dead_letter_visibility(
    seeded_database_urls: SqlServerUrls,
) -> None:
    """Failed email jobs retry with bounded exponential backoff and transition to dead-letter."""
    org_id = UUID(seeded_database_urls["ORG_A_ID"])
    user_id = UUID(seeded_database_urls["USER_A1_ID"])
    tenant_context = SqlServerTenantContext(
        seeded_database_urls["DATABASE_RUNTIME_URL"]
    )
    claim_store = SqlServerOutboxClaimStore(
        seeded_database_urls["DATABASE_RUNTIME_URL"]
    )
    dedup = SqlServerConsumerDeduplicationStore()

    event_id = uuid4()
    with tenant_context.connection(org_id) as connection:
        connection.execute(
            text(
                "INSERT INTO ops.outbox_events ("
                "  event_id, organization_id, event_type, aggregate_type, aggregate_id, "
                "  payload_version, payload_json, correlation_id, idempotency_key, "
                "  attempts, created_at, available_at"
                ") VALUES ("
                "  :event_id, :org_id, 'circulation.loan_overdue', 'loan', :agg_id, "
                "  1, :payload_json, :corr_id, :idemp_key, 0, SYSUTCDATETIME(), SYSUTCDATETIME()"
                ")"
            ),
            {
                "event_id": str(event_id),
                "org_id": str(org_id),
                "agg_id": str(uuid4()),
                "payload_json": json.dumps(
                    {
                        "borrower_user_id": str(user_id),
                        "book_title": "Refactoring",
                    }
                ),
                "corr_id": str(uuid4()),
                "idemp_key": f"overdue-{event_id}",
            },
        )
        connection.commit()

    sink = DevelopmentEmailSink()
    sink.simulate_failure(count=10, error=EmailDeliveryError("SMTP 550 Mailbox full"))
    consumer = EmailDeliveryConsumer(email_port=sink, deduplication_port=dedup)

    max_retries = 2
    dispatcher = OutboxDispatcherService(
        claim_store=claim_store,
        deduplication_port=dedup,
        tenant_context=tenant_context,
        max_retries=max_retries,
        base_backoff_seconds=1,
    )
    dispatcher.register_handler(
        "circulation.loan_overdue",
        consumer.handle_event,
        max_payload_version=1,
    )

    # Dispatch attempt 1 -> failed, scheduled retry
    assert dispatcher.dispatch_one() is True
    # Make event immediately available for attempt 2
    with connect(seeded_database_urls["DATABASE_BOOTSTRAP_URL"]) as connection:
        connection.execute(
            f"UPDATE ops.outbox_events SET available_at = SYSUTCDATETIME() "
            f"WHERE event_id = '{event_id}'"
        )

    # Dispatch attempt 2 (max_retries reached) -> dead_letter
    assert dispatcher.dispatch_one() is True

    with tenant_context.connection(org_id) as connection:
        row = connection.execute(
            text(
                "SELECT attempts, delivered_at, dead_lettered_at, last_error "
                "FROM ops.outbox_events WHERE event_id = :event_id"
            ),
            {"event_id": str(event_id)},
        ).fetchone()

        assert row is not None
        assert row.attempts == 2
        assert row.delivered_at is None
        assert row.dead_lettered_at is not None
        assert "SMTP 550 Mailbox full" in str(row.last_error)


def test_email_replay_safety_deduplication(
    seeded_database_urls: SqlServerUrls,
) -> None:
    """Replaying an outbox event does NOT send duplicate emails."""
    org_id = UUID(seeded_database_urls["ORG_A_ID"])
    user_id = UUID(seeded_database_urls["USER_A1_ID"])
    tenant_context = SqlServerTenantContext(
        seeded_database_urls["DATABASE_RUNTIME_URL"]
    )
    sink = DevelopmentEmailSink()
    dedup = SqlServerConsumerDeduplicationStore()
    consumer = EmailDeliveryConsumer(email_port=sink, deduplication_port=dedup)

    event_id = uuid4()
    event = _create_claimed_event(
        event_id=event_id,
        organization_id=org_id,
        event_type="circulation.reservation_allocated",
        payload={
            "reservation_id": str(uuid4()),
            "organization_id": str(org_id),
            "book_title": "Clean Code",
            "requester_user_id": str(user_id),
        },
    )

    # First execution
    with tenant_context.connection(org_id) as connection:
        _persist_outbox_event(connection, event)
        consumer.handle_event(connection, event)
        connection.commit()

    assert len(sink.get_deliveries()) == 1

    # Second execution (replay of the same event)
    with tenant_context.connection(org_id) as connection:
        consumer.handle_event(connection, event)
        connection.commit()

    # Must still be exactly 1 delivery
    assert len(sink.get_deliveries()) == 1


def test_email_payload_sanitization_removes_secrets(
    seeded_database_urls: SqlServerUrls,
) -> None:
    """Sensitive material (password, token, secret, card number) is scrubbed from email."""
    org_id = UUID(seeded_database_urls["ORG_A_ID"])
    user_id = UUID(seeded_database_urls["USER_A1_ID"])
    tenant_context = SqlServerTenantContext(
        seeded_database_urls["DATABASE_RUNTIME_URL"]
    )
    sink = DevelopmentEmailSink()
    dedup = SqlServerConsumerDeduplicationStore()
    consumer = EmailDeliveryConsumer(email_port=sink, deduplication_port=dedup)

    event = _create_claimed_event(
        organization_id=org_id,
        event_type="public_library.payment_recorded",
        payload={
            "payment_id": str(uuid4()),
            "user_id": str(user_id),
            "amount": "15.00",
            "currency": "USD",
            "password": "supersecretpassword",
            "token": "bearer-token-12345",
            "api_key": "secret-key-999",
            "card_number": "4111222233334444",
            "cvv": "123",
            "client_secret": "sensitive-data",
        },
    )

    with tenant_context.connection(org_id) as connection:
        _persist_outbox_event(connection, event)
        consumer.handle_event(connection, event)
        connection.commit()

    assert len(sink.get_deliveries()) == 1
    email = sink.get_deliveries()[0]
    body = email.body_text
    assert "supersecretpassword" not in body
    assert "bearer-token-12345" not in body
    assert "secret-key-999" not in body
    assert "4111222233334444" not in body
    assert "123" not in body
    assert "sensitive-data" not in body
    assert "15.00" in body


def test_worker_health_and_queue_metrics(
    seeded_database_urls: SqlServerUrls,
) -> None:
    """Worker observability service exposes health, queue metrics, and dead letters."""
    metrics_store = SqlServerQueueMetricsStore(
        seeded_database_urls["DATABASE_RUNTIME_URL"]
    )
    health_service = WorkerHealthService(
        database_url=seeded_database_urls["DATABASE_RUNTIME_URL"],
        redis_url="redis://localhost:6379/0",
        metrics_store=metrics_store,
        broker_probe=lambda: True,
    )

    health_status = health_service.check_health()
    assert health_status.database_connected is True
    assert health_status.broker_connected is True
    assert isinstance(health_status.queue_metrics, QueueMetrics)
    assert health_status.status in ("ok", "degraded")


def test_worker_graceful_shutdown() -> None:
    """Worker shutdown coordinator stops new claims and drains active execution."""
    shutdown = WorkerGracefulShutdown()
    assert shutdown.is_running() is True

    shutdown.request_shutdown()
    assert shutdown.is_running() is False


def test_worker_reconnect_policy() -> None:
    """Worker reconnect policy retries transient failures with bounded backoff."""
    reconnect = WorkerReconnectPolicy(max_attempts=3, base_delay_seconds=0.01)
    call_count = 0

    def flaky_operation() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("Transient network drop")
        return "success"

    result = reconnect.execute_with_retry(flaky_operation)
    assert result == "success"
    assert call_count == 3


class _InMemoryClaimStore:
    def __init__(self, events: list[ClaimedOutboxEvent]) -> None:
        self.events = list(events)
        self.delivered: list[UUID] = []
        self.failures: list[dict[str, Any]] = []

    def claim_next_event(
        self,
        *,
        lease_token: UUID,
        lease_duration_seconds: int = 30,
    ) -> ClaimedOutboxEvent | None:
        if not self.events:
            return None
        event = self.events.pop(0)
        return ClaimedOutboxEvent(
            event_id=event.event_id,
            organization_id=event.organization_id,
            event_type=event.event_type,
            aggregate_type=event.aggregate_type,
            aggregate_id=event.aggregate_id,
            payload_version=event.payload_version,
            payload_json=event.payload_json,
            correlation_id=event.correlation_id,
            idempotency_key=event.idempotency_key,
            attempts=event.attempts + 1,
            lease_token=lease_token,
            lease_expires_at=datetime.now(timezone.utc),
            created_at=event.created_at,
        )

    def mark_delivered(
        self,
        *,
        event_id: UUID,
        lease_token: UUID,
        organization_id: UUID | None = None,
    ) -> bool:
        self.delivered.append(event_id)
        return True

    def record_failure(
        self,
        *,
        event_id: UUID,
        lease_token: UUID,
        error_message: str,
        retry_delay_seconds: int = 0,
        is_dead_letter: bool = False,
        organization_id: UUID | None = None,
    ) -> None:
        self.failures.append(
            {
                "event_id": event_id,
                "lease_token": lease_token,
                "error_message": error_message,
                "retry_delay_seconds": retry_delay_seconds,
                "is_dead_letter": is_dead_letter,
            }
        )


class _InMemoryDeduplicationStore:
    def __init__(self) -> None:
        self.processed: set[tuple[UUID, UUID, str]] = set()
        self.job_statuses: list[dict[str, Any]] = []

    def is_processed(
        self,
        connection: Any,
        *,
        organization_id: UUID,
        outbox_event_id: UUID,
        job_type: str,
        deduplication_key: str | None = None,
    ) -> bool:
        return (organization_id, outbox_event_id, job_type) in self.processed

    def record_processed(
        self,
        connection: Any,
        *,
        organization_id: UUID,
        outbox_event_id: UUID,
        job_type: str,
        payload_version: int,
        deduplication_key: str | None = None,
    ) -> Any:
        self.processed.add((organization_id, outbox_event_id, job_type))
        return MagicMock()

    def record_job_status(
        self,
        connection: Any,
        *,
        organization_id: UUID,
        outbox_event_id: UUID,
        job_type: str,
        payload_version: int,
        status: str,
        attempts: int,
        next_run_at: datetime | None = None,
        last_error: str | None = None,
    ) -> Any:
        self.job_statuses.append(
            {
                "organization_id": organization_id,
                "outbox_event_id": outbox_event_id,
                "job_type": job_type,
                "status": status,
                "attempts": attempts,
                "last_error": last_error,
            }
        )
        return MagicMock()


class _MockTenantContext:
    def __init__(self, user_email: str = "alice@example.com") -> None:
        self.user_email = user_email

    from contextlib import contextmanager

    @contextmanager
    def connection(self, organization_id: UUID) -> Iterator[Any]:
        conn = MagicMock()
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row.email = self.user_email
        mock_result.fetchone.return_value = mock_row
        conn.execute.return_value = mock_result
        yield conn


def test_in_memory_provider_failure_retry_and_dead_letter() -> None:
    """In-memory verification of provider failure, bounded exponential backoff, and dead-letter state."""
    org_id = uuid4()
    event_id = uuid4()
    event = _create_claimed_event(
        event_id=event_id,
        organization_id=org_id,
        event_type="circulation.loan_checked_out",
        payload={
            "loan_id": str(uuid4()),
            "borrower_user_id": str(uuid4()),
            "book_title": "Design Patterns",
            "password": "should-be-scrubbed-password",
        },
        attempts=0,
    )

    claim_store = _InMemoryClaimStore([event])
    dedup = _InMemoryDeduplicationStore()
    sink = DevelopmentEmailSink()
    sink.simulate_failure(
        count=10, error=EmailDeliveryError("SMTP connection dropped password=rawsecret")
    )
    consumer = EmailDeliveryConsumer(email_port=sink, deduplication_port=dedup)
    tenant_context = _MockTenantContext()

    max_retries = 2
    dispatcher = OutboxDispatcherService(
        claim_store=claim_store,  # type: ignore[arg-type]
        deduplication_port=dedup,  # type: ignore[arg-type]
        tenant_context=tenant_context,  # type: ignore[arg-type]
        max_retries=max_retries,
        base_backoff_seconds=1,
    )
    dispatcher.register_handler(
        "circulation.loan_checked_out",
        consumer.handle_event,
        max_payload_version=1,
    )

    # Attempt 1: failure with retry scheduled
    assert dispatcher.dispatch_one() is True
    assert len(claim_store.failures) == 1
    failure1 = claim_store.failures[0]
    assert failure1["is_dead_letter"] is False
    assert failure1["retry_delay_seconds"] == 1
    assert "rawsecret" not in failure1["error_message"]

    # Re-queue for Attempt 2 (exhausted -> dead letter)
    event_retry = _create_claimed_event(
        event_id=event_id,
        organization_id=org_id,
        event_type="circulation.loan_checked_out",
        payload={
            "loan_id": str(uuid4()),
            "borrower_user_id": str(uuid4()),
            "book_title": "Design Patterns",
        },
        attempts=1,
    )
    claim_store.events.append(event_retry)
    assert dispatcher.dispatch_one() is True
    assert len(claim_store.failures) == 2
    failure2 = claim_store.failures[1]
    assert failure2["is_dead_letter"] is True

    # Job record status reflects dead_letter
    dead_letters = [s for s in dedup.job_statuses if s["status"] == "dead_letter"]
    assert len(dead_letters) == 1
    assert dead_letters[0]["attempts"] == 2


def test_in_memory_email_replay_deduplication() -> None:
    """In-memory verification that replayed events are safe and not delivered twice."""
    org_id = uuid4()
    event_id = uuid4()
    event = _create_claimed_event(
        event_id=event_id,
        organization_id=org_id,
        event_type="circulation.loan_approved",
        payload={"recipient_email": "reader@example.com", "book_title": "Clean Code"},
    )
    claim_store = _InMemoryClaimStore([event])
    dedup = _InMemoryDeduplicationStore()
    sink = DevelopmentEmailSink()
    consumer = EmailDeliveryConsumer(email_port=sink, deduplication_port=dedup)
    tenant_context = _MockTenantContext()

    dispatcher = OutboxDispatcherService(
        claim_store=claim_store,  # type: ignore[arg-type]
        deduplication_port=dedup,  # type: ignore[arg-type]
        tenant_context=tenant_context,  # type: ignore[arg-type]
    )
    dispatcher.register_handler(
        "circulation.loan_approved",
        consumer.handle_event,
        max_payload_version=1,
    )

    # First dispatch -> email delivered
    assert dispatcher.dispatch_one() is True
    assert len(sink.get_deliveries()) == 1

    # Replay the same event -> consumer detects is_processed and skips send
    claim_store.events.append(event)
    assert dispatcher.dispatch_one() is True
    assert len(sink.get_deliveries()) == 1


def test_worker_health_http_endpoint() -> None:
    """HTTP endpoint GET /api/v1/health/worker returns worker status and queue metrics."""
    from openlibrary.app.config import AppConfig
    from openlibrary.app.factory import create_app

    mock_metrics_store = MagicMock()
    mock_metrics_store.get_queue_metrics.return_value = QueueMetrics(
        pending_count=3,
        in_flight_count=1,
        dead_letter_count=0,
        delivered_count=150,
        failed_jobs_count=0,
    )
    health_service = WorkerHealthService(
        database_url="mssql+pyodbc://mock",
        redis_url="redis://localhost:6379/0",
        metrics_store=mock_metrics_store,
        database_probe=lambda: True,
        broker_probe=lambda: True,
    )

    app = create_app(
        AppConfig(
            readiness_probe=lambda: True,
            worker_health_service=health_service,
        )
    )
    client = app.test_client()

    response = client.get("/api/v1/health/worker")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"
    assert data["database_connected"] is True
    assert data["broker_connected"] is True
    assert data["queue_metrics"]["pending_count"] == 3
    assert data["queue_metrics"]["delivered_count"] == 150

    # Test unavailable when broker fails
    health_service._broker_probe = lambda: False
    bad_response = client.get("/api/v1/health/worker")
    assert bad_response.status_code == 503
    assert bad_response.mimetype == "application/problem+json"
    problem_data = bad_response.get_json()
    assert problem_data["title"] == "Worker unavailable"
