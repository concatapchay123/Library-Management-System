"""Domain entities, status transitions, and rules for reservations."""

from __future__ import annotations

from typing import Final
from uuid import UUID


class ReservationStatus:
    """Allowed lifecycle statuses for a book reservation."""

    PENDING: Final[str] = "pending"
    HELD: Final[str] = "held"
    FULFILLED: Final[str] = "fulfilled"
    CANCELLED: Final[str] = "cancelled"
    EXPIRED: Final[str] = "expired"

    ALL: Final[frozenset[str]] = frozenset(
        {PENDING, HELD, FULFILLED, CANCELLED, EXPIRED}
    )


ALLOWED_RESERVATION_TRANSITIONS: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        (ReservationStatus.PENDING, ReservationStatus.HELD),
        (ReservationStatus.PENDING, ReservationStatus.CANCELLED),
        (ReservationStatus.HELD, ReservationStatus.FULFILLED),
        (ReservationStatus.HELD, ReservationStatus.CANCELLED),
        (ReservationStatus.HELD, ReservationStatus.EXPIRED),
    }
)


def is_allowed_reservation_transition(from_status: str, to_status: str) -> bool:
    """Return True if the status transition is permitted by domain policy."""
    return (from_status, to_status) in ALLOWED_RESERVATION_TRANSITIONS


def validate_reservation_transition(from_status: str, to_status: str) -> None:
    """Raise InvalidReservationStatusTransitionError if the transition is forbidden."""
    if not is_allowed_reservation_transition(from_status, to_status):
        raise InvalidReservationStatusTransitionError(from_status, to_status)


class ReservationNotFoundError(Exception):
    """Raised when a reservation does not exist in the tenant context."""

    problem_type: Final[str] = (
        "https://openlibraryos.example/problems/reservation-not-found"
    )
    status_code: Final[int] = 404
    title: Final[str] = "Reservation not found"

    def __init__(self, reservation_id: UUID) -> None:
        super().__init__(f"Reservation {reservation_id} does not exist in this tenant")
        self.reservation_id = reservation_id


class InvalidReservationStatusTransitionError(Exception):
    """Raised when an illegal reservation state transition is attempted."""

    problem_type: Final[str] = (
        "https://openlibraryos.example/problems/invalid-reservation-status-transition"
    )
    status_code: Final[int] = 409
    title: Final[str] = "Invalid reservation status transition"

    def __init__(self, from_status: str, to_status: str) -> None:
        super().__init__(
            f"Cannot transition reservation from '{from_status}' to '{to_status}'"
        )
        self.from_status = from_status
        self.to_status = to_status


class ActiveReservationLimitExceededError(Exception):
    """Raised when a patron already holds an active reservation for the book."""

    problem_type: Final[str] = (
        "https://openlibraryos.example/problems/active-reservation-limit-exceeded"
    )
    status_code: Final[int] = 409
    title: Final[str] = "Active reservation limit exceeded"

    def __init__(
        self, message: str = "User already has an active reservation for this book"
    ) -> None:
        super().__init__(message)


class ReservationNotEligibleForClaimError(Exception):
    """Raised when attempting to claim a reservation that is not in held status."""

    problem_type: Final[str] = (
        "https://openlibraryos.example/problems/reservation-not-eligible-for-claim"
    )
    status_code: Final[int] = 409
    title: Final[str] = "Reservation not eligible for claim"

    def __init__(self, reservation_id: UUID, current_status: str) -> None:
        super().__init__(
            f"Reservation {reservation_id} is in status '{current_status}', expected 'held'"
        )
        self.reservation_id = reservation_id
        self.current_status = current_status


class CopyNotAvailableForReservationError(Exception):
    """Raised when allocating a copy that is not in available status."""

    problem_type: Final[str] = (
        "https://openlibraryos.example/problems/copy-not-available-for-reservation"
    )
    status_code: Final[int] = 409
    title: Final[str] = "Copy not available for reservation"

    def __init__(self, copy_id: UUID, current_status: str) -> None:
        super().__init__(
            f"Copy {copy_id} is in status '{current_status}', expected 'available'"
        )
        self.copy_id = copy_id
        self.current_status = current_status
