"""Application service, evaluator, and scheduled dispatcher jobs for overdue loans and hold expiry."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime, timezone
import json
import logging
from typing import Any, Final
from uuid import UUID, uuid4

from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.loans import Loan, LoanStore
from openlibrary.modules.core.application.reservations import ReservationService
from openlibrary.modules.core.domain.loans import LoanStatus, validate_loan_transition
from openlibrary.modules.ops.application.dispatcher import (
    ConsumerDeduplicationPort,
    OutboxDispatcherService,
)
from openlibrary.modules.ops.application.persistence import (
    AuditEvent,
    AuditedTransaction,
    ClaimedOutboxEvent,
    OutboxEvent,
    serialize_event_payload,
)

_LOGGER = logging.getLogger(__name__)

CIRCULATION_SCHEDULED_OVERDUE_EVENT: Final[str] = (
    "circulation.scheduled_overdue_evaluation"
)
CIRCULATION_SCHEDULED_HOLD_EXPIRY_EVENT: Final[str] = (
    "circulation.scheduled_hold_expiry"
)
CIRCULATION_LOAN_OVERDUE_EVENT: Final[str] = "circulation.loan_overdue"


class OverdueEvaluator:
    """Evaluates active checked-out loans against stored due dates and transitions them to overdue."""

    def __init__(
        self,
        *,
        loan_store: LoanStore,
        transaction: AuditedTransaction | None = None,
        connection_provider: Callable[[UUID], AbstractContextManager[object]]
        | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._loan_store = loan_store
        self._transaction = transaction
        self._connection_provider = connection_provider
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def evaluate_overdue_loans(
        self,
        *,
        organization_id: UUID,
        as_of: datetime | None = None,
        correlation_id: UUID | None = None,
    ) -> list[Loan]:
        """Evaluate and transition overdue loans for an organization."""
        if self._connection_provider is not None:
            with self._connection_provider(organization_id) as conn:
                return self.evaluate_overdue_loans_in_connection(
                    conn,
                    organization_id=organization_id,
                    as_of=as_of,
                    correlation_id=correlation_id,
                )
        return self.evaluate_overdue_loans_in_connection(
            None,
            organization_id=organization_id,
            as_of=as_of,
            correlation_id=correlation_id,
        )

    def evaluate_overdue_loans_in_connection(
        self,
        connection: object,
        *,
        organization_id: UUID,
        as_of: datetime | None = None,
        correlation_id: UUID | None = None,
    ) -> list[Loan]:
        """Atomically find due loans, mark overdue, and emit outbox and audit events."""
        effective_now = as_of or self._clock()

        if (
            hasattr(self._loan_store, "find_overdue_loans_in_connection")
            and connection is not None
        ):
            due_loans = getattr(self._loan_store, "find_overdue_loans_in_connection")(
                connection, organization_id, effective_now
            )
        else:
            due_loans = self._loan_store.find_overdue_loans(
                organization_id, effective_now
            )

        if not due_loans:
            return []

        transitioned_loans: list[Loan] = []
        for current_loan in due_loans:
            validate_loan_transition(current_loan.status, LoanStatus.OVERDUE)

            updated = Loan(
                loan_id=current_loan.loan_id,
                organization_id=current_loan.organization_id,
                copy_id=current_loan.copy_id,
                borrower_user_id=current_loan.borrower_user_id,
                status=LoanStatus.OVERDUE,
                loan_status=LoanStatus.OVERDUE,
                request_status=current_loan.request_status,
                requested_at=current_loan.requested_at,
                approved_at=current_loan.approved_at,
                checked_out_at=current_loan.checked_out_at,
                due_at=current_loan.due_at,
                returned_at=current_loan.returned_at,
                policy_snapshot=current_loan.policy_snapshot,
                created_at=current_loan.created_at,
                updated_at=effective_now,
            )

            audit_corr = correlation_id or uuid4()
            audit_event = AuditEvent(
                action="loan.marked_overdue",
                entity_type="loan",
                entity_id=current_loan.loan_id,
                payload={
                    "loan_id": str(current_loan.loan_id),
                    "copy_id": str(current_loan.copy_id),
                    "borrower_user_id": str(current_loan.borrower_user_id),
                    "due_at": current_loan.due_at.isoformat()
                    if current_loan.due_at
                    else None,
                    "status": LoanStatus.OVERDUE,
                },
                correlation_id=audit_corr,
                actor_user_id=None,
                actor_type="system",
            )
            outbox_event = OutboxEvent(
                event_type=CIRCULATION_LOAN_OVERDUE_EVENT,
                aggregate_type="loan",
                aggregate_id=current_loan.loan_id,
                payload_version=1,
                payload={
                    "loan_id": str(current_loan.loan_id),
                    "organization_id": str(organization_id),
                    "copy_id": str(current_loan.copy_id),
                    "borrower_user_id": str(current_loan.borrower_user_id),
                    "due_at": current_loan.due_at.isoformat()
                    if current_loan.due_at
                    else None,
                },
                correlation_id=audit_corr,
                idempotency_key=f"loan:{current_loan.loan_id}:overdue",
            )

            def _mutation(conn: object) -> Loan:
                if hasattr(self._loan_store, "record_update_loan_in_connection"):
                    return getattr(  # type: ignore[no-any-return]
                        self._loan_store, "record_update_loan_in_connection"
                    )(conn, updated)
                return self._loan_store.update_loan(updated)

            if self._transaction is not None:
                persisted = self._transaction.run(
                    connection,  # type: ignore[arg-type]
                    _mutation,
                    audit_event,
                    (outbox_event,),
                )
            else:
                persisted = _mutation(connection)

            transitioned_loans.append(persisted)

        return transitioned_loans


def handle_scheduled_overdue_evaluation(
    connection: Any,
    event: ClaimedOutboxEvent,
    *,
    evaluator: OverdueEvaluator,
    deduplication_port: ConsumerDeduplicationPort | None = None,
    clock: Callable[[], datetime] | None = None,
) -> None:
    """Consumer handler for scheduled overdue evaluation work."""
    org_id = event.organization_id
    job_type = CIRCULATION_SCHEDULED_OVERDUE_EVENT

    if deduplication_port is not None:
        if deduplication_port.is_processed(
            connection,
            organization_id=org_id,
            outbox_event_id=event.event_id,
            job_type=job_type,
        ):
            return

    payload: dict[str, Any] = {}
    if hasattr(event, "payload_json") and getattr(event, "payload_json"):
        try:
            payload = json.loads(getattr(event, "payload_json"))
        except (ValueError, TypeError, json.JSONDecodeError):
            payload = {}
    elif hasattr(event, "payload") and isinstance(getattr(event, "payload"), dict):
        payload = getattr(event, "payload")

    as_of: datetime | None = None
    if payload.get("as_of"):
        try:
            as_of = datetime.fromisoformat(str(payload["as_of"]))
        except (ValueError, TypeError):
            as_of = None

    if as_of is None and clock is not None:
        as_of = clock()

    evaluator.evaluate_overdue_loans_in_connection(
        connection,
        organization_id=org_id,
        as_of=as_of,
        correlation_id=event.correlation_id,
    )

    if deduplication_port is not None:
        deduplication_port.record_processed(
            connection,
            organization_id=org_id,
            outbox_event_id=event.event_id,
            job_type=job_type,
            payload_version=event.payload_version,
        )


def handle_scheduled_hold_expiry(
    connection: Any,
    event: ClaimedOutboxEvent,
    *,
    reservation_service: ReservationService,
    deduplication_port: ConsumerDeduplicationPort | None = None,
    clock: Callable[[], datetime] | None = None,
) -> None:
    """Consumer handler for scheduled reservation hold-expiry sweep."""
    org_id = event.organization_id
    job_type = CIRCULATION_SCHEDULED_HOLD_EXPIRY_EVENT

    if deduplication_port is not None:
        if deduplication_port.is_processed(
            connection,
            organization_id=org_id,
            outbox_event_id=event.event_id,
            job_type=job_type,
        ):
            return

    payload: dict[str, Any] = {}
    if hasattr(event, "payload_json") and getattr(event, "payload_json"):
        try:
            payload = json.loads(getattr(event, "payload_json"))
        except (ValueError, TypeError, json.JSONDecodeError):
            payload = {}
    elif hasattr(event, "payload") and isinstance(getattr(event, "payload"), dict):
        payload = getattr(event, "payload")

    now: datetime | None = None
    if payload.get("now"):
        try:
            now = datetime.fromisoformat(str(payload["now"]))
        except (ValueError, TypeError):
            now = None

    if now is None and clock is not None:
        now = clock()

    system_principal = Principal(
        user_id=uuid4(),
        organization_id=org_id,
        session_id=uuid4(),
    )

    reservation_service.expire_holds(
        actor=system_principal,
        now=now,
        correlation_id=event.correlation_id,
    )

    if deduplication_port is not None:
        deduplication_port.record_processed(
            connection,
            organization_id=org_id,
            outbox_event_id=event.event_id,
            job_type=job_type,
            payload_version=event.payload_version,
        )


def register_circulation_scheduled_jobs(
    dispatcher: OutboxDispatcherService,
    *,
    overdue_evaluator: OverdueEvaluator,
    reservation_service: ReservationService,
    deduplication_port: ConsumerDeduplicationPort | None = None,
    clock: Callable[[], datetime] | None = None,
) -> None:
    """Register circulation scheduled jobs with the generic outbox dispatcher."""

    def _overdue_callback(conn: Any, event: ClaimedOutboxEvent) -> None:
        handle_scheduled_overdue_evaluation(
            conn,
            event,
            evaluator=overdue_evaluator,
            deduplication_port=deduplication_port,
            clock=clock,
        )

    def _hold_expiry_callback(conn: Any, event: ClaimedOutboxEvent) -> None:
        handle_scheduled_hold_expiry(
            conn,
            event,
            reservation_service=reservation_service,
            deduplication_port=deduplication_port,
            clock=clock,
        )

    dispatcher.register_handler(
        CIRCULATION_SCHEDULED_OVERDUE_EVENT,
        _overdue_callback,
        max_payload_version=1,
    )
    dispatcher.register_handler(
        CIRCULATION_SCHEDULED_HOLD_EXPIRY_EVENT,
        _hold_expiry_callback,
        max_payload_version=1,
    )


def enqueue_scheduled_circulation_job(
    connection: Any,
    *,
    organization_id: UUID,
    job_type: str,
    payload: dict[str, Any] | None = None,
    correlation_id: UUID | None = None,
    idempotency_key: str | None = None,
) -> OutboxEvent:
    """Enqueue a durable scheduled circulation job in ops.outbox_events."""
    from sqlalchemy import text

    event_id = uuid4()
    corr_id = correlation_id or uuid4()
    idemp_key = idempotency_key or f"sched:{job_type}:{organization_id}:{event_id.hex}"
    event_payload = payload or {}

    connection.execute(
        text(
            "INSERT INTO ops.outbox_events "
            "(event_id, organization_id, event_type, aggregate_type, aggregate_id, "
            "payload_version, payload_json, correlation_id, idempotency_key) "
            "VALUES (:event_id, :organization_id, :event_type, :aggregate_type, "
            ":aggregate_id, :payload_version, :payload_json, :correlation_id, "
            ":idempotency_key)"
        ),
        {
            "event_id": str(event_id),
            "organization_id": str(organization_id),
            "event_type": job_type,
            "aggregate_type": "circulation",
            "aggregate_id": str(organization_id),
            "payload_version": 1,
            "payload_json": serialize_event_payload(event_payload),
            "correlation_id": str(corr_id),
            "idempotency_key": idemp_key,
        },
    )

    return OutboxEvent(
        event_id=event_id,
        event_type=job_type,
        aggregate_type="circulation",
        aggregate_id=organization_id,
        payload_version=1,
        payload=event_payload,
        correlation_id=corr_id,
        idempotency_key=idemp_key,
    )
