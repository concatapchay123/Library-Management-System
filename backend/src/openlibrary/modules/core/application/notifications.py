"""Application service, protocols, and event consumer for in-app notifications."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
import re
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection

from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.authorization import AuthorizationPort
from openlibrary.modules.core.domain.notifications import (
    NotificationChannel,
    NotificationNotFoundError,
    NotificationStatus,
)
from openlibrary.modules.ops.application.dispatcher import (
    ConsumerDeduplicationPort,
    OutboxDispatcherService,
)
from openlibrary.modules.ops.application.persistence import ClaimedOutboxEvent


_LOGGER = logging.getLogger(__name__)

_SENSITIVE_KEY = re.compile(r"[^a-z0-9]")
_SENSITIVE_NAMES = frozenset(
    {
        "apikey",
        "authorization",
        "cardnumber",
        "cardpan",
        "clientsecret",
        "credential",
        "credentials",
        "cvc",
        "cvv",
        "idtoken",
        "pan",
        "password",
        "passwordhash",
        "paymentpayload",
        "rawpaymentpayload",
        "rawwebhookbody",
        "refreshtoken",
        "secret",
        "token",
        "webhookbody",
    }
)


def sanitize_notification_payload(data: Mapping[str, object]) -> dict[str, object]:
    """Recursively scrub credentials and sensitive fields from notification payload."""
    cleaned: dict[str, object] = {}
    for key, value in data.items():
        if not isinstance(key, str):
            continue
        normalized_key = _SENSITIVE_KEY.sub("", key.casefold())
        if (
            normalized_key in _SENSITIVE_NAMES
            or normalized_key.endswith("token")
            or "secret" in normalized_key
        ):
            continue
        if isinstance(value, Mapping):
            cleaned[key] = sanitize_notification_payload(value)
        elif isinstance(value, (list, tuple)):
            cleaned[key] = [
                sanitize_notification_payload(item)
                if isinstance(item, Mapping)
                else item
                for item in value
            ]
        else:
            cleaned[key] = value
    return cleaned


@dataclass(frozen=True, slots=True)
class Notification:
    """One immutable tenant-scoped notification representation."""

    notification_id: UUID
    organization_id: UUID
    user_id: UUID
    type: str
    payload: Mapping[str, object]
    channel: str = NotificationChannel.IN_APP
    status: str = NotificationStatus.UNREAD
    read_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    outbox_event_id: UUID | None = None


class NotificationStore(Protocol):
    """Port for persisting and querying tenant notifications."""

    def create_notification(
        self,
        notification: Notification,
        *,
        outbox_event_id: UUID | None = None,
    ) -> Notification:
        """Persist a new notification."""
        ...

    def create_notification_in_connection(
        self,
        connection: Connection,
        notification: Notification,
        *,
        outbox_event_id: UUID | None = None,
    ) -> Notification:
        """Persist a new notification inside an existing tenant transaction."""
        ...

    def list_notifications(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        status: str | None = None,
        limit: int = 50,
    ) -> list[Notification]:
        """List notifications ordered by created_at DESC."""
        ...

    def get_notification(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        notification_id: UUID,
    ) -> Notification | None:
        """Fetch a single notification by id."""
        ...

    def mark_as_read(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        notification_id: UUID,
        read_at: datetime,
    ) -> Notification | None:
        """Set status to read and record read_at timestamp."""
        ...


class NotificationService:
    """Application service for reading and updating notification state."""

    _PERM_READ = "notification.read"

    def __init__(
        self,
        *,
        store: NotificationStore,
        authorizer: AuthorizationPort,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._authorizer = authorizer
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def list_notifications(
        self,
        *,
        actor: Principal,
        status: str | None = None,
        limit: int = 50,
    ) -> list[Notification]:
        """List user inbox notifications under tenant authorization."""
        self._authorizer.require(actor, self._PERM_READ)
        if status is not None and status not in NotificationStatus:
            raise ValueError(f"Invalid status filter: {status}")
        return self._store.list_notifications(
            organization_id=actor.organization_id,
            user_id=actor.user_id,
            status=status,
            limit=limit,
        )

    def mark_notification_read(
        self,
        *,
        actor: Principal,
        notification_id: UUID,
    ) -> Notification:
        """Mark one notification read explicitly and idempotently."""
        self._authorizer.require(actor, self._PERM_READ)
        existing = self._store.get_notification(
            organization_id=actor.organization_id,
            user_id=actor.user_id,
            notification_id=notification_id,
        )
        if existing is None:
            raise NotificationNotFoundError(f"Notification {notification_id} not found")

        if existing.status == NotificationStatus.READ:
            return existing

        now = self._clock()
        updated = self._store.mark_as_read(
            organization_id=actor.organization_id,
            user_id=actor.user_id,
            notification_id=notification_id,
            read_at=now,
        )
        if updated is None:
            raise NotificationNotFoundError(f"Notification {notification_id} not found")
        return updated


SUPPORTED_NOTIFICATION_EVENT_TYPES = frozenset(
    {
        "circulation.loan_requested",
        "circulation.loan_approved",
        "circulation.loan_rejected",
        "circulation.loan_checked_out",
        "circulation.loan_returned",
        "circulation.loan_overdue",
        "circulation.reservation_created",
        "circulation.reservation_allocated",
        "circulation.reservation_cancelled",
        "circulation.reservation_claimed",
        "circulation.reservation_expired",
        "public_library.payment_recorded",
        "public_library.payment_status_changed",
        "public_library.payment_reconciled",
        "public_library.payment_webhook_processed",
    }
)


class NotificationConsumer:
    """Consumes domain events from outbox dispatcher and persists notifications."""

    _JOB_TYPE = "core.notifications"
    _MAX_PAYLOAD_VERSION = 1

    def __init__(
        self,
        *,
        store: NotificationStore,
        deduplication_port: ConsumerDeduplicationPort | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._deduplication_port = deduplication_port
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def handle_event(self, connection: Connection, event: ClaimedOutboxEvent) -> None:
        """Handle one claimed outbox event idempotently inside tenant transaction."""
        org_id = event.organization_id

        if event.payload_version > self._MAX_PAYLOAD_VERSION:
            raise ValueError(
                f"Unsupported payload version {event.payload_version} for event {event.event_type}"
            )

        # 1. Deduplication check via BE-015 dispatcher port
        if self._deduplication_port is not None:
            if self._deduplication_port.is_processed(
                connection,
                organization_id=org_id,
                outbox_event_id=event.event_id,
                job_type=self._JOB_TYPE,
            ):
                return

        # 2. Parse event payload
        payload: dict[str, Any] = {}
        if hasattr(event, "payload_json") and getattr(event, "payload_json"):
            try:
                payload = json.loads(getattr(event, "payload_json"))
            except Exception:
                payload = {}
        elif hasattr(event, "payload") and isinstance(getattr(event, "payload"), dict):
            payload = getattr(event, "payload")

        # 3. Resolve target user_id
        target_user_id = self._resolve_target_user(
            connection, org_id, event.event_type, payload
        )
        if target_user_id is None:
            _LOGGER.warning(
                "Could not resolve recipient user_id for event %s (type=%s, org=%s)",
                event.event_id,
                event.event_type,
                org_id,
            )
            return

        # 4. Sanitize payload (exclude secrets and credentials)
        sanitized_payload = sanitize_notification_payload(payload)

        # 5. Build and persist notification
        now = self._clock()
        notification = Notification(
            notification_id=uuid4(),
            organization_id=org_id,
            user_id=target_user_id,
            type=event.event_type,
            payload=sanitized_payload,
            channel=NotificationChannel.IN_APP,
            status=NotificationStatus.UNREAD,
            read_at=None,
            created_at=now,
            outbox_event_id=event.event_id,
        )

        self._store.create_notification_in_connection(
            connection,
            notification,
            outbox_event_id=event.event_id,
        )

        # 6. Record processed status in deduplication port
        if self._deduplication_port is not None:
            self._deduplication_port.record_processed(
                connection,
                organization_id=org_id,
                outbox_event_id=event.event_id,
                job_type=self._JOB_TYPE,
                payload_version=event.payload_version,
            )

    def _resolve_target_user(
        self,
        connection: Connection,
        organization_id: UUID,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> UUID | None:
        """Extract or look up the recipient user_id for this domain event."""
        # Direct user identification in payload
        for direct_field in ("borrower_user_id", "requester_user_id", "user_id"):
            val = payload.get(direct_field)
            if val:
                try:
                    return UUID(str(val))
                except ValueError:
                    pass

        # Lookup from loan if loan_id present
        raw_loan_id = payload.get("loan_id")
        if raw_loan_id:
            try:
                loan_uuid = UUID(str(raw_loan_id))
                row = connection.execute(
                    text(
                        "SELECT borrower_user_id FROM core.loans "
                        "WHERE organization_id = :org_id AND loan_id = :loan_id"
                    ),
                    {"org_id": str(organization_id), "loan_id": str(loan_uuid)},
                ).fetchone()
                if row and row.borrower_user_id:
                    return UUID(str(row.borrower_user_id))
            except Exception:
                pass

        # Lookup from reservation if reservation_id present
        raw_res_id = payload.get("reservation_id")
        if raw_res_id:
            try:
                res_uuid = UUID(str(raw_res_id))
                row = connection.execute(
                    text(
                        "SELECT requester_user_id FROM core.reservations "
                        "WHERE organization_id = :org_id AND reservation_id = :res_id"
                    ),
                    {"org_id": str(organization_id), "res_id": str(res_uuid)},
                ).fetchone()
                if row and row.requester_user_id:
                    return UUID(str(row.requester_user_id))
            except Exception:
                pass

        # Lookup from payment or member if present
        raw_member_id = payload.get("member_id")
        if raw_member_id:
            try:
                member_uuid = UUID(str(raw_member_id))
                row = connection.execute(
                    text(
                        "SELECT user_id FROM public_library.members "
                        "WHERE organization_id = :org_id AND member_id = :member_id"
                    ),
                    {"org_id": str(organization_id), "member_id": str(member_uuid)},
                ).fetchone()
                if row and row.user_id:
                    return UUID(str(row.user_id))
            except Exception:
                pass

        raw_payment_id = payload.get("payment_id")
        if raw_payment_id:
            try:
                payment_uuid = UUID(str(raw_payment_id))
                row = connection.execute(
                    text(
                        "SELECT m.user_id FROM public_library.payments p "
                        "JOIN public_library.members m ON m.organization_id = p.organization_id "
                        "AND m.member_id = p.member_id "
                        "WHERE p.organization_id = :org_id AND p.payment_id = :payment_id"
                    ),
                    {"org_id": str(organization_id), "payment_id": str(payment_uuid)},
                ).fetchone()
                if row and row.user_id:
                    return UUID(str(row.user_id))
            except Exception:
                pass

        return None


def register_notification_consumers(
    dispatcher: OutboxDispatcherService,
    consumer: NotificationConsumer,
    *,
    event_types: frozenset[str] = SUPPORTED_NOTIFICATION_EVENT_TYPES,
) -> None:
    """Register consumer handler on dispatcher for all supported notification domain event types."""
    for event_type in event_types:
        dispatcher.register_handler(
            event_type,
            consumer.handle_event,
            max_payload_version=1,
        )
