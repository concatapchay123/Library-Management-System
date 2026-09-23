"""Unit tests for NotificationService, NotificationConsumer, and authorization controls."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from uuid import UUID, uuid4

import pytest

from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.authorization import (
    AuthorizationDenied,
    AuthorizationPort,
)
from openlibrary.modules.core.application.notifications import (
    Notification,
    NotificationConsumer,
    NotificationService,
    NotificationStore,
    sanitize_notification_payload,
)
from openlibrary.modules.core.domain.notifications import (
    NotificationNotFoundError,
    NotificationStatus,
)
from openlibrary.modules.ops.application.dispatcher import (
    ConsumerDeduplicationPort,
)
from openlibrary.modules.ops.application.persistence import (
    ClaimedOutboxEvent,
    JobRecord,
)


class InMemoryNotificationStore(NotificationStore):
    """In-memory mock store for unit testing."""

    def __init__(self) -> None:
        self.notifications: dict[tuple[UUID, UUID, UUID], Notification] = {}

    def create_notification(
        self,
        notification: Notification,
        *,
        outbox_event_id: UUID | None = None,
    ) -> Notification:
        key = (
            notification.organization_id,
            notification.user_id,
            notification.notification_id,
        )
        self.notifications[key] = notification
        return notification

    def create_notification_in_connection(
        self,
        connection: object,
        notification: Notification,
        *,
        outbox_event_id: UUID | None = None,
    ) -> Notification:
        return self.create_notification(notification, outbox_event_id=outbox_event_id)

    def list_notifications(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        status: str | None = None,
        limit: int = 50,
    ) -> list[Notification]:
        results: list[Notification] = []
        for (org_id, u_id, _), notif in self.notifications.items():
            if org_id == organization_id and u_id == user_id:
                if status is None or notif.status == status:
                    results.append(notif)
        results.sort(key=lambda n: n.created_at, reverse=True)
        return results[:limit]

    def get_notification(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        notification_id: UUID,
    ) -> Notification | None:
        return self.notifications.get((organization_id, user_id, notification_id))

    def mark_as_read(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        notification_id: UUID,
        read_at: datetime,
    ) -> Notification | None:
        key = (organization_id, user_id, notification_id)
        existing = self.notifications.get(key)
        if existing is None:
            return None
        updated = Notification(
            notification_id=existing.notification_id,
            organization_id=existing.organization_id,
            user_id=existing.user_id,
            type=existing.type,
            payload=existing.payload,
            channel=existing.channel,
            status=NotificationStatus.READ,
            read_at=existing.read_at or read_at,
            created_at=existing.created_at,
            outbox_event_id=existing.outbox_event_id,
        )
        self.notifications[key] = updated
        return updated


class MockAuthorizer(AuthorizationPort):
    def __init__(self, allowed: set[tuple[UUID, str]] | None = None) -> None:
        self.allowed = allowed or set()

    def allow(self, principal: Principal, permission: str) -> None:
        self.allowed.add((principal.user_id, permission))

    def require(self, principal: Principal, permission: str) -> None:
        if (principal.user_id, permission) not in self.allowed:
            raise AuthorizationDenied(f"Permission {permission} denied")


class MockDeduplicationPort(ConsumerDeduplicationPort):
    def __init__(self) -> None:
        self.processed: set[tuple[UUID, UUID, str]] = set()

    def is_processed(
        self,
        connection: object,
        *,
        organization_id: UUID,
        outbox_event_id: UUID,
        job_type: str,
        deduplication_key: str | None = None,
    ) -> bool:
        return (organization_id, outbox_event_id, job_type) in self.processed

    def record_processed(
        self,
        connection: object,
        *,
        organization_id: UUID,
        outbox_event_id: UUID,
        job_type: str,
        payload_version: int,
        deduplication_key: str | None = None,
    ) -> JobRecord:
        self.processed.add((organization_id, outbox_event_id, job_type))
        now = datetime.now(timezone.utc)
        return JobRecord(
            job_id=uuid4(),
            organization_id=organization_id,
            outbox_event_id=outbox_event_id,
            job_type=job_type,
            payload_version=payload_version,
            status="completed",
            attempts=1,
            created_at=now,
            updated_at=now,
        )

    def record_job_status(
        self,
        connection: object,
        *,
        organization_id: UUID,
        outbox_event_id: UUID,
        job_type: str,
        payload_version: int,
        status: str,
        attempts: int,
        next_run_at: datetime | None = None,
        last_error: str | None = None,
    ) -> JobRecord:
        now = datetime.now(timezone.utc)
        return JobRecord(
            job_id=uuid4(),
            organization_id=organization_id,
            outbox_event_id=outbox_event_id,
            job_type=job_type,
            payload_version=payload_version,
            status=status,
            attempts=attempts,
            created_at=now,
            updated_at=now,
            next_run_at=next_run_at,
            last_error=last_error,
        )


def _claimed_event(
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


def test_list_notifications_requires_authorization() -> None:
    store = InMemoryNotificationStore()
    authorizer = MockAuthorizer()
    service = NotificationService(store=store, authorizer=authorizer)

    actor = Principal(user_id=uuid4(), organization_id=uuid4(), session_id=uuid4())
    with pytest.raises(AuthorizationDenied):
        service.list_notifications(actor=actor)


def test_list_notifications_filters_by_user_and_status() -> None:
    store = InMemoryNotificationStore()
    authorizer = MockAuthorizer()
    service = NotificationService(store=store, authorizer=authorizer)

    org_id = uuid4()
    user_1 = uuid4()
    user_2 = uuid4()
    actor_1 = Principal(user_id=user_1, organization_id=org_id, session_id=uuid4())
    authorizer.allow(actor_1, "notification.read")

    # Seed notifications
    notif_1 = Notification(
        notification_id=uuid4(),
        organization_id=org_id,
        user_id=user_1,
        type="circulation.loan_approved",
        payload={"loan_id": str(uuid4())},
        status=NotificationStatus.UNREAD,
    )
    notif_2 = Notification(
        notification_id=uuid4(),
        organization_id=org_id,
        user_id=user_1,
        type="circulation.loan_returned",
        payload={"loan_id": str(uuid4())},
        status=NotificationStatus.READ,
        read_at=datetime.now(timezone.utc),
    )
    notif_3 = Notification(
        notification_id=uuid4(),
        organization_id=org_id,
        user_id=user_2,
        type="circulation.loan_approved",
        payload={"loan_id": str(uuid4())},
        status=NotificationStatus.UNREAD,
    )
    store.create_notification(notif_1)
    store.create_notification(notif_2)
    store.create_notification(notif_3)

    # List all for user_1
    all_notifs = service.list_notifications(actor=actor_1)
    assert len(all_notifs) == 2
    assert {n.notification_id for n in all_notifs} == {
        notif_1.notification_id,
        notif_2.notification_id,
    }

    # List unread only
    unread_notifs = service.list_notifications(actor=actor_1, status="unread")
    assert len(unread_notifs) == 1
    assert unread_notifs[0].notification_id == notif_1.notification_id

    # Invalid status filter
    with pytest.raises(ValueError, match="Invalid status filter"):
        service.list_notifications(actor=actor_1, status="invalid_status")


def test_mark_notification_read_is_explicit_and_idempotent() -> None:
    store = InMemoryNotificationStore()
    authorizer = MockAuthorizer()
    clock_time = datetime(2026, 9, 23, 14, 0, tzinfo=timezone.utc)
    service = NotificationService(
        store=store, authorizer=authorizer, clock=lambda: clock_time
    )

    org_id = uuid4()
    user_id = uuid4()
    actor = Principal(user_id=user_id, organization_id=org_id, session_id=uuid4())
    authorizer.allow(actor, "notification.read")

    notif = Notification(
        notification_id=uuid4(),
        organization_id=org_id,
        user_id=user_id,
        type="circulation.loan_checked_out",
        payload={"loan_id": str(uuid4())},
        status=NotificationStatus.UNREAD,
    )
    store.create_notification(notif)

    # Mark read
    read_notif = service.mark_notification_read(
        actor=actor, notification_id=notif.notification_id
    )
    assert read_notif.status == NotificationStatus.READ
    assert read_notif.read_at == clock_time

    # Idempotent second mark
    later_time = datetime(2026, 9, 23, 15, 0, tzinfo=timezone.utc)
    service_later = NotificationService(
        store=store, authorizer=authorizer, clock=lambda: later_time
    )
    second_read = service_later.mark_notification_read(
        actor=actor, notification_id=notif.notification_id
    )
    assert second_read.status == NotificationStatus.READ
    # Preserves first read_at
    assert second_read.read_at == clock_time


def test_mark_notification_read_not_found_on_other_user() -> None:
    store = InMemoryNotificationStore()
    authorizer = MockAuthorizer()
    service = NotificationService(store=store, authorizer=authorizer)

    org_id = uuid4()
    user_1 = uuid4()
    user_2 = uuid4()
    actor_2 = Principal(user_id=user_2, organization_id=org_id, session_id=uuid4())
    authorizer.allow(actor_2, "notification.read")

    notif = Notification(
        notification_id=uuid4(),
        organization_id=org_id,
        user_id=user_1,
        type="circulation.loan_overdue",
        payload={"loan_id": str(uuid4())},
        status=NotificationStatus.UNREAD,
    )
    store.create_notification(notif)

    # User 2 cannot mark user 1's notification read
    with pytest.raises(NotificationNotFoundError):
        service.mark_notification_read(
            actor=actor_2, notification_id=notif.notification_id
        )


def test_consumer_handles_events_idempotently() -> None:
    store = InMemoryNotificationStore()
    dedup = MockDeduplicationPort()
    consumer = NotificationConsumer(store=store, deduplication_port=dedup)

    org_id = uuid4()
    user_id = uuid4()
    ev_id = uuid4()
    event = _claimed_event(
        event_id=ev_id,
        organization_id=org_id,
        event_type="circulation.loan_approved",
        payload={"borrower_user_id": str(user_id), "loan_id": str(uuid4())},
    )

    # First consumption
    conn = object()
    consumer.handle_event(conn, event)
    assert len(store.notifications) == 1

    # Second consumption (replayed event)
    consumer.handle_event(conn, event)
    # Deduplication port halts duplicate processing
    assert len(store.notifications) == 1


def test_consumer_unsupported_version_raises() -> None:
    store = InMemoryNotificationStore()
    consumer = NotificationConsumer(store=store)

    event = _claimed_event(
        organization_id=uuid4(),
        event_type="circulation.loan_approved",
        payload={"borrower_user_id": str(uuid4())},
        payload_version=2,  # unsupported
    )
    with pytest.raises(ValueError, match="Unsupported payload version"):
        consumer.handle_event(object(), event)


def test_payload_sanitization_removes_secrets() -> None:
    raw_payload = {
        "user_id": str(uuid4()),
        "amount": "25.00",
        "currency": "USD",
        "card_number": "4111222233334444",
        "secret_token": "super_secret_jwt",
        "nested": {
            "password": "plaintext_password",
            "safe_description": "Overdue fine payment",
            "cvc": "123",
        },
    }
    sanitized = sanitize_notification_payload(raw_payload)

    assert "user_id" in sanitized
    assert "amount" in sanitized
    assert "currency" in sanitized
    assert "card_number" not in sanitized
    assert "secret_token" not in sanitized
    assert "nested" in sanitized
    nested = sanitized["nested"]
    assert isinstance(nested, dict)
    assert "password" not in nested
    assert "cvc" not in nested
    assert nested.get("safe_description") == "Overdue fine payment"
