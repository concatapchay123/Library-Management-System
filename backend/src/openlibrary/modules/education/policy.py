"""Borrowing policy adapter for the education edition.

Implements the BorrowingPolicyResolver protocol consumed by core circulation.
Zero core loan entities or core domain logic know about student/teacher concepts.
"""

from __future__ import annotations

from uuid import UUID

from openlibrary.modules.core.application.loans import (
    BorrowingPolicy,
    BorrowingPolicyResolver,
)
from openlibrary.modules.core.domain.loans import BorrowerNotEligibleError
from openlibrary.modules.education.application import (
    DEFAULT_STUDENT_DURATION_DAYS,
    DEFAULT_STUDENT_MAX_ACTIVE_LOANS,
    DEFAULT_TEACHER_DURATION_DAYS,
    DEFAULT_TEACHER_MAX_ACTIVE_LOANS,
    EducationStore,
)
from openlibrary.modules.education.domain import Student, Teacher


class EducationBorrowerPolicyAdapter(BorrowingPolicyResolver):
    """Resolves student/teacher borrowing policies from education profile and configured policy data."""

    def __init__(
        self,
        store: EducationStore,
        fallback_resolver: BorrowingPolicyResolver | None = None,
    ) -> None:
        self._store = store
        self._fallback = fallback_resolver

    def resolve_policy(
        self, organization_id: UUID, borrower_user_id: UUID
    ) -> BorrowingPolicy:
        """Resolve tenant-scoped policy rules and snapshot facts for a borrower."""
        if not self._store.is_edition_enabled(organization_id):
            if self._fallback is not None:
                return self._fallback.resolve_policy(organization_id, borrower_user_id)
            raise BorrowerNotEligibleError(
                f"Education edition is not enabled for organization {organization_id}"
            )

        # 1. Check for student profile
        student = self._store.get_student_by_user_id(organization_id, borrower_user_id)
        if student is not None and student.status == "active":
            return self._build_student_policy(organization_id, student)

        # 2. Check for teacher profile
        teacher = self._store.get_teacher_by_user_id(organization_id, borrower_user_id)
        if teacher is not None and teacher.status == "active":
            return self._build_teacher_policy(organization_id, teacher)

        # 3. Borrower has no active education profile in this tenant
        if self._fallback is not None:
            return self._fallback.resolve_policy(organization_id, borrower_user_id)

        raise BorrowerNotEligibleError(
            f"User {borrower_user_id} has no active student or teacher profile in organization {organization_id}"
        )

    def _build_student_policy(
        self, organization_id: UUID, student: Student
    ) -> BorrowingPolicy:
        configured = self._store.get_borrower_policy(organization_id, "student")
        if configured is not None and configured.status == "active":
            max_active_loans = configured.max_active_loans
            duration_days = configured.duration_days
            policy_id: str | None = str(configured.policy_id)
        else:
            max_active_loans = DEFAULT_STUDENT_MAX_ACTIVE_LOANS
            duration_days = DEFAULT_STUDENT_DURATION_DAYS
            policy_id = None

        facts: dict[str, object] = {
            "borrower_type": "student",
            "max_active_loans": max_active_loans,
            "duration_days": duration_days,
            "source": "education",
            "student_id": str(student.student_id),
            "student_number": student.student_number,
        }
        if policy_id is not None:
            facts["policy_id"] = policy_id

        return BorrowingPolicy(
            borrower_type="student",
            max_active_loans=max_active_loans,
            duration_days=duration_days,
            policy_snapshot=facts,
        )

    def _build_teacher_policy(
        self, organization_id: UUID, teacher: Teacher
    ) -> BorrowingPolicy:
        configured = self._store.get_borrower_policy(organization_id, "teacher")
        if configured is not None and configured.status == "active":
            max_active_loans = configured.max_active_loans
            duration_days = configured.duration_days
            policy_id: str | None = str(configured.policy_id)
        else:
            max_active_loans = DEFAULT_TEACHER_MAX_ACTIVE_LOANS
            duration_days = DEFAULT_TEACHER_DURATION_DAYS
            policy_id = None

        facts: dict[str, object] = {
            "borrower_type": "teacher",
            "max_active_loans": max_active_loans,
            "duration_days": duration_days,
            "source": "education",
            "teacher_id": str(teacher.teacher_id),
            "employee_number": teacher.employee_number,
        }
        if policy_id is not None:
            facts["policy_id"] = policy_id

        return BorrowingPolicy(
            borrower_type="teacher",
            max_active_loans=max_active_loans,
            duration_days=duration_days,
            policy_snapshot=facts,
        )
