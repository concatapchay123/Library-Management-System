"""Domain state machine policy for loan lifecycle transitions."""

from __future__ import annotations

from typing import Final
from uuid import UUID


class LoanStatus:
    """Allowed lifecycle statuses for a copy loan."""

    REQUESTED: Final[str] = "requested"
    APPROVED: Final[str] = "approved"
    REJECTED: Final[str] = "rejected"
    CHECKED_OUT: Final[str] = "checked_out"
    RETURNED: Final[str] = "returned"
    CANCELLED: Final[str] = "cancelled"
    OVERDUE: Final[str] = "overdue"

    ALL: Final[frozenset[str]] = frozenset(
        {REQUESTED, APPROVED, REJECTED, CHECKED_OUT, RETURNED, CANCELLED, OVERDUE}
    )


ALLOWED_LOAN_TRANSITIONS: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        (LoanStatus.REQUESTED, LoanStatus.APPROVED),
        (LoanStatus.REQUESTED, LoanStatus.REJECTED),
        (LoanStatus.REQUESTED, LoanStatus.CANCELLED),
        (LoanStatus.APPROVED, LoanStatus.CHECKED_OUT),
        (LoanStatus.APPROVED, LoanStatus.CANCELLED),
        (LoanStatus.CHECKED_OUT, LoanStatus.RETURNED),
        (LoanStatus.CHECKED_OUT, LoanStatus.OVERDUE),
        (LoanStatus.OVERDUE, LoanStatus.RETURNED),
    }
)


class InvalidLoanStatusTransitionError(Exception):
    """Raised when a loan status change violates the allowed transition policy."""

    problem_type: Final[str] = (
        "https://openlibraryos.example/problems/invalid-loan-status-transition"
    )
    status_code: Final[int] = 409
    title: Final[str] = "Invalid loan status transition"

    def __init__(self, from_status: str, to_status: str) -> None:
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(
            f"Cannot transition loan status from '{from_status}' to '{to_status}'."
        )


class CopyNotAvailableForLoanError(Exception):
    """Raised when an attempt is made to borrow a copy not in available status."""

    problem_type: Final[str] = (
        "https://openlibraryos.example/problems/copy-not-available"
    )
    status_code: Final[int] = 409
    title: Final[str] = "Copy not available"

    def __init__(self, copy_id: UUID, current_status: str) -> None:
        self.copy_id = copy_id
        self.current_status = current_status
        super().__init__(
            f"Copy {copy_id} is in status '{current_status}' and cannot be borrowed."
        )


class ActiveLoanLimitExceededError(Exception):
    """Raised when a borrower exceeds the active loan limit."""

    problem_type: Final[str] = (
        "https://openlibraryos.example/problems/loan-not-eligible"
    )
    status_code: Final[int] = 409
    title: Final[str] = "Loan request rejected"

    def __init__(
        self, message: str = "The borrower has reached the active loan limit."
    ) -> None:
        super().__init__(message)


class LoanNotFoundError(KeyError):
    """Raised when a loan is not found within the tenant."""

    problem_type: Final[str] = "https://openlibraryos.example/problems/not-found"
    status_code: Final[int] = 404
    title: Final[str] = "Loan not found"

    def __init__(self, loan_id: UUID) -> None:
        self.loan_id = loan_id
        super().__init__(f"Loan {loan_id} not found.")


def is_allowed_loan_transition(from_status: str, to_status: str) -> bool:
    """Return True if the loan status transition is permitted."""
    return (from_status, to_status) in ALLOWED_LOAN_TRANSITIONS


def validate_loan_transition(from_status: str, to_status: str) -> None:
    """Validate that transition is allowed; raise InvalidLoanStatusTransitionError if not."""
    if not is_allowed_loan_transition(from_status, to_status):
        raise InvalidLoanStatusTransitionError(from_status, to_status)
