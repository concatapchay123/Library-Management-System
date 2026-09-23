"""Application service and ports for outbox event dispatching and deduplication."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import logging
import re
from typing import Protocol, TypeVar
from uuid import UUID, uuid4

from sqlalchemy.engine import Connection

from openlibrary.modules.core.infrastructure.tenancy import SqlServerTenantContext
from openlibrary.modules.ops.application.persistence import (
    ClaimedOutboxEvent,
    JobRecord,
)


T = TypeVar("T")
ConsumerHandler = Callable[[Connection, ClaimedOutboxEvent], None]

_SENSITIVE_PATTERN = re.compile(
    r"(password|token|secret|credential|api[_-]?key|card[_-]?number)\s*[=:]\s*\S+",
    re.IGNORECASE,
)
_LOGGER = logging.getLogger(__name__)


def sanitize_error_message(error: str, *, max_length: int = 1000) -> str:
    """Sanitize and truncate error messages before persistent storage."""
    cleaned = _SENSITIVE_PATTERN.sub(r"\1=[REDACTED]", error.strip())
    if len(cleaned) > max_length:
        return cleaned[: max_length - 3] + "..."
    return cleaned


class OutboxClaimStore(Protocol):
    """Port for pre-context outbox event claiming and status tracking."""

    def claim_next_event(
        self,
        *,
        lease_token: UUID,
        lease_duration_seconds: int = 30,
    ) -> ClaimedOutboxEvent | None:
        """Atomically claim one available event across tenants using stored procedure."""
        ...

    def mark_delivered(
        self,
        *,
        event_id: UUID,
        lease_token: UUID,
        organization_id: UUID | None = None,
    ) -> bool:
        """Mark event delivered and clear lease."""
        ...

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
        """Record bounded retry delay or dead-letter state."""
        ...


class ConsumerDeduplicationPort(Protocol):
    """Port for checking and recording idempotent consumer processing."""

    def is_processed(
        self,
        connection: Connection,
        *,
        organization_id: UUID,
        outbox_event_id: UUID,
        job_type: str,
        deduplication_key: str | None = None,
    ) -> bool:
        """Return True if this job has already completed."""
        ...

    def record_processed(
        self,
        connection: Connection,
        *,
        organization_id: UUID,
        outbox_event_id: UUID,
        job_type: str,
        payload_version: int,
        deduplication_key: str | None = None,
    ) -> JobRecord:
        """Record consumer completion in the tenant's transaction."""
        ...

    def record_job_status(
        self,
        connection: Connection,
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
        """Update or insert a job record tracking event dispatch status."""
        ...


class OutboxDispatcherService:
    """Coordinates claiming durable outbox events and safe consumer processing."""

    def __init__(
        self,
        *,
        claim_store: OutboxClaimStore,
        deduplication_port: ConsumerDeduplicationPort,
        tenant_context: SqlServerTenantContext,
        lease_duration_seconds: int = 30,
        max_retries: int = 5,
        base_backoff_seconds: int = 1,
        max_backoff_seconds: int = 3600,
    ) -> None:
        self._claim_store = claim_store
        self._deduplication_port = deduplication_port
        self._tenant_context = tenant_context
        self._lease_duration_seconds = lease_duration_seconds
        self._max_retries = max_retries
        self._base_backoff_seconds = base_backoff_seconds
        self._max_backoff_seconds = max_backoff_seconds
        self._handlers: dict[str, tuple[ConsumerHandler, int]] = {}

    def register_handler(
        self,
        event_type: str,
        handler: ConsumerHandler,
        *,
        max_payload_version: int = 1,
    ) -> None:
        """Register a consumer callback for a specific outbox event type."""
        self._handlers[event_type] = (handler, max_payload_version)

    def dispatch_one(self) -> bool:
        """Claim and dispatch at most one event. Returns True if an event was claimed."""
        lease_token = uuid4()
        event = self._claim_store.claim_next_event(
            lease_token=lease_token,
            lease_duration_seconds=self._lease_duration_seconds,
        )
        if event is None:
            return False

        handler_info = self._handlers.get(event.event_type)
        if handler_info is None:
            error_msg = f"No handler registered for event type: {event.event_type}"
            self._handle_failure(
                event=event,
                lease_token=lease_token,
                error=RuntimeError(error_msg),
                is_permanent=True,
            )
            return True

        handler, max_payload_version = handler_info
        if event.payload_version > max_payload_version:
            error_msg = (
                f"Unsupported payload version {event.payload_version} "
                f"(max supported: {max_payload_version}) for event {event.event_type}"
            )
            self._handle_failure(
                event=event,
                lease_token=lease_token,
                error=ValueError(error_msg),
                is_permanent=True,
            )
            return True

        try:
            with self._tenant_context.connection(event.organization_id) as connection:
                handler(connection, event)
                connection.commit()

            self._claim_store.mark_delivered(
                event_id=event.event_id,
                lease_token=lease_token,
                organization_id=event.organization_id,
            )

            try:
                with self._tenant_context.connection(
                    event.organization_id
                ) as connection:
                    self._deduplication_port.record_job_status(
                        connection,
                        organization_id=event.organization_id,
                        outbox_event_id=event.event_id,
                        job_type=event.event_type,
                        payload_version=event.payload_version,
                        status="completed",
                        attempts=event.attempts,
                    )
                    connection.commit()
            except Exception as exc:
                _LOGGER.warning(
                    "Failed to record completed job status for event %s: %s",
                    event.event_id,
                    exc,
                )

            return True

        except Exception as error:
            self._handle_failure(
                event=event,
                lease_token=lease_token,
                error=error,
                is_permanent=False,
            )
            return True

    def _handle_failure(
        self,
        *,
        event: ClaimedOutboxEvent,
        lease_token: UUID,
        error: Exception,
        is_permanent: bool,
    ) -> None:
        sanitized_error = sanitize_error_message(str(error))
        is_dead_letter = is_permanent or (event.attempts >= self._max_retries)
        retry_delay = 0
        if not is_dead_letter:
            if self._base_backoff_seconds <= 0:
                retry_delay = 0
            else:
                retry_delay = min(
                    self._base_backoff_seconds * (2 ** (event.attempts - 1)),
                    self._max_backoff_seconds,
                )

        self._claim_store.record_failure(
            event_id=event.event_id,
            lease_token=lease_token,
            error_message=sanitized_error,
            retry_delay_seconds=retry_delay,
            is_dead_letter=is_dead_letter,
            organization_id=event.organization_id,
        )

        try:
            with self._tenant_context.connection(event.organization_id) as connection:
                status = "dead_letter" if is_dead_letter else "failed"
                self._deduplication_port.record_job_status(
                    connection,
                    organization_id=event.organization_id,
                    outbox_event_id=event.event_id,
                    job_type=event.event_type,
                    payload_version=event.payload_version,
                    status=status,
                    attempts=event.attempts,
                    last_error=sanitized_error,
                )
                connection.commit()
        except Exception as exc:
            _LOGGER.warning(
                "Failed to record failure job status for event %s: %s",
                event.event_id,
                exc,
            )
