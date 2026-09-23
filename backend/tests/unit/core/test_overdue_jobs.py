"""Unit tests for BE-019: overdue calculation, domain transitions, and scheduled circulation jobs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest

from openlibrary.modules.core.application.copy_status import CopyStatusStore
from openlibrary.modules.core.application.inventory import BookCopy
from openlibrary.modules.core.application.loans import Loan, LoanStore
from openlibrary.modules.core.application.overdue import (
    CIRCULATION_SCHEDULED_HOLD_EXPIRY_EVENT,
    CIRCULATION_SCHEDULED_OVERDUE_EVENT,
    OverdueEvaluator,
    register_circulation_scheduled_jobs,
)
from openlibrary.modules.core.application.reservations import (
    Reservation,
    ReservationService,
    ReservationStore,
)
from openlibrary.modules.core.domain.copy_status import CopyStatus
from openlibrary.modules.core.domain.loans import (
    InvalidLoanStatusTransitionError,
    LoanNotFoundError,
    LoanStatus,
    is_allowed_loan_transition,
    validate_loan_transition,
)
from openlibrary.modules.core.domain.reservations import (
    ReservationNotFoundError,
    ReservationStatus,
)
from openlibrary.modules.ops.application.dispatcher import (
    ConsumerDeduplicationPort,
    OutboxDispatcherService,
)
from openlibrary.modules.ops.application.persistence import (
    AuditEvent,
    AuditedTransaction,
    ClaimedOutboxEvent,
    JobRecord,
    OutboxEvent,
)


@dataclass
class _InMemoryLoanStore(LoanStore):
    loans: dict[UUID, Loan] = field(default_factory=dict)

    def create_loan(self, loan: Loan) -> Loan:
        self.loans[loan.loan_id] = loan
        return loan

    def get_loan(self, organization_id: UUID, loan_id: UUID) -> Loan:
        loan = self.loans.get(loan_id)
        if loan is None or loan.organization_id != organization_id:
            raise LoanNotFoundError(loan_id)
        return loan

    def update_loan(self, loan: Loan) -> Loan:
        if (
            loan.loan_id not in self.loans
            or self.loans[loan.loan_id].organization_id != loan.organization_id
        ):
            raise LoanNotFoundError(loan.loan_id)
        self.loans[loan.loan_id] = loan
        return loan

    def list_loans(
        self,
        organization_id: UUID,
        *,
        borrower_user_id: UUID | None = None,
        copy_id: UUID | None = None,
        status: str | None = None,
    ) -> list[Loan]:
        results = [
            loan
            for loan in self.loans.values()
            if loan.organization_id == organization_id
        ]
        if borrower_user_id is not None:
            results = [
                loan_item
                for loan_item in results
                if loan_item.borrower_user_id == borrower_user_id
            ]
        if copy_id is not None:
            results = [
                loan_item for loan_item in results if loan_item.copy_id == copy_id
            ]
        if status is not None:
            results = [loan_item for loan_item in results if loan_item.status == status]
        return sorted(results, key=lambda loan_item: loan_item.created_at, reverse=True)

    def count_active_loans_for_borrower(
        self, organization_id: UUID, borrower_user_id: UUID
    ) -> int:
        return sum(
            1
            for loan_item in self.loans.values()
            if loan_item.organization_id == organization_id
            and loan_item.borrower_user_id == borrower_user_id
            and loan_item.status in (LoanStatus.CHECKED_OUT, LoanStatus.OVERDUE)
        )

    def get_active_loan_for_copy(
        self, organization_id: UUID, copy_id: UUID
    ) -> Loan | None:
        for loan_item in self.loans.values():
            if (
                loan_item.organization_id == organization_id
                and loan_item.copy_id == copy_id
                and loan_item.status in (LoanStatus.CHECKED_OUT, LoanStatus.OVERDUE)
            ):
                return loan_item
        return None

    def find_overdue_loans(self, organization_id: UUID, as_of: datetime) -> list[Loan]:
        return [
            loan
            for loan in self.loans.values()
            if loan.organization_id == organization_id
            and loan.status == LoanStatus.CHECKED_OUT
            and loan.due_at is not None
            and loan.due_at < as_of
        ]

    def record_update_loan_in_connection(self, connection: Any, loan: Loan) -> Loan:
        return self.update_loan(loan)


@dataclass
class _InMemoryCopyStore(CopyStatusStore):
    copies: dict[UUID, BookCopy] = field(default_factory=dict)

    def get_copy(self, organization_id: UUID, copy_id: UUID) -> BookCopy:
        return self.copies[copy_id]

    def get_copy_for_update_in_connection(
        self, connection: Any, organization_id: UUID, copy_id: UUID
    ) -> BookCopy:
        return self.get_copy(organization_id, copy_id)

    def update_copy_status(
        self, organization_id: UUID, copy_id: UUID, new_status: str
    ) -> BookCopy:
        current = self.copies[copy_id]
        updated = BookCopy(
            copy_id=current.copy_id,
            organization_id=current.organization_id,
            book_id=current.book_id,
            barcode=current.barcode,
            location_id=current.location_id,
            status=new_status,
            condition_code=current.condition_code,
            acquired_at=current.acquired_at,
            created_at=current.created_at,
            updated_at=datetime.now(timezone.utc),
        )
        self.copies[copy_id] = updated
        return updated

    def append_history(self, history: Any) -> None:
        pass


@dataclass
class _InMemoryReservationStore(ReservationStore):
    reservations: dict[UUID, Reservation] = field(default_factory=dict)

    def create_reservation(self, reservation: Reservation) -> Reservation:
        self.reservations[reservation.reservation_id] = reservation
        return reservation

    def get_reservation(
        self, organization_id: UUID, reservation_id: UUID
    ) -> Reservation:
        res = self.reservations.get(reservation_id)
        if res is None or res.organization_id != organization_id:
            raise ReservationNotFoundError(reservation_id)
        return res

    def update_reservation(self, reservation: Reservation) -> Reservation:
        if (
            reservation.reservation_id not in self.reservations
            or self.reservations[reservation.reservation_id].organization_id
            != reservation.organization_id
        ):
            raise ReservationNotFoundError(reservation.reservation_id)
        self.reservations[reservation.reservation_id] = reservation
        return reservation

    def list_reservations(
        self,
        organization_id: UUID,
        *,
        book_id: UUID | None = None,
        requester_user_id: UUID | None = None,
        status: str | None = None,
    ) -> list[Reservation]:
        results = [
            r
            for r in self.reservations.values()
            if r.organization_id == organization_id
        ]
        if book_id is not None:
            results = [r for r in results if r.book_id == book_id]
        if requester_user_id is not None:
            results = [r for r in results if r.requester_user_id == requester_user_id]
        if status is not None:
            results = [r for r in results if r.status == status]
        return sorted(results, key=lambda r: (r.queue_position, r.created_at))

    def get_next_queue_position(self, organization_id: UUID, book_id: UUID) -> int:
        positions = [
            r.queue_position
            for r in self.reservations.values()
            if r.organization_id == organization_id and r.book_id == book_id
        ]
        return max(positions, default=0) + 1

    def get_next_pending_reservation(
        self, organization_id: UUID, book_id: UUID
    ) -> Reservation | None:
        candidates = [
            r
            for r in self.reservations.values()
            if r.organization_id == organization_id
            and r.book_id == book_id
            and r.status == ReservationStatus.PENDING
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda r: (r.queue_position, r.created_at))

    def get_active_reservation_for_user_and_book(
        self, organization_id: UUID, book_id: UUID, user_id: UUID
    ) -> Reservation | None:
        for r in self.reservations.values():
            if (
                r.organization_id == organization_id
                and r.book_id == book_id
                and r.requester_user_id == user_id
                and r.status in (ReservationStatus.PENDING, ReservationStatus.HELD)
            ):
                return r
        return None

    def list_expired_holds(
        self, organization_id: UUID, now: datetime
    ) -> list[Reservation]:
        return [
            r
            for r in self.reservations.values()
            if r.organization_id == organization_id
            and r.status == ReservationStatus.HELD
            and r.hold_expires_at is not None
            and r.hold_expires_at <= now
        ]


class _RecordingTransaction(AuditedTransaction):
    def __init__(self) -> None:
        self.audits: list[AuditEvent] = []
        self.outbox: list[OutboxEvent] = []

    def run(
        self,
        connection: Any,
        mutation: Any,
        audit_event: AuditEvent,
        outbox_events: Any,
    ) -> Any:
        result = mutation(connection)
        self.audits.append(audit_event)
        self.outbox.extend(outbox_events)
        return result


class _InMemoryDeduplicationStore(ConsumerDeduplicationPort):
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
        return JobRecord(
            job_id=uuid4(),
            organization_id=organization_id,
            outbox_event_id=outbox_event_id,
            job_type=job_type,
            payload_version=payload_version,
            status="completed",
            attempts=1,
            next_run_at=None,
            last_error=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
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
        rec = {
            "organization_id": organization_id,
            "outbox_event_id": outbox_event_id,
            "job_type": job_type,
            "status": status,
            "attempts": attempts,
            "last_error": last_error,
        }
        self.job_statuses.append(rec)
        return JobRecord(
            job_id=uuid4(),
            organization_id=organization_id,
            outbox_event_id=outbox_event_id,
            job_type=job_type,
            payload_version=payload_version,
            status=status,
            attempts=attempts,
            next_run_at=next_run_at,
            last_error=last_error,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )


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
                "error_message": error_message,
                "is_dead_letter": is_dead_letter,
            }
        )


class _DummyConnection:
    def commit(self) -> None:
        pass

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        pass


class _DummyTenantContext:
    def connection(self, organization_id: UUID) -> Any:
        from contextlib import contextmanager

        @contextmanager
        def _conn() -> Any:
            yield _DummyConnection()

        return _conn()


def _make_loan(
    *,
    organization_id: UUID,
    status: str = LoanStatus.CHECKED_OUT,
    due_at: datetime | None = None,
) -> Loan:
    now = datetime.now(timezone.utc)
    return Loan(
        loan_id=uuid4(),
        organization_id=organization_id,
        copy_id=uuid4(),
        borrower_user_id=uuid4(),
        status=status,
        loan_status=status,
        request_status="fulfilled",
        requested_at=now,
        approved_at=now,
        checked_out_at=now,
        due_at=due_at or (now + timedelta(days=14)),
        returned_at=None,
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------


def test_overdue_domain_status_and_transitions() -> None:
    """LoanStatus.OVERDUE is a first-class status with explicit state machine transitions."""
    assert LoanStatus.OVERDUE == "overdue"
    assert LoanStatus.OVERDUE in LoanStatus.ALL

    # Allowed: CHECKED_OUT -> OVERDUE
    assert is_allowed_loan_transition(LoanStatus.CHECKED_OUT, LoanStatus.OVERDUE)
    validate_loan_transition(LoanStatus.CHECKED_OUT, LoanStatus.OVERDUE)

    # Allowed: OVERDUE -> RETURNED
    assert is_allowed_loan_transition(LoanStatus.OVERDUE, LoanStatus.RETURNED)
    validate_loan_transition(LoanStatus.OVERDUE, LoanStatus.RETURNED)

    # Disallowed transitions raise InvalidLoanStatusTransitionError
    assert not is_allowed_loan_transition(LoanStatus.REQUESTED, LoanStatus.OVERDUE)
    with pytest.raises(InvalidLoanStatusTransitionError):
        validate_loan_transition(LoanStatus.REQUESTED, LoanStatus.OVERDUE)

    assert not is_allowed_loan_transition(LoanStatus.RETURNED, LoanStatus.OVERDUE)
    with pytest.raises(InvalidLoanStatusTransitionError):
        validate_loan_transition(LoanStatus.RETURNED, LoanStatus.OVERDUE)


def test_overdue_evaluator_transitions_due_loans() -> None:
    """OverdueEvaluator transitions checked_out loans with passed due dates to overdue."""
    org_id = uuid4()
    now = datetime.now(timezone.utc)
    loan_store = _InMemoryLoanStore()
    tx = _RecordingTransaction()

    # Loan 1: due 2 hours ago (should become overdue)
    overdue_loan = _make_loan(
        organization_id=org_id,
        due_at=now - timedelta(hours=2),
    )
    # Loan 2: due in 5 days (should stay checked_out)
    future_loan = _make_loan(
        organization_id=org_id,
        due_at=now + timedelta(days=5),
    )
    loan_store.create_loan(overdue_loan)
    loan_store.create_loan(future_loan)

    evaluator = OverdueEvaluator(
        loan_store=loan_store,
        transaction=tx,
        clock=lambda: now,
    )

    evaluated = evaluator.evaluate_overdue_loans(organization_id=org_id)

    assert len(evaluated) == 1
    assert evaluated[0].loan_id == overdue_loan.loan_id
    assert evaluated[0].status == LoanStatus.OVERDUE
    assert evaluated[0].loan_status == LoanStatus.OVERDUE

    # Verify store updated
    stored_loan_1 = loan_store.get_loan(org_id, overdue_loan.loan_id)
    assert stored_loan_1.status == LoanStatus.OVERDUE

    stored_loan_2 = loan_store.get_loan(org_id, future_loan.loan_id)
    assert stored_loan_2.status == LoanStatus.CHECKED_OUT

    # Verify audit and outbox events emitted
    assert len(tx.audits) == 1
    assert tx.audits[0].action == "loan.marked_overdue"
    assert tx.audits[0].entity_id == overdue_loan.loan_id
    assert tx.audits[0].actor_type == "system"

    assert len(tx.outbox) == 1
    assert tx.outbox[0].event_type == "circulation.loan_overdue"
    assert tx.outbox[0].aggregate_id == overdue_loan.loan_id
    assert tx.outbox[0].idempotency_key == f"loan:{overdue_loan.loan_id}:overdue"


def test_overdue_evaluator_clock_injection() -> None:
    """Clock use is injectable in tests to evaluate overdue state at arbitrary timestamps."""
    org_id = uuid4()
    base_time = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    current_mock_time = base_time

    loan_store = _InMemoryLoanStore()
    tx = _RecordingTransaction()

    # Loan due at 2026-10-02 12:00:00
    loan = _make_loan(
        organization_id=org_id,
        due_at=base_time + timedelta(days=1),
    )
    loan_store.create_loan(loan)

    evaluator = OverdueEvaluator(
        loan_store=loan_store,
        transaction=tx,
        clock=lambda: current_mock_time,
    )

    # 1. At base_time: loan is not overdue
    assert evaluator.evaluate_overdue_loans(organization_id=org_id) == []
    assert loan_store.get_loan(org_id, loan.loan_id).status == LoanStatus.CHECKED_OUT

    # 2. Advance clock past due date (2 days later)
    current_mock_time = base_time + timedelta(days=2)
    overdue_list = evaluator.evaluate_overdue_loans(organization_id=org_id)
    assert len(overdue_list) == 1
    assert overdue_list[0].loan_id == loan.loan_id
    assert overdue_list[0].status == LoanStatus.OVERDUE
    assert loan_store.get_loan(org_id, loan.loan_id).status == LoanStatus.OVERDUE


def test_repeat_overdue_evaluation_does_not_duplicate_state_or_events() -> None:
    """Re-running overdue evaluation does not duplicate state changes or outbox events."""
    org_id = uuid4()
    now = datetime.now(timezone.utc)
    loan_store = _InMemoryLoanStore()
    tx = _RecordingTransaction()

    loan = _make_loan(organization_id=org_id, due_at=now - timedelta(hours=1))
    loan_store.create_loan(loan)

    evaluator = OverdueEvaluator(
        loan_store=loan_store,
        transaction=tx,
        clock=lambda: now,
    )

    # Run 1: transitions loan and emits events
    first_run = evaluator.evaluate_overdue_loans(organization_id=org_id)
    assert len(first_run) == 1
    assert len(tx.outbox) == 1
    assert len(tx.audits) == 1

    # Run 2: loan is already overdue; no further transition or outbox event
    second_run = evaluator.evaluate_overdue_loans(organization_id=org_id)
    assert len(second_run) == 0
    assert len(tx.outbox) == 1
    assert len(tx.audits) == 1


def test_scheduled_overdue_evaluation_dispatcher_job() -> None:
    """Overdue evaluation is dispatched through the generic worker contract and observable in job records."""
    org_id = uuid4()
    now = datetime.now(timezone.utc)
    loan_store = _InMemoryLoanStore()
    tx = _RecordingTransaction()

    loan = _make_loan(organization_id=org_id, due_at=now - timedelta(hours=1))
    loan_store.create_loan(loan)

    evaluator = OverdueEvaluator(
        loan_store=loan_store, transaction=tx, clock=lambda: now
    )

    event_id = uuid4()
    claimed_event = ClaimedOutboxEvent(
        event_id=event_id,
        organization_id=org_id,
        event_type=CIRCULATION_SCHEDULED_OVERDUE_EVENT,
        aggregate_type="circulation",
        aggregate_id=org_id,
        payload_version=1,
        payload_json='{"as_of": null}',
        correlation_id=uuid4(),
        idempotency_key=f"sched:overdue:{org_id}:{now.date()}",
        attempts=0,
        lease_token=uuid4(),
        lease_expires_at=now + timedelta(seconds=30),
        created_at=now,
    )

    claim_store = _InMemoryClaimStore([claimed_event])
    dedup_store = _InMemoryDeduplicationStore()
    tenant_context = _DummyTenantContext()

    dispatcher = OutboxDispatcherService(
        claim_store=claim_store,  # type: ignore[arg-type]
        deduplication_port=dedup_store,
        tenant_context=tenant_context,  # type: ignore[arg-type]
    )

    # Empty dummy reservation service for overdue-only test
    dummy_res_service = ReservationService(
        reservation_store=_InMemoryReservationStore(),
        copy_store=_InMemoryCopyStore(),
        authorizer=None,  # type: ignore[arg-type]
    )

    register_circulation_scheduled_jobs(
        dispatcher,
        overdue_evaluator=evaluator,
        reservation_service=dummy_res_service,
        deduplication_port=dedup_store,
        clock=lambda: now,
    )

    # Dispatch job
    assert dispatcher.dispatch_one() is True
    assert event_id in claim_store.delivered
    assert loan_store.get_loan(org_id, loan.loan_id).status == LoanStatus.OVERDUE

    # Verify deduplication record and job status
    assert dedup_store.is_processed(
        None,
        organization_id=org_id,
        outbox_event_id=event_id,
        job_type=CIRCULATION_SCHEDULED_OVERDUE_EVENT,
    )
    assert any(
        s["status"] == "completed" and s["outbox_event_id"] == event_id
        for s in dedup_store.job_statuses
    )


def test_scheduled_hold_expiry_dispatcher_job() -> None:
    """Hold expiry scheduled job runs through the generic worker contract."""
    org_id = uuid4()
    now = datetime.now(timezone.utc)
    book_id = uuid4()
    copy_id = uuid4()
    user_1 = uuid4()
    user_2 = uuid4()

    copy_store = _InMemoryCopyStore()
    loc_id = uuid4()
    copy_store.copies[copy_id] = BookCopy(
        copy_id=copy_id,
        organization_id=org_id,
        book_id=book_id,
        barcode="BAR-001",
        location_id=loc_id,
        status=CopyStatus.RESERVED,
        condition_code="good",
        acquired_at=now,
        created_at=now,
        updated_at=now,
    )

    res_store = _InMemoryReservationStore()
    # Expired held reservation
    res_1 = Reservation(
        reservation_id=uuid4(),
        organization_id=org_id,
        book_id=book_id,
        requester_user_id=user_1,
        queue_position=1,
        status=ReservationStatus.HELD,
        copy_id=copy_id,
        hold_expires_at=now - timedelta(hours=1),
        created_at=now - timedelta(days=2),
        updated_at=now - timedelta(days=2),
    )
    # Next pending reservation in queue
    res_2 = Reservation(
        reservation_id=uuid4(),
        organization_id=org_id,
        book_id=book_id,
        requester_user_id=user_2,
        queue_position=2,
        status=ReservationStatus.PENDING,
        copy_id=None,
        hold_expires_at=None,
        created_at=now - timedelta(days=1),
        updated_at=now - timedelta(days=1),
    )
    res_store.create_reservation(res_1)
    res_store.create_reservation(res_2)

    res_service = ReservationService(
        reservation_store=res_store,
        copy_store=copy_store,
        authorizer=None,  # type: ignore[arg-type]
    )

    event_id = uuid4()
    claimed_event = ClaimedOutboxEvent(
        event_id=event_id,
        organization_id=org_id,
        event_type=CIRCULATION_SCHEDULED_HOLD_EXPIRY_EVENT,
        aggregate_type="circulation",
        aggregate_id=org_id,
        payload_version=1,
        payload_json="{}",
        correlation_id=uuid4(),
        idempotency_key=f"sched:hold_exp:{org_id}:{now.date()}",
        attempts=0,
        lease_token=uuid4(),
        lease_expires_at=now + timedelta(seconds=30),
        created_at=now,
    )

    claim_store = _InMemoryClaimStore([claimed_event])
    dedup_store = _InMemoryDeduplicationStore()
    tenant_context = _DummyTenantContext()

    dispatcher = OutboxDispatcherService(
        claim_store=claim_store,  # type: ignore[arg-type]
        deduplication_port=dedup_store,
        tenant_context=tenant_context,  # type: ignore[arg-type]
    )

    dummy_evaluator = OverdueEvaluator(
        loan_store=_InMemoryLoanStore(),
    )

    register_circulation_scheduled_jobs(
        dispatcher,
        overdue_evaluator=dummy_evaluator,
        reservation_service=res_service,
        deduplication_port=dedup_store,
        clock=lambda: now,
    )

    assert dispatcher.dispatch_one() is True

    # Reservation 1 expired, Reservation 2 advanced to held with copy allocated
    updated_res_1 = res_store.get_reservation(org_id, res_1.reservation_id)
    assert updated_res_1.status == ReservationStatus.EXPIRED

    updated_res_2 = res_store.get_reservation(org_id, res_2.reservation_id)
    assert updated_res_2.status == ReservationStatus.HELD
    assert updated_res_2.copy_id == copy_id


def test_tenant_isolation_in_overdue_evaluation() -> None:
    """Evaluation strictly stays within the tenant of the job; no cross-tenant scanning."""
    org_a = uuid4()
    org_b = uuid4()
    now = datetime.now(timezone.utc)

    loan_store = _InMemoryLoanStore()
    tx = _RecordingTransaction()

    loan_a = _make_loan(organization_id=org_a, due_at=now - timedelta(hours=1))
    loan_b = _make_loan(organization_id=org_b, due_at=now - timedelta(hours=1))
    loan_store.create_loan(loan_a)
    loan_store.create_loan(loan_b)

    evaluator = OverdueEvaluator(
        loan_store=loan_store, transaction=tx, clock=lambda: now
    )

    # Run for Org A only
    evaluated_a = evaluator.evaluate_overdue_loans(organization_id=org_a)
    assert len(evaluated_a) == 1
    assert evaluated_a[0].loan_id == loan_a.loan_id

    # Org A loan is now overdue
    assert loan_store.get_loan(org_a, loan_a.loan_id).status == LoanStatus.OVERDUE

    # Org B loan must REMAIN checked_out
    assert loan_store.get_loan(org_b, loan_b.loan_id).status == LoanStatus.CHECKED_OUT
