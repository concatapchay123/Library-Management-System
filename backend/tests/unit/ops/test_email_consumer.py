"""Unit tests for BE-026 email delivery consumer, sink, metrics, and worker lifecycle."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

from openlibrary.modules.ops.application.email import (
    DevelopmentEmailSink,
    EmailDeliveryError,
    EmailMessage,
)
from openlibrary.modules.ops.application.email_consumer import (
    EmailDeliveryConsumer,
    format_notification_email,
)
from openlibrary.modules.ops.application.metrics import (
    QueueMetrics,
)
from openlibrary.modules.ops.application.persistence import ClaimedOutboxEvent
from openlibrary.modules.ops.application.worker_lifecycle import (
    WorkerHealthService,
    WorkerHealthStatus,
    WorkerReconnectPolicy,
)


class InMemoryDeduplicationStore:
    def __init__(self) -> None:
        self.processed: set[tuple[UUID, UUID, str]] = set()

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


class MockConnection:
    """Mock connection that simulates SQL queries for user email lookup."""

    def __init__(self, user_emails: dict[tuple[UUID, UUID], str] | None = None) -> None:
        self.user_emails = user_emails or {}
        self.executed_queries: list[tuple[str, dict[str, Any]]] = []

    def execute(self, statement: Any, params: dict[str, Any] | None = None) -> Any:
        sql = str(statement)
        p = params or {}
        self.executed_queries.append((sql, p))

        # Check for core.users email lookup query
        if "FROM core.users" in sql:
            org_id = UUID(str(p.get("org_id")))
            user_id = UUID(str(p.get("user_id")))
            email = self.user_emails.get((org_id, user_id))
            mock_result = MagicMock()
            if email:
                mock_row = MagicMock()
                mock_row.email = email
                mock_result.fetchone.return_value = mock_row
            else:
                mock_result.fetchone.return_value = None
            return mock_result

        # Fallback empty query result
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        return mock_result


def _make_event(
    *,
    organization_id: UUID,
    event_type: str,
    payload: dict[str, Any],
    event_id: UUID | None = None,
    payload_version: int = 1,
) -> ClaimedOutboxEvent:
    ev_id = event_id or uuid4()
    now = datetime.now(timezone.utc)
    return ClaimedOutboxEvent(
        event_id=ev_id,
        organization_id=organization_id,
        event_type=event_type,
        aggregate_type="loan",
        aggregate_id=uuid4(),
        payload_version=payload_version,
        payload_json=json.dumps(payload),
        correlation_id=uuid4(),
        idempotency_key=f"idemp-{ev_id}",
        attempts=1,
        lease_token=uuid4(),
        lease_expires_at=now,
        created_at=now,
    )


def test_email_message_immutability_and_slots() -> None:
    message = EmailMessage(
        to_address="reader@example.com",
        subject="Welcome",
        body_text="Welcome to OpenLibraryOS",
    )
    assert message.to_address == "reader@example.com"
    assert message.subject == "Welcome"
    assert message.body_text == "Welcome to OpenLibraryOS"
    assert message.body_html is None
    with pytest.raises(Exception):
        message.to_address = "other@example.com"  # type: ignore[misc]


def test_development_sink_operations() -> None:
    sink = DevelopmentEmailSink()
    assert sink.get_deliveries() == []

    m1 = EmailMessage(to_address="a@example.com", subject="S1", body_text="B1")
    m2 = EmailMessage(to_address="b@example.com", subject="S2", body_text="B2")
    m3 = EmailMessage(to_address="a@example.com", subject="S3", body_text="B3")

    sink.send(m1)
    sink.send(m2)
    sink.send(m3)

    assert len(sink.get_deliveries()) == 3
    assert len(sink.get_deliveries_for("a@example.com")) == 2
    assert len(sink.get_deliveries_for("b@example.com")) == 1

    sink.clear()
    assert len(sink.get_deliveries()) == 0


def test_consumer_rejects_unsupported_payload_version() -> None:
    sink = DevelopmentEmailSink()
    consumer = EmailDeliveryConsumer(email_port=sink)
    event = _make_event(
        organization_id=uuid4(),
        event_type="circulation.loan_approved",
        payload={},
        payload_version=2,
    )
    conn = MockConnection()
    with pytest.raises(ValueError, match="Unsupported payload version"):
        consumer.handle_event(conn, event)  # type: ignore[arg-type]


def test_consumer_deduplication_skips_processed_event() -> None:
    org_id = uuid4()
    ev_id = uuid4()
    sink = DevelopmentEmailSink()
    dedup = InMemoryDeduplicationStore()
    # Mark as already processed
    dedup.processed.add((org_id, ev_id, "ops.email_delivery"))

    consumer = EmailDeliveryConsumer(email_port=sink, deduplication_port=dedup)
    event = _make_event(
        event_id=ev_id,
        organization_id=org_id,
        event_type="circulation.loan_approved",
        payload={"recipient_email": "reader@example.com"},
    )
    conn = MockConnection()
    consumer.handle_event(conn, event)  # type: ignore[arg-type]

    # No email sent because it was already processed
    assert len(sink.get_deliveries()) == 0


def test_consumer_resolves_email_from_core_users() -> None:
    org_id = uuid4()
    user_id = uuid4()
    sink = DevelopmentEmailSink()
    dedup = InMemoryDeduplicationStore()
    consumer = EmailDeliveryConsumer(email_port=sink, deduplication_port=dedup)

    event = _make_event(
        organization_id=org_id,
        event_type="circulation.loan_approved",
        payload={
            "loan_id": str(uuid4()),
            "borrower_user_id": str(user_id),
            "book_title": "Effective Python",
        },
    )

    conn = MockConnection(user_emails={(org_id, user_id): "scholar@university.edu"})
    consumer.handle_event(conn, event)  # type: ignore[arg-type]

    assert len(sink.get_deliveries()) == 1
    email = sink.get_deliveries()[0]
    assert email.to_address == "scholar@university.edu"
    assert "Loan Approved" in email.subject
    assert "Effective Python" in email.body_text
    assert (org_id, event.event_id, "ops.email_delivery") in dedup.processed


def test_consumer_skips_when_user_or_email_unresolvable() -> None:
    org_id = uuid4()
    sink = DevelopmentEmailSink()
    dedup = InMemoryDeduplicationStore()
    consumer = EmailDeliveryConsumer(email_port=sink, deduplication_port=dedup)

    event = _make_event(
        organization_id=org_id,
        event_type="circulation.loan_approved",
        payload={"unknown_field": "some_value"},
    )
    conn = MockConnection()  # No email resolved
    consumer.handle_event(conn, event)  # type: ignore[arg-type]

    assert len(sink.get_deliveries()) == 0


def test_consumer_propagates_email_delivery_failure() -> None:
    org_id = uuid4()
    user_id = uuid4()
    sink = DevelopmentEmailSink()
    sink.simulate_failure(count=1, error=EmailDeliveryError("SMTP connection dropped"))
    dedup = InMemoryDeduplicationStore()
    consumer = EmailDeliveryConsumer(email_port=sink, deduplication_port=dedup)

    event = _make_event(
        organization_id=org_id,
        event_type="circulation.loan_approved",
        payload={
            "recipient_email": "reader@example.com",
            "borrower_user_id": str(user_id),
        },
    )
    conn = MockConnection()

    with pytest.raises(EmailDeliveryError, match="SMTP connection dropped"):
        consumer.handle_event(conn, event)  # type: ignore[arg-type]

    # Deduplication was NOT recorded because delivery failed
    assert (org_id, event.event_id, "ops.email_delivery") not in dedup.processed


def test_format_notification_email_scrubs_secrets() -> None:
    payload = {
        "book_title": "Site Reliability Engineering",
        "password": "plain_password_123",
        "api_key": "secret_key_abc",
        "card_number": "1234567812345678",
        "amount": "25.00",
    }
    subject, body = format_notification_email("circulation.loan_overdue", payload)
    assert "Overdue" in subject
    assert "Site Reliability Engineering" in body
    assert "plain_password_123" not in body
    assert "secret_key_abc" not in body
    assert "1234567812345678" not in body


def test_worker_health_service_evaluation() -> None:
    mock_metrics_store = MagicMock()
    mock_metrics = QueueMetrics(
        pending_count=5,
        in_flight_count=1,
        dead_letter_count=0,
        delivered_count=100,
        failed_jobs_count=0,
    )
    mock_metrics_store.get_queue_metrics.return_value = mock_metrics

    health_service = WorkerHealthService(
        database_url="mssql+pyodbc://mock",
        redis_url="redis://localhost:6379/0",
        metrics_store=mock_metrics_store,
        database_probe=lambda: True,
        broker_probe=lambda: True,
    )

    status = health_service.check_health()
    assert status.status == "ok"
    assert status.database_connected is True
    assert status.broker_connected is True
    assert status.queue_metrics.pending_count == 5

    # If broker fails -> degraded or unavailable
    health_service._broker_probe = lambda: False
    degraded_status = health_service.check_health()
    assert degraded_status.status == "unavailable"
    assert degraded_status.broker_connected is False


def test_worker_health_status_serialization() -> None:
    metrics = QueueMetrics(
        pending_count=2,
        in_flight_count=0,
        dead_letter_count=1,
        delivered_count=50,
        failed_jobs_count=1,
    )
    health = WorkerHealthStatus(
        status="degraded",
        database_connected=True,
        broker_connected=True,
        queue_metrics=metrics,
        uptime_seconds=3600.0,
    )
    d = health.to_dict()
    assert d["status"] == "degraded"
    assert d["database_connected"] is True
    assert d["queue_metrics"]["dead_letter_count"] == 1
    assert d["uptime_seconds"] == 3600.0


def test_reconnect_policy_exhaustion() -> None:
    reconnect = WorkerReconnectPolicy(max_attempts=2, base_delay_seconds=0.01)

    def always_fail() -> None:
        raise ConnectionRefusedError("Database host down")

    with pytest.raises(ConnectionRefusedError, match="Database host down"):
        reconnect.execute_with_retry(always_fail)
