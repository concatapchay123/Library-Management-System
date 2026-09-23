"""Unit tests for the outbox dispatcher service and consumer deduplication logic."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

from openlibrary.modules.ops.application.dispatcher import (
    OutboxDispatcherService,
    sanitize_error_message,
)
from openlibrary.modules.ops.application.persistence import (
    ClaimedOutboxEvent,
    JobRecord,
)


class InMemoryClaimStore:
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


class InMemoryDeduplicationStore:
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
    ) -> JobRecord:
        now = datetime.now(timezone.utc)
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


class FakeTenantContext:
    @contextmanager
    def connection(self, organization_id: UUID) -> Any:
        mock_conn = MagicMock()
        yield mock_conn


def _make_event(
    event_type: str = "book.loaned",
    payload_version: int = 1,
    attempts: int = 0,
) -> ClaimedOutboxEvent:
    now = datetime.now(timezone.utc)
    return ClaimedOutboxEvent(
        event_id=uuid4(),
        organization_id=uuid4(),
        event_type=event_type,
        aggregate_type="loan",
        aggregate_id=uuid4(),
        payload_version=payload_version,
        payload_json='{"loan_id": "test"}',
        correlation_id=uuid4(),
        idempotency_key="key-1",
        attempts=attempts,
        lease_token=uuid4(),
        lease_expires_at=now,
        created_at=now,
    )


def test_sanitize_error_message_redacts_credentials() -> None:
    raw = "Failed with password=super_secret_123 and token: eyJhbGciOi"
    sanitized = sanitize_error_message(raw)
    assert "super_secret_123" not in sanitized
    assert "password=[REDACTED]" in sanitized
    assert "token=[REDACTED]" in sanitized


def test_dispatcher_rejects_unsupported_payload_version() -> None:
    event = _make_event(payload_version=2)
    claim_store = InMemoryClaimStore([event])
    dedup = InMemoryDeduplicationStore()
    context = FakeTenantContext()

    handled = False

    def handler(conn: Any, evt: ClaimedOutboxEvent) -> None:
        nonlocal handled
        handled = True

    dispatcher = OutboxDispatcherService(
        claim_store=claim_store,  # type: ignore[arg-type]
        deduplication_port=dedup,
        tenant_context=context,  # type: ignore[arg-type]
    )
    dispatcher.register_handler("book.loaned", handler, max_payload_version=1)

    assert dispatcher.dispatch_one() is True
    assert not handled
    assert len(claim_store.failures) == 1
    assert claim_store.failures[0]["is_dead_letter"] is True
    assert "Unsupported payload version" in claim_store.failures[0]["error_message"]


def test_dispatcher_bounded_retry_transitions_to_dead_letter() -> None:
    event = _make_event(attempts=2)  # already attempted twice, max_retries=3
    claim_store = InMemoryClaimStore([event])
    dedup = InMemoryDeduplicationStore()
    context = FakeTenantContext()

    def handler(conn: Any, evt: ClaimedOutboxEvent) -> None:
        raise RuntimeError("External service unavailable")

    dispatcher = OutboxDispatcherService(
        claim_store=claim_store,  # type: ignore[arg-type]
        deduplication_port=dedup,
        tenant_context=context,  # type: ignore[arg-type]
        max_retries=3,
    )
    dispatcher.register_handler("book.loaned", handler, max_payload_version=1)

    # Dispatch: attempts becomes 3 -> reaches max_retries -> dead-letter
    assert dispatcher.dispatch_one() is True
    assert len(claim_store.failures) == 1
    failure = claim_store.failures[0]
    assert failure["is_dead_letter"] is True
    assert "External service unavailable" in failure["error_message"]

    # Verify job status recorded as dead-letter
    assert len(dedup.job_statuses) == 1
    assert dedup.job_statuses[0]["status"] == "dead_letter"
    assert dedup.job_statuses[0]["attempts"] == 3


def test_dispatcher_returns_false_when_no_events_available() -> None:
    claim_store = InMemoryClaimStore([])
    dedup = InMemoryDeduplicationStore()
    context = FakeTenantContext()

    dispatcher = OutboxDispatcherService(
        claim_store=claim_store,  # type: ignore[arg-type]
        deduplication_port=dedup,
        tenant_context=context,  # type: ignore[arg-type]
    )
    assert dispatcher.dispatch_one() is False
