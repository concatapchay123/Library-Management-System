"""Domain state machine policy for physical copy status transitions."""

from __future__ import annotations

from typing import Final


class CopyStatus:
    """Allowed lifecycle statuses for an individually tracked book copy."""

    AVAILABLE: Final[str] = "available"
    BORROWED: Final[str] = "borrowed"
    LOST: Final[str] = "lost"
    DAMAGED: Final[str] = "damaged"
    MAINTENANCE: Final[str] = "maintenance"

    ALL: Final[frozenset[str]] = frozenset(
        {AVAILABLE, BORROWED, LOST, DAMAGED, MAINTENANCE}
    )


# Explicit allowed status transitions
ALLOWED_TRANSITIONS: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        # From available
        (CopyStatus.AVAILABLE, CopyStatus.BORROWED),
        (CopyStatus.AVAILABLE, CopyStatus.MAINTENANCE),
        (CopyStatus.AVAILABLE, CopyStatus.DAMAGED),
        (CopyStatus.AVAILABLE, CopyStatus.LOST),
        # From borrowed
        (CopyStatus.BORROWED, CopyStatus.AVAILABLE),
        (CopyStatus.BORROWED, CopyStatus.MAINTENANCE),
        (CopyStatus.BORROWED, CopyStatus.DAMAGED),
        (CopyStatus.BORROWED, CopyStatus.LOST),
        # From maintenance
        (CopyStatus.MAINTENANCE, CopyStatus.AVAILABLE),
        (CopyStatus.MAINTENANCE, CopyStatus.DAMAGED),
        (CopyStatus.MAINTENANCE, CopyStatus.LOST),
        # From damaged
        (CopyStatus.DAMAGED, CopyStatus.AVAILABLE),
        (CopyStatus.DAMAGED, CopyStatus.MAINTENANCE),
        (CopyStatus.DAMAGED, CopyStatus.LOST),
        # From lost
        (CopyStatus.LOST, CopyStatus.AVAILABLE),
        (CopyStatus.LOST, CopyStatus.MAINTENANCE),
        (CopyStatus.LOST, CopyStatus.DAMAGED),
    }
)


class InvalidCopyStatusTransitionError(Exception):
    """Raised when a copy status change violates the allowed transition policy."""

    problem_type: Final[str] = (
        "https://openlibraryos.example/problems/invalid-copy-status-transition"
    )
    status_code: Final[int] = 409
    title: Final[str] = "Invalid copy status transition"

    def __init__(self, from_status: str, to_status: str) -> None:
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(
            f"Cannot transition copy status from '{from_status}' to '{to_status}'."
        )


def is_allowed_transition(from_status: str, to_status: str) -> bool:
    """Return True if the transition from from_status to to_status is allowed."""
    return (from_status, to_status) in ALLOWED_TRANSITIONS


def validate_transition(from_status: str, to_status: str) -> None:
    """Validate that transition is allowed; raise InvalidCopyStatusTransitionError if not."""
    if not is_allowed_transition(from_status, to_status):
        raise InvalidCopyStatusTransitionError(from_status, to_status)
