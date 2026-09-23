"""Integration tests for education borrower-policy adapter and loan snapshots.

Validates BE-021 requirements:
- Resolving configurable education borrowing policies through a stable port.
- Student default 5 books/14 days and teacher default 20 books/90 days.
- Overrides via organization policy data.
- Tenant isolation of borrowing policies.
- Snapshots stored on the loan at checkout and immutability after policy updates.
- Core circulation depends only on the policy port with zero education imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.authorization import (
    AuthorizationPort,
)
from openlibrary.modules.core.application.copy_status import (
    CopyStatusHistory,
    CopyStatusStore,
)
from openlibrary.modules.core.application.inventory import BookCopy
from openlibrary.modules.core.application.loans import (
    Loan,
    LoanService,
    LoanStore,
)
from openlibrary.modules.core.domain.copy_status import CopyStatus
from openlibrary.modules.core.domain.loans import (
    ActiveLoanLimitExceededError,
    BorrowerNotEligibleError,
    LoanStatus,
)
from openlibrary.modules.education.domain import (
    BorrowerPolicy,
    Student,
    Teacher,
)
from openlibrary.modules.education.policy import (
    DEFAULT_STUDENT_DURATION_DAYS,
    DEFAULT_STUDENT_MAX_ACTIVE_LOANS,
    DEFAULT_TEACHER_DURATION_DAYS,
    DEFAULT_TEACHER_MAX_ACTIVE_LOANS,
    EducationBorrowerPolicyAdapter,
)


class _AllowAllAuthorizer(AuthorizationPort):
    def require(self, actor: Principal, permission: str) -> None:
        pass


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
        self, organization_id: UUID, copy_id: UUID, status: str
    ) -> None:
        copy = self.get_copy(organization_id, copy_id)
        self.copies[copy_id] = BookCopy(
            copy_id=copy.copy_id,
            organization_id=copy.organization_id,
            book_id=copy.book_id,
            barcode=copy.barcode,
            status=status,
            location_id=copy.location_id,
            condition_code=copy.condition_code,
            acquired_at=copy.acquired_at,
            created_at=copy.created_at,
            updated_at=datetime.now(timezone.utc),
        )

    def append_history(self, record: CopyStatusHistory) -> None:
        self.history.append(record)

    def list_history(
        self, organization_id: UUID, copy_id: UUID
    ) -> list[CopyStatusHistory]:
        return [h for h in self.history if h.copy_id == copy_id]


@dataclass
class _InMemoryLoanStore(LoanStore):
    loans: dict[UUID, Loan] = field(default_factory=dict)

    def create_loan(self, loan: Loan) -> Loan:
        self.loans[loan.loan_id] = loan
        return loan

    def get_loan(self, organization_id: UUID, loan_id: UUID) -> Loan:
        loan = self.loans.get(loan_id)
        if loan is None or loan.organization_id != organization_id:
            raise KeyError(loan_id)
        return loan

    def update_loan(self, loan: Loan) -> Loan:
        if (
            loan.loan_id not in self.loans
            or self.loans[loan.loan_id].organization_id != loan.organization_id
        ):
            raise KeyError(loan.loan_id)
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
                loan for loan in results if loan.borrower_user_id == borrower_user_id
            ]
        if copy_id is not None:
            results = [loan for loan in results if loan.copy_id == copy_id]
        if status is not None:
            results = [loan for loan in results if loan.status == status]
        return sorted(results, key=lambda loan: loan.created_at, reverse=True)

    def count_active_loans_for_borrower(
        self, organization_id: UUID, borrower_user_id: UUID
    ) -> int:
        return sum(
            1
            for loan in self.loans.values()
            if loan.organization_id == organization_id
            and loan.borrower_user_id == borrower_user_id
            and loan.status == LoanStatus.CHECKED_OUT
        )

    def get_active_loan_for_copy(
        self, organization_id: UUID, copy_id: UUID
    ) -> Loan | None:
        for loan in self.loans.values():
            if (
                loan.organization_id == organization_id
                and loan.copy_id == copy_id
                and loan.status == LoanStatus.CHECKED_OUT
            ):
                return loan
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


@dataclass
class _InMemoryEducationStore:
    is_enabled: bool = True
    students: dict[tuple[UUID, UUID], Student] = field(default_factory=dict)
    teachers: dict[tuple[UUID, UUID], Teacher] = field(default_factory=dict)
    policies: dict[tuple[UUID, str], BorrowerPolicy] = field(default_factory=dict)

    def is_edition_enabled(self, organization_id: UUID) -> bool:
        return self.is_enabled

    def get_student_by_user_id(
        self, organization_id: UUID, user_id: UUID
    ) -> Student | None:
        return self.students.get((organization_id, user_id))

    def get_teacher_by_user_id(
        self, organization_id: UUID, user_id: UUID
    ) -> Teacher | None:
        return self.teachers.get((organization_id, user_id))

    def get_borrower_policy(
        self, organization_id: UUID, borrower_type: str
    ) -> BorrowerPolicy | None:
        return self.policies.get((organization_id, borrower_type))

    def list_borrower_policies(self, organization_id: UUID) -> list[BorrowerPolicy]:
        return [
            p for (org_id, _), p in self.policies.items() if org_id == organization_id
        ]

    def upsert_borrower_policy(self, policy: BorrowerPolicy) -> BorrowerPolicy:
        self.policies[(policy.organization_id, policy.borrower_type)] = policy
        return policy


def _make_copy(organization_id: UUID, copy_id: UUID | None = None) -> BookCopy:
    now = datetime.now(timezone.utc)
    return BookCopy(
        copy_id=copy_id or uuid4(),
        organization_id=organization_id,
        book_id=uuid4(),
        barcode=f"BC-{uuid4().hex[:8]}",
        status=CopyStatus.AVAILABLE,
        location_id=uuid4(),
        condition_code="good",
        acquired_at=now,
        created_at=now,
        updated_at=now,
    )


def test_resolve_student_default_policy() -> None:
    org_id = uuid4()
    user_id = uuid4()
    now = datetime.now(timezone.utc)

    edu_store = _InMemoryEducationStore()
    student = Student(
        student_id=uuid4(),
        organization_id=org_id,
        user_id=user_id,
        student_number="STU-001",
        department_id=None,
        status="active",
        created_at=now,
        updated_at=now,
    )
    edu_store.students[(org_id, user_id)] = student

    adapter = EducationBorrowerPolicyAdapter(store=edu_store)
    policy = adapter.resolve_policy(org_id, user_id)

    assert policy.borrower_type == "student"
    assert policy.max_active_loans == DEFAULT_STUDENT_MAX_ACTIVE_LOANS  # 5
    assert policy.duration_days == DEFAULT_STUDENT_DURATION_DAYS  # 14
    assert policy.policy_snapshot["borrower_type"] == "student"
    assert policy.policy_snapshot["max_active_loans"] == 5
    assert policy.policy_snapshot["duration_days"] == 14
    assert policy.policy_snapshot["student_number"] == "STU-001"


def test_resolve_teacher_default_policy() -> None:
    org_id = uuid4()
    user_id = uuid4()
    now = datetime.now(timezone.utc)

    edu_store = _InMemoryEducationStore()
    teacher = Teacher(
        teacher_id=uuid4(),
        organization_id=org_id,
        user_id=user_id,
        employee_number="TEA-999",
        department_id=None,
        status="active",
        created_at=now,
        updated_at=now,
    )
    edu_store.teachers[(org_id, user_id)] = teacher

    adapter = EducationBorrowerPolicyAdapter(store=edu_store)
    policy = adapter.resolve_policy(org_id, user_id)

    assert policy.borrower_type == "teacher"
    assert policy.max_active_loans == DEFAULT_TEACHER_MAX_ACTIVE_LOANS  # 20
    assert policy.duration_days == DEFAULT_TEACHER_DURATION_DAYS  # 90
    assert policy.policy_snapshot["borrower_type"] == "teacher"
    assert policy.policy_snapshot["max_active_loans"] == 20
    assert policy.policy_snapshot["duration_days"] == 90
    assert policy.policy_snapshot["employee_number"] == "TEA-999"


def test_organization_policy_override() -> None:
    org_id = uuid4()
    user_id = uuid4()
    now = datetime.now(timezone.utc)

    edu_store = _InMemoryEducationStore()
    student = Student(
        student_id=uuid4(),
        organization_id=org_id,
        user_id=user_id,
        student_number="STU-002",
        department_id=None,
        status="active",
        created_at=now,
        updated_at=now,
    )
    edu_store.students[(org_id, user_id)] = student

    # Override student policy to 8 books, 21 days
    custom_policy = BorrowerPolicy(
        policy_id=uuid4(),
        organization_id=org_id,
        borrower_type="student",
        max_active_loans=8,
        duration_days=21,
        status="active",
        created_at=now,
        updated_at=now,
    )
    edu_store.upsert_borrower_policy(custom_policy)

    adapter = EducationBorrowerPolicyAdapter(store=edu_store)
    policy = adapter.resolve_policy(org_id, user_id)

    assert policy.borrower_type == "student"
    assert policy.max_active_loans == 8
    assert policy.duration_days == 21
    assert policy.policy_snapshot["policy_id"] == str(custom_policy.policy_id)


def test_policy_resolution_is_tenant_scoped() -> None:
    org_a = uuid4()
    org_b = uuid4()
    user_id = uuid4()
    now = datetime.now(timezone.utc)

    edu_store = _InMemoryEducationStore()
    # Student in Org A
    edu_store.students[(org_a, user_id)] = Student(
        student_id=uuid4(),
        organization_id=org_a,
        user_id=user_id,
        student_number="STU-A",
        department_id=None,
        status="active",
        created_at=now,
        updated_at=now,
    )
    # Custom policy in Org A: 10 books / 30 days
    edu_store.upsert_borrower_policy(
        BorrowerPolicy(
            policy_id=uuid4(),
            organization_id=org_a,
            borrower_type="student",
            max_active_loans=10,
            duration_days=30,
            status="active",
            created_at=now,
            updated_at=now,
        )
    )

    adapter = EducationBorrowerPolicyAdapter(store=edu_store)

    # In Org A, resolves overridden policy
    policy_a = adapter.resolve_policy(org_a, user_id)
    assert policy_a.max_active_loans == 10
    assert policy_a.duration_days == 30

    # In Org B, user is not a student in Org B
    with pytest.raises(BorrowerNotEligibleError):
        adapter.resolve_policy(org_b, user_id)


def test_ineligible_borrower_without_fallback_raises_error() -> None:
    org_id = uuid4()
    user_id = uuid4()

    edu_store = _InMemoryEducationStore()
    adapter = EducationBorrowerPolicyAdapter(store=edu_store, fallback_resolver=None)

    with pytest.raises(BorrowerNotEligibleError):
        adapter.resolve_policy(org_id, user_id)


def test_changing_policy_affects_future_eligibility_without_controller_changes() -> (
    None
):
    org_id = uuid4()
    student_user_id = uuid4()
    librarian_user_id = uuid4()
    now = datetime.now(timezone.utc)

    edu_store = _InMemoryEducationStore()
    edu_store.students[(org_id, student_user_id)] = Student(
        student_id=uuid4(),
        organization_id=org_id,
        user_id=student_user_id,
        student_number="STU-LIMIT",
        department_id=None,
        status="active",
        created_at=now,
        updated_at=now,
    )

    loan_store = _InMemoryLoanStore()
    copy_store = _InMemoryCopyStore()
    authorizer = _AllowAllAuthorizer()

    adapter = EducationBorrowerPolicyAdapter(store=edu_store)
    loan_service = LoanService(
        loan_store=loan_store,
        copy_store=copy_store,
        authorizer=authorizer,
        policy_resolver=adapter,
    )

    student_actor = Principal(
        user_id=student_user_id, organization_id=org_id, session_id=uuid4()
    )
    librarian_actor = Principal(
        user_id=librarian_user_id, organization_id=org_id, session_id=uuid4()
    )

    # 1. Borrow up to default student limit (5 books)
    for _ in range(5):
        copy = _make_copy(org_id)
        copy_store.copies[copy.copy_id] = copy
        loan_service.desk_checkout(
            actor=librarian_actor,
            copy_id=copy.copy_id,
            borrower_user_id=student_user_id,
        )

    assert loan_store.count_active_loans_for_borrower(org_id, student_user_id) == 5

    # 2. 6th borrow attempt rejected by active loan limit
    copy6 = _make_copy(org_id)
    copy_store.copies[copy6.copy_id] = copy6
    with pytest.raises(ActiveLoanLimitExceededError):
        loan_service.request_loan(actor=student_actor, copy_id=copy6.copy_id)

    # 3. Evidence checkpoint: Changing organization policy affects future eligibility without controller changes
    edu_store.upsert_borrower_policy(
        BorrowerPolicy(
            policy_id=uuid4(),
            organization_id=org_id,
            borrower_type="student",
            max_active_loans=6,
            duration_days=14,
            status="active",
            created_at=now,
            updated_at=now,
        )
    )

    # 4. Now 6th loan can be requested and checked out!
    loan6 = loan_service.request_loan(actor=student_actor, copy_id=copy6.copy_id)
    assert loan6.status == LoanStatus.REQUESTED
    assert loan6.policy_snapshot["max_active_loans"] == 6


def test_checkout_snapshot_and_immutability_after_policy_changes() -> None:
    org_id = uuid4()
    teacher_user_id = uuid4()
    librarian_user_id = uuid4()
    now = datetime.now(timezone.utc)

    edu_store = _InMemoryEducationStore()
    edu_store.teachers[(org_id, teacher_user_id)] = Teacher(
        teacher_id=uuid4(),
        organization_id=org_id,
        user_id=teacher_user_id,
        employee_number="TEA-SNAP",
        department_id=None,
        status="active",
        created_at=now,
        updated_at=now,
    )

    loan_store = _InMemoryLoanStore()
    copy_store = _InMemoryCopyStore()
    authorizer = _AllowAllAuthorizer()

    adapter = EducationBorrowerPolicyAdapter(store=edu_store)
    loan_service = LoanService(
        loan_store=loan_store,
        copy_store=copy_store,
        authorizer=authorizer,
        policy_resolver=adapter,
    )

    librarian_actor = Principal(
        user_id=librarian_user_id, organization_id=org_id, session_id=uuid4()
    )

    copy = _make_copy(org_id)
    copy_store.copies[copy.copy_id] = copy

    # Checkout loan for teacher (default 90 days)
    loan = loan_service.desk_checkout(
        actor=librarian_actor,
        copy_id=copy.copy_id,
        borrower_user_id=teacher_user_id,
    )

    assert loan.status == LoanStatus.CHECKED_OUT
    assert loan.due_at is not None
    initial_due_at = loan.due_at
    initial_snapshot = dict(loan.policy_snapshot)

    assert initial_snapshot["borrower_type"] == "teacher"
    assert initial_snapshot["duration_days"] == 90
    assert initial_snapshot["max_active_loans"] == 20
    assert initial_snapshot["employee_number"] == "TEA-SNAP"

    # Evidence checkpoint: Admin changes organization teacher policy to 30 days and 10 books
    edu_store.upsert_borrower_policy(
        BorrowerPolicy(
            policy_id=uuid4(),
            organization_id=org_id,
            borrower_type="teacher",
            max_active_loans=10,
            duration_days=30,
            status="active",
            created_at=now,
            updated_at=now,
        )
    )

    # Existing loan facts remain completely stable and immutable
    refetched_loan = loan_service.get_loan(actor=librarian_actor, loan_id=loan.loan_id)
    assert refetched_loan.due_at == initial_due_at
    assert refetched_loan.policy_snapshot["duration_days"] == 90
    assert refetched_loan.policy_snapshot["max_active_loans"] == 20


def test_core_circulation_has_no_education_imports() -> None:
    """Reviewer checklist: Verify no education code or imports exist in core domain or application."""
    import openlibrary.modules.core.application.loans as core_app_loans
    import openlibrary.modules.core.domain.loans as core_domain_loans

    with open(core_domain_loans.__file__, "r", encoding="utf-8") as f:
        domain_src = f.read()
    with open(core_app_loans.__file__, "r", encoding="utf-8") as f:
        app_src = f.read()

    assert "education" not in domain_src.lower()
    assert "openlibrary.modules.education" not in app_src
    assert "Student" not in domain_src
    assert "Teacher" not in domain_src
