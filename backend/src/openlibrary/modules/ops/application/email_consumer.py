"""Email delivery consumer for durable domain events with deduplication and bounded retry."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
import json
import logging
import re
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from openlibrary.modules.ops.application.dispatcher import (
    ConsumerDeduplicationPort,
    OutboxDispatcherService,
)
from openlibrary.modules.ops.application.email import (
    EmailDeliveryError,
    EmailMessage,
    EmailPort,
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


def _sanitize_dict(data: Mapping[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in data.items():
        if not isinstance(key, str):
            continue
        normalized = _SENSITIVE_KEY.sub("", key.casefold())
        if (
            normalized in _SENSITIVE_NAMES
            or normalized.endswith("token")
            or "secret" in normalized
            or "password" in normalized
            or "credential" in normalized
        ):
            continue
        if isinstance(value, Mapping):
            cleaned[key] = _sanitize_dict(value)
        elif isinstance(value, (list, tuple)):
            cleaned[key] = [
                _sanitize_dict(item) if isinstance(item, Mapping) else item
                for item in value
            ]
        else:
            cleaned[key] = value
    return cleaned


SUPPORTED_EMAIL_EVENT_TYPES = frozenset(
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

_SUBJECT_TEMPLATES: dict[str, str] = {
    "circulation.loan_requested": "[OpenLibraryOS] Loan Requested",
    "circulation.loan_approved": "[OpenLibraryOS] Loan Approved",
    "circulation.loan_rejected": "[OpenLibraryOS] Loan Request Rejected",
    "circulation.loan_checked_out": "[OpenLibraryOS] Book Checked Out",
    "circulation.loan_returned": "[OpenLibraryOS] Book Returned Successfully",
    "circulation.loan_overdue": "[OpenLibraryOS] Overdue Notice: Please Return Book",
    "circulation.reservation_created": "[OpenLibraryOS] Reservation Confirmed",
    "circulation.reservation_allocated": "[OpenLibraryOS] Reservation Ready for Pickup",
    "circulation.reservation_cancelled": "[OpenLibraryOS] Reservation Cancelled",
    "circulation.reservation_claimed": "[OpenLibraryOS] Reservation Claimed",
    "circulation.reservation_expired": "[OpenLibraryOS] Reservation Expired",
    "public_library.payment_recorded": "[OpenLibraryOS] Payment Receipt",
    "public_library.payment_status_changed": "[OpenLibraryOS] Payment Status Update",
    "public_library.payment_reconciled": "[OpenLibraryOS] Payment Reconciled",
    "public_library.payment_webhook_processed": "[OpenLibraryOS] Payment Processed",
}


def format_notification_email(
    event_type: str, payload: Mapping[str, Any]
) -> tuple[str, str]:
    """Format human-readable subject and scrubbed body text for an event."""
    sanitized = _sanitize_dict(payload)
    subject = _SUBJECT_TEMPLATES.get(
        event_type, f"[OpenLibraryOS] Notification: {event_type}"
    )

    lines = [f"Notification event: {event_type}"]
    title = sanitized.get("book_title")
    if title:
        lines.append(f"Title: {title}")

    loan_id = sanitized.get("loan_id")
    if loan_id:
        lines.append(f"Loan ID: {loan_id}")

    res_id = sanitized.get("reservation_id")
    if res_id:
        lines.append(f"Reservation ID: {res_id}")

    due_date = sanitized.get("due_date")
    if due_date:
        lines.append(f"Due date: {due_date}")

    hold_expires = sanitized.get("hold_expires_at")
    if hold_expires:
        lines.append(f"Hold expires at: {hold_expires}")

    amount = sanitized.get("amount")
    currency = sanitized.get("currency", "USD")
    if amount is not None:
        lines.append(f"Amount: {amount} {currency}")

    # Add other non-sensitive key-values
    known = {
        "book_title",
        "loan_id",
        "reservation_id",
        "due_date",
        "hold_expires_at",
        "amount",
        "currency",
    }
    for k, v in sanitized.items():
        if k not in known and not isinstance(v, (dict, list)):
            lines.append(f"{k}: {v}")

    lines.append("\nThank you for using OpenLibraryOS.")
    body_text = "\n".join(lines)
    return subject, body_text


class EmailDeliveryConsumer:
    """Consumes durable outbox events and dispatches notification emails idempotently."""

    _JOB_TYPE = "ops.email_delivery"
    _MAX_PAYLOAD_VERSION = 1

    def __init__(
        self,
        *,
        email_port: EmailPort,
        deduplication_port: ConsumerDeduplicationPort | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._email_port = email_port
        self._deduplication_port = deduplication_port
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def handle_event(self, connection: Connection, event: ClaimedOutboxEvent) -> None:
        """Handle one claimed outbox event and deliver email idempotently."""
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
                _LOGGER.info(
                    "Event %s already processed for %s; skipping email delivery.",
                    event.event_id,
                    self._JOB_TYPE,
                )
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

        # 3. Resolve recipient email address
        recipient_email = self._resolve_recipient_email(
            connection, org_id, event.event_type, payload
        )
        if not recipient_email:
            _LOGGER.warning(
                "Could not resolve recipient email for event %s (type=%s, org=%s)",
                event.event_id,
                event.event_type,
                org_id,
            )
            # Record processed so missing recipient doesn't cause an infinite retry loop
            if self._deduplication_port is not None:
                self._deduplication_port.record_processed(
                    connection,
                    organization_id=org_id,
                    outbox_event_id=event.event_id,
                    job_type=self._JOB_TYPE,
                    payload_version=event.payload_version,
                )
            return

        # 4. Format subject and body (sanitizing credentials)
        subject, body_text = format_notification_email(event.event_type, payload)

        # 5. Build and send email message
        message = EmailMessage(
            to_address=recipient_email,
            subject=subject,
            body_text=body_text,
            organization_id=org_id,
            event_id=event.event_id,
        )

        delivery_result = self._email_port.send(message)
        if not delivery_result.success:
            err_msg = delivery_result.error_message or "Email provider delivery failed"
            raise EmailDeliveryError(err_msg)

        # 6. Record processed status in deduplication port
        if self._deduplication_port is not None:
            self._deduplication_port.record_processed(
                connection,
                organization_id=org_id,
                outbox_event_id=event.event_id,
                job_type=self._JOB_TYPE,
                payload_version=event.payload_version,
            )

    def _resolve_recipient_email(
        self,
        connection: Connection,
        organization_id: UUID,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> str | None:
        """Resolve the target email address from payload or core.users table."""
        # Direct email in payload
        for direct_field in (
            "recipient_email",
            "email",
            "borrower_email",
            "requester_email",
        ):
            val = payload.get(direct_field)
            if val and isinstance(val, str) and "@" in val:
                return str(val).strip()

        # Try to resolve user_id
        user_id = self._resolve_user_id(connection, organization_id, payload)
        if user_id is None:
            return None

        # Look up email in core.users
        try:
            row = connection.execute(
                text(
                    "SELECT email FROM core.users "
                    "WHERE organization_id = :org_id AND user_id = :user_id"
                ),
                {"org_id": str(organization_id), "user_id": str(user_id)},
            ).fetchone()
            if row and row.email:
                return str(row.email).strip()
        except Exception as exc:
            _LOGGER.warning("Error looking up user email for user %s: %s", user_id, exc)

        return None

    def _resolve_user_id(
        self,
        connection: Connection,
        organization_id: UUID,
        payload: Mapping[str, Any],
    ) -> UUID | None:
        """Extract user_id directly or via domain relationship tables."""
        for field in ("borrower_user_id", "requester_user_id", "user_id"):
            val = payload.get(field)
            if val:
                try:
                    return UUID(str(val))
                except ValueError:
                    pass

        # Loan lookup
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

        # Reservation lookup
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

        # Public library member / payment lookup
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


def register_email_consumers(
    dispatcher: OutboxDispatcherService,
    consumer: EmailDeliveryConsumer,
    *,
    event_types: frozenset[str] = SUPPORTED_EMAIL_EVENT_TYPES,
) -> None:
    """Register email delivery handler on dispatcher for all supported domain events."""
    for event_type in event_types:
        dispatcher.register_handler(
            event_type,
            consumer.handle_event,
            max_payload_version=1,
        )
