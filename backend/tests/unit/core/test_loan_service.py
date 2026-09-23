"""Unit tests for loan domain transitions and LoanService application logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest

from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.authorization import (
    AuthorizationDenied,
    AuthorizationPort,
)
from openlibrary.modules.core.application.copy_status import (
    CopyStatusHistory,
    CopyStatusStore,
)
from openlibrary.modules.core.application.inventory import BookCopy
from openlibrary.modules.core.application.loans import Loan, LoanService, LoanStore
from openlibrary.modules.core.domain.copy_status import CopyStatus
from openlibrary.modules.core.domain.loans import (
    ALLOWED_LOAN_TRANSITIONS,
    ActiveLoanLimitExceededError,
    CopyNotAvailableForLoanError,
    InvalidLoanStatusTransitionError,
    LoanNotFoundError,
    LoanStatus,
    is_allowed_loan_transition,
    validate_loan_transition,
)
from openlibrary.modules.ops.application.persistence import (
    AuditEvent,
    AuditedTransaction,
    OutboxEvent,
)

ORG_A = uuid4()
ORG_B = uuid4()
BORROWER_ID = uuid4()
LIBRARIAN_ID = uuid4()
BORROWER_ACTOR = Principal(
    user_id=BORROWER_ID, organization_id=ORG_A, session_id=uuid4()
)
LIBRARIAN_ACTOR = Principal(
    user_id=LIBRARIAN_ID, organization_id=ORG_A, session_id=uuid4()
)


class _AllowAllAuthorizer(AuthorizationPort):
    def require(self, principal: Principal, permission: str) -> None:
        pass


class _DenyAllAuthorizer(AuthorizationPort):
    def require(self, principal: Principal, permission: str) -> None:
        raise AuthorizationDenied(f"Permission denied: {permission}")


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
            loan_item
            for loan_item in self.loans.values()
            if loan_item.organization_id == organization_id
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
            and loan_item.status == LoanStatus.CHECKED_OUT
        )

    def get_active_loan_for_copy(
        self, organization_id: UUID, copy_id: UUID
    ) -> Loan | None:
        for loan_item in self.loans.values():
            if (
                loan_item.organization_id == organization_id
                and loan_item.copy_id == copy_id
                and loan_item.status == LoanStatus.CHECKED_OUT
            ):
                return loan_item
        return None


@dataclass
class _InMemoryCopyStore(CopyStatusStore):
    copies: dict[UUID, BookCopy] = field(default_factory=dict)
    history: list[CopyStatusHistory] = field(default_factory=list)

    def get_copy(self, organization_id: UUID, copy_id: UUID) -> BookCopy:
        copy = self.copies.get(copy_id)
        if copy is None or copy.organization_id != organization_id:
            raise KeyError(copy_id)
        return copy

    def update_copy_status(
        self, organization_id: UUID, copy_id: UUID, to_status: str
    ) -> BookCopy:
        copy = self.get_copy(organization_id, copy_id)
        now = datetime.now(timezone.utc)
        updated = BookCopy(
            copy_id=copy.copy_id,
            organization_id=copy.organization_id,
            book_id=copy.book_id,
            barcode=copy.barcode,
            location_id=copy.location_id,
            status=to_status,
            condition_code=copy.condition_code,
            acquired_at=copy.acquired_at,
            created_at=copy.created_at,
            updated_at=now,
        )
        self.copies[copy_id] = updated
        return updated

    def append_history(self, record: CopyStatusHistory) -> CopyStatusHistory:
        self.history.append(record)
        return record

    def list_history_for_copy(
        self, organization_id: UUID, copy_id: UUID
    ) -> list[CopyStatusHistory]:
        return [
            h
            for h in self.history
            if h.organization_id == organization_id and h.copy_id == copy_id
        ]


@dataclass
class _RecordingAuditedTransaction(AuditedTransaction):
    audit_events: list[AuditEvent] = field(default_factory=list)
    outbox_events: list[OutboxEvent] = field(default_factory=list)

    def run(
        self,
        connection: Any,
        mutation: Any,
        audit_event: AuditEvent,
        outbox_events: Any,
    ) -> Any:
        result = mutation(connection)
        self.audit_events.append(audit_event)
        self.outbox_events.extend(outbox_events)
        return result


def _make_sample_copy(copy_id: UUID, status: str = CopyStatus.AVAILABLE) -> BookCopy:
    now = datetime.now(timezone.utc)
    return BookCopy(
        copy_id=copy_id,
        organization_id=ORG_A,
        book_id=uuid4(),
        barcode="BC-UNIT-1",
        location_id=uuid4(),
        status=status,
        condition_code="good",
        acquired_at=now,
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# Domain State Machine Tests
# ---------------------------------------------------------------------------


def test_domain_allowed_transitions() -> None:
    expected = {
        (LoanStatus.REQUESTED, LoanStatus.APPROVED),
        (LoanStatus.REQUESTED, LoanStatus.REJECTED),
        (LoanStatus.REQUESTED, LoanStatus.CANCELLED),
        (LoanStatus.APPROVED, LoanStatus.CHECKED_OUT),
        (LoanStatus.APPROVED, LoanStatus.CANCELLED),
        (LoanStatus.CHECKED_OUT, LoanStatus.RETURNED),
    }
    assert ALLOWED_LOAN_TRANSITIONS == expected
    for from_s, to_s in expected:
        assert is_allowed_loan_transition(from_s, to_s) is True
        validate_loan_transition(from_s, to_s)  # Should not raise


def test_domain_disallowed_transitions_raise() -> None:
    # Direct checkout from requested is strictly forbidden
    assert (
        is_allowed_loan_transition(LoanStatus.REQUESTED, LoanStatus.CHECKED_OUT)
        is False
    )
    with pytest.raises(InvalidLoanStatusTransitionError):
        validate_loan_transition(LoanStatus.REQUESTED, LoanStatus.CHECKED_OUT)

    # Returned is terminal
    assert (
        is_allowed_loan_transition(LoanStatus.RETURNED, LoanStatus.CHECKED_OUT) is False
    )
    with pytest.raises(InvalidLoanStatusTransitionError):
        validate_loan_transition(LoanStatus.RETURNED, LoanStatus.CHECKED_OUT)


# ---------------------------------------------------------------------------
# Application Service Tests
# ---------------------------------------------------------------------------


def test_request_loan_records_audit_and_outbox() -> None:
    loan_store = _InMemoryLoanStore()
    copy_store = _InMemoryCopyStore()
    copy_id = uuid4()
    copy_store.copies[copy_id] = _make_sample_copy(copy_id)
    tx = _RecordingAuditedTransaction()

    service = LoanService(
        loan_store=loan_store,
        copy_store=copy_store,
        authorizer=_AllowAllAuthorizer(),
        transaction=tx,
    )

    loan = service.request_loan(
        actor=BORROWER_ACTOR,
        copy_id=copy_id,
        duration_days=10,
    )

    assert loan.status == LoanStatus.REQUESTED
    assert loan.loan_status == LoanStatus.REQUESTED
    assert loan.request_status == "pending"
    assert loan.policy_snapshot["duration_days"] == 10

    # Operational evidence
    assert len(tx.audit_events) == 1
    assert tx.audit_events[0].action == "loan.requested"
    assert len(tx.outbox_events) == 1
    assert tx.outbox_events[0].event_type == "circulation.loan_requested"


def test_request_loan_rejects_unavailable_copy() -> None:
    loan_store = _InMemoryLoanStore()
    copy_store = _InMemoryCopyStore()
    copy_id = uuid4()
    copy_store.copies[copy_id] = _make_sample_copy(
        copy_id, status=CopyStatus.MAINTENANCE
    )

    service = LoanService(
        loan_store=loan_store,
        copy_store=copy_store,
        authorizer=_AllowAllAuthorizer(),
    )

    with pytest.raises(CopyNotAvailableForLoanError):
        service.request_loan(actor=BORROWER_ACTOR, copy_id=copy_id)


def test_request_loan_rejects_when_limit_exceeded() -> None:
    loan_store = _InMemoryLoanStore()
    copy_store = _InMemoryCopyStore()
    now = datetime.now(timezone.utc)

    # 5 active loans
    for _ in range(5):
        cid = uuid4()
        loan_store.create_loan(
            Loan(
                loan_id=uuid4(),
                organization_id=ORG_A,
                copy_id=cid,
                borrower_user_id=BORROWER_ID,
                status=LoanStatus.CHECKED_OUT,
                loan_status=LoanStatus.CHECKED_OUT,
                request_status="fulfilled",
                requested_at=now,
                created_at=now,
                updated_at=now,
            )
        )

    copy_id = uuid4()
    copy_store.copies[copy_id] = _make_sample_copy(copy_id)

    service = LoanService(
        loan_store=loan_store,
        copy_store=copy_store,
        authorizer=_AllowAllAuthorizer(),
    )

    with pytest.raises(ActiveLoanLimitExceededError):
        service.request_loan(actor=BORROWER_ACTOR, copy_id=copy_id)


def test_approval_and_rejection_actions() -> None:
    loan_store = _InMemoryLoanStore()
    copy_store = _InMemoryCopyStore()
    copy_id = uuid4()
    copy_store.copies[copy_id] = _make_sample_copy(copy_id)
    tx = _RecordingAuditedTransaction()

    service = LoanService(
        loan_store=loan_store,
        copy_store=copy_store,
        authorizer=_AllowAllAuthorizer(),
        transaction=tx,
    )

    loan = service.request_loan(actor=BORROWER_ACTOR, copy_id=copy_id)

    # Approve
    approved = service.approve_loan(actor=LIBRARIAN_ACTOR, loan_id=loan.loan_id)
    assert approved.status == LoanStatus.APPROVED
    assert approved.approved_at is not None

    # Cannot reject an approved loan
    with pytest.raises(InvalidLoanStatusTransitionError):
        service.reject_loan(actor=LIBRARIAN_ACTOR, loan_id=loan.loan_id)


def test_checkout_requires_approval_first() -> None:
    loan_store = _InMemoryLoanStore()
    copy_store = _InMemoryCopyStore()
    copy_id = uuid4()
    copy_store.copies[copy_id] = _make_sample_copy(copy_id)

    service = LoanService(
        loan_store=loan_store,
        copy_store=copy_store,
        authorizer=_AllowAllAuthorizer(),
    )

    loan = service.request_loan(actor=BORROWER_ACTOR, copy_id=copy_id)

    # Invariant: Self-service requests cannot checkout without approval
    with pytest.raises(InvalidLoanStatusTransitionError):
        service.checkout_loan(actor=LIBRARIAN_ACTOR, loan_id=loan.loan_id)


def test_desk_checkout_invokes_shared_service_with_approval() -> None:
    loan_store = _InMemoryLoanStore()
    copy_store = _InMemoryCopyStore()
    copy_id = uuid4()
    copy_store.copies[copy_id] = _make_sample_copy(copy_id)
    tx = _RecordingAuditedTransaction()

    service = LoanService(
        loan_store=loan_store,
        copy_store=copy_store,
        authorizer=_AllowAllAuthorizer(),
        transaction=tx,
    )

    loan = service.desk_checkout(
        actor=LIBRARIAN_ACTOR,
        copy_id=copy_id,
        borrower_user_id=BORROWER_ID,
        duration_days=28,
    )

    assert loan.status == LoanStatus.CHECKED_OUT
    assert loan.approved_at is not None
    assert loan.checked_out_at is not None
    assert loan.due_at is not None

    # Copy transitioned to borrowed
    assert copy_store.get_copy(ORG_A, copy_id).status == CopyStatus.BORROWED
    assert any(h.to_status == CopyStatus.BORROWED for h in copy_store.history)

    # Audit events sequence shows full lifecycle
    actions = [e.action for e in tx.audit_events]
    assert actions == ["loan.requested", "loan.approved", "loan.checked_out"]


def test_atomic_return_updates_loan_and_copy() -> None:
    loan_store = _InMemoryLoanStore()
    copy_store = _InMemoryCopyStore()
    copy_id = uuid4()
    copy_store.copies[copy_id] = _make_sample_copy(copy_id)
    tx = _RecordingAuditedTransaction()

    service = LoanService(
        loan_store=loan_store,
        copy_store=copy_store,
        authorizer=_AllowAllAuthorizer(),
        transaction=tx,
    )

    checked_out_loan = service.desk_checkout(
        actor=LIBRARIAN_ACTOR,
        copy_id=copy_id,
        borrower_user_id=BORROWER_ID,
    )

    # Return
    returned_loan = service.return_loan(
        actor=LIBRARIAN_ACTOR,
        loan_id=checked_out_loan.loan_id,
    )

    assert returned_loan.status == LoanStatus.RETURNED
    assert returned_loan.returned_at is not None

    # Copy is available again
    assert copy_store.get_copy(ORG_A, copy_id).status == CopyStatus.AVAILABLE

    # Copy history appended
    history = copy_store.list_history_for_copy(ORG_A, copy_id)
    assert any(
        h.from_status == CopyStatus.BORROWED and h.to_status == CopyStatus.AVAILABLE
        for h in history
    )

    # Outbox event for return emitted
    assert any(o.event_type == "circulation.loan_returned" for o in tx.outbox_events)


def test_authorization_checks_fail_closed() -> None:
    loan_store = _InMemoryLoanStore()
    copy_store = _InMemoryCopyStore()
    copy_id = uuid4()
    copy_store.copies[copy_id] = _make_sample_copy(copy_id)

    service = LoanService(
        loan_store=loan_store,
        copy_store=copy_store,
        authorizer=_DenyAllAuthorizer(),
    )

    with pytest.raises(AuthorizationDenied):
        service.request_loan(actor=BORROWER_ACTOR, copy_id=copy_id)

    with pytest.raises(AuthorizationDenied):
        service.desk_checkout(
            actor=LIBRARIAN_ACTOR, copy_id=copy_id, borrower_user_id=BORROWER_ID
        )
