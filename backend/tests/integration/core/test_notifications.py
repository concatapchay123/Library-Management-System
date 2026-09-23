"""Integration coverage for BE-025: in-app notification persistence, replay deduplication, and read workflow."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
import json
import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy.engine import make_url

from openlibrary.infrastructure.sqlserver.migrate import (
    bootstrap_database_identities,
    connect,
    database_url_for,
    run_migrations,
)
from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.authorization import AuthorizationPort
from openlibrary.modules.core.application.notifications import (
    Notification,
    NotificationConsumer,
    NotificationService,
    register_notification_consumers,
)
from openlibrary.modules.core.domain.notifications import (
    NotificationNotFoundError,
    NotificationStatus,
)
from openlibrary.modules.core.infrastructure.notifications import (
    SqlServerNotificationStore,
)
from openlibrary.modules.core.infrastructure.tenancy import SqlServerTenantContext
from openlibrary.modules.ops.application.dispatcher import (
    OutboxDispatcherService,
)
from openlibrary.modules.ops.application.persistence import ClaimedOutboxEvent
from openlibrary.modules.ops.infrastructure.dispatcher import (
    SqlServerConsumerDeduplicationStore,
    SqlServerOutboxClaimStore,
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
    database_name = f"openlibrary_be025_{uuid4().hex}"
    bootstrap_url = database_urls["DATABASE_BOOTSTRAP_URL"]
    with connect(bootstrap_url, database="master") as connection:
        connection.execute(f"CREATE DATABASE [{database_name}]")

    urls = SqlServerUrls(
        {
            name: database_url_for(url, database_name)
            for name, url in database_urls.items()
        }
    )
    migration_login = f"be025_migrator_{uuid4().hex}"
    runtime_login = f"be025_runtime_{uuid4().hex}"
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

    org_a_id = uuid4()
    org_b_id = uuid4()
    user_a1_id = uuid4()
    user_a2_id = uuid4()
    user_b1_id = uuid4()

    with connect(urls["DATABASE_BOOTSTRAP_URL"]) as connection:
        connection.execute(
            "INSERT INTO core.organizations "
            "(organization_id, name, slug, organization_type, status, timezone, settings_json) "
            f"VALUES ('{org_a_id}', N'Tenant Alpha', 'tenant-alpha', 'public_library', 'active', 'UTC', N'{{}}'), "
            f"('{org_b_id}', N'Tenant Beta', 'tenant-beta', 'public_library', 'active', 'UTC', N'{{}}')"
        )
        connection.execute(
            "INSERT INTO core.users "
            "(user_id, organization_id, email, password_hash, status) "
            f"VALUES ('{user_a1_id}', '{org_a_id}', 'usera1@example.com', 'hash', 'active'), "
            f"('{user_a2_id}', '{org_a_id}', 'usera2@example.com', 'hash', 'active'), "
            f"('{user_b1_id}', '{org_b_id}', 'userb1@example.com', 'hash', 'active')"
        )

    urls["ORG_A_ID"] = str(org_a_id)
    urls["ORG_B_ID"] = str(org_b_id)
    urls["USER_A1_ID"] = str(user_a1_id)
    urls["USER_A2_ID"] = str(user_a2_id)
    urls["USER_B1_ID"] = str(user_b1_id)

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


class _AllowAllAuthorizer(AuthorizationPort):
    def require(self, principal: Principal, permission: str) -> None:
        pass


def _create_claimed_event(
    *,
    event_id: UUID | None = None,
    organization_id: UUID,
    event_type: str,
    payload: dict[str, object],
    payload_version: int = 1,
) -> ClaimedOutboxEvent:
    now = datetime.now(timezone.utc)
    ev_id = event_id or uuid4()
    return ClaimedOutboxEvent(
        event_id=ev_id,
        organization_id=organization_id,
        event_type=event_type,
        aggregate_type="loan",
        aggregate_id=uuid4(),
        payload_version=payload_version,
        payload_json=json.dumps(payload),
        correlation_id=uuid4(),
        idempotency_key=f"test:{ev_id}",
        attempts=1,
        lease_token=uuid4(),
        lease_expires_at=now,
        created_at=now,
    )


def test_notification_classes_exist() -> None:
    assert Notification is not None
    assert NotificationStatus.UNREAD == "unread"
    assert NotificationStatus.READ == "read"
    assert NotificationService is not None
    assert NotificationConsumer is not None
    assert register_notification_consumers is not None
    assert OutboxDispatcherService is not None
    assert SqlServerOutboxClaimStore is not None


def test_domain_event_consumed_and_persisted(
    seeded_database_urls: SqlServerUrls,
) -> None:
    org_id = UUID(seeded_database_urls["ORG_A_ID"])
    user_id = UUID(seeded_database_urls["USER_A1_ID"])
    tenant_context = SqlServerTenantContext(
        seeded_database_urls["DATABASE_RUNTIME_URL"]
    )
    store = SqlServerNotificationStore(seeded_database_urls["DATABASE_RUNTIME_URL"])
    dedup = SqlServerConsumerDeduplicationStore()
    consumer = NotificationConsumer(store=store, deduplication_port=dedup)

    event = _create_claimed_event(
        organization_id=org_id,
        event_type="circulation.loan_approved",
        payload={
            "loan_id": str(uuid4()),
            "organization_id": str(org_id),
            "copy_id": str(uuid4()),
            "borrower_user_id": str(user_id),
        },
    )

    with tenant_context.connection(org_id) as connection:
        consumer.handle_event(connection, event)
        connection.commit()

    service = NotificationService(store=store, authorizer=_AllowAllAuthorizer())
    actor = Principal(user_id=user_id, organization_id=org_id, session_id=uuid4())
    notifications = service.list_notifications(actor=actor, status="unread")

    assert len(notifications) == 1
    notif = notifications[0]
    assert notif.user_id == user_id
    assert notif.organization_id == org_id
    assert notif.type == "circulation.loan_approved"
    assert notif.status == NotificationStatus.UNREAD
    assert notif.read_at is None


def test_event_replay_creates_no_duplicate_notification(
    seeded_database_urls: SqlServerUrls,
) -> None:
    org_id = UUID(seeded_database_urls["ORG_A_ID"])
    user_id = UUID(seeded_database_urls["USER_A1_ID"])
    tenant_context = SqlServerTenantContext(
        seeded_database_urls["DATABASE_RUNTIME_URL"]
    )
    store = SqlServerNotificationStore(seeded_database_urls["DATABASE_RUNTIME_URL"])
    dedup = SqlServerConsumerDeduplicationStore()
    consumer = NotificationConsumer(store=store, deduplication_port=dedup)

    replay_event_id = uuid4()
    event = _create_claimed_event(
        event_id=replay_event_id,
        organization_id=org_id,
        event_type="circulation.reservation_allocated",
        payload={
            "reservation_id": str(uuid4()),
            "organization_id": str(org_id),
            "book_id": str(uuid4()),
            "copy_id": str(uuid4()),
            "requester_user_id": str(user_id),
            "hold_expires_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    # First delivery
    with tenant_context.connection(org_id) as connection:
        consumer.handle_event(connection, event)
        connection.commit()

    # Replay delivery (same outbox event)
    with tenant_context.connection(org_id) as connection:
        consumer.handle_event(connection, event)
        connection.commit()

    service = NotificationService(store=store, authorizer=_AllowAllAuthorizer())
    actor = Principal(user_id=user_id, organization_id=org_id, session_id=uuid4())
    notifications = service.list_notifications(actor=actor)

    # Must contain only 1 reservation_allocated notification
    alloc_notifs = [
        n for n in notifications if n.type == "circulation.reservation_allocated"
    ]
    assert len(alloc_notifs) == 1


def test_read_state_transition_is_explicit_and_idempotent(
    seeded_database_urls: SqlServerUrls,
) -> None:
    org_id = UUID(seeded_database_urls["ORG_A_ID"])
    user_id = UUID(seeded_database_urls["USER_A1_ID"])
    tenant_context = SqlServerTenantContext(
        seeded_database_urls["DATABASE_RUNTIME_URL"]
    )
    store = SqlServerNotificationStore(seeded_database_urls["DATABASE_RUNTIME_URL"])
    dedup = SqlServerConsumerDeduplicationStore()
    consumer = NotificationConsumer(store=store, deduplication_port=dedup)

    event = _create_claimed_event(
        organization_id=org_id,
        event_type="circulation.loan_overdue",
        payload={
            "loan_id": str(uuid4()),
            "organization_id": str(org_id),
            "copy_id": str(uuid4()),
            "borrower_user_id": str(user_id),
            "due_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    with tenant_context.connection(org_id) as connection:
        consumer.handle_event(connection, event)
        connection.commit()

    service = NotificationService(store=store, authorizer=_AllowAllAuthorizer())
    actor = Principal(user_id=user_id, organization_id=org_id, session_id=uuid4())
    unread_items = service.list_notifications(actor=actor, status="unread")
    overdue_notif = next(
        n for n in unread_items if n.type == "circulation.loan_overdue"
    )

    # Transition to read
    read_notif = service.mark_notification_read(
        actor=actor, notification_id=overdue_notif.notification_id
    )
    assert read_notif.status == NotificationStatus.READ
    assert read_notif.read_at is not None

    # Idempotent second read
    second_read = service.mark_notification_read(
        actor=actor, notification_id=overdue_notif.notification_id
    )
    assert second_read.status == NotificationStatus.READ
    assert second_read.read_at == read_notif.read_at


def test_cross_tenant_notification_isolation(
    seeded_database_urls: SqlServerUrls,
) -> None:
    org_a_id = UUID(seeded_database_urls["ORG_A_ID"])
    org_b_id = UUID(seeded_database_urls["ORG_B_ID"])
    user_a1_id = UUID(seeded_database_urls["USER_A1_ID"])
    user_b1_id = UUID(seeded_database_urls["USER_B1_ID"])

    tenant_context = SqlServerTenantContext(
        seeded_database_urls["DATABASE_RUNTIME_URL"]
    )
    store = SqlServerNotificationStore(seeded_database_urls["DATABASE_RUNTIME_URL"])
    consumer = NotificationConsumer(store=store)

    event = _create_claimed_event(
        organization_id=org_a_id,
        event_type="circulation.loan_requested",
        payload={
            "loan_id": str(uuid4()),
            "organization_id": str(org_a_id),
            "copy_id": str(uuid4()),
            "borrower_user_id": str(user_a1_id),
        },
    )
    with tenant_context.connection(org_a_id) as connection:
        consumer.handle_event(connection, event)
        connection.commit()

    service = NotificationService(store=store, authorizer=_AllowAllAuthorizer())
    actor_a = Principal(
        user_id=user_a1_id, organization_id=org_a_id, session_id=uuid4()
    )
    actor_b = Principal(
        user_id=user_b1_id, organization_id=org_b_id, session_id=uuid4()
    )

    notifs_a = service.list_notifications(actor=actor_a)
    assert any(n.user_id == user_a1_id for n in notifs_a)

    # Tenant B user sees no notifications from Tenant A
    notifs_b = service.list_notifications(actor=actor_b)
    assert len(notifs_b) == 0

    # Tenant B user cannot mutate Tenant A notification
    target_id = notifs_a[0].notification_id
    with pytest.raises(NotificationNotFoundError):
        service.mark_notification_read(actor=actor_b, notification_id=target_id)
