"""Unit tests for reservation domain transitions, allocator, and application service."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import threading
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
from openlibrary.modules.core.application.reservations import (
    Reservation,
    ReservationService,
    ReservationStore,
)
from openlibrary.modules.core.domain.copy_status import CopyStatus
from openlibrary.modules.core.domain.reservations import (
    ActiveReservationLimitExceededError,
    InvalidReservationStatusTransitionError,
    ReservationNotEligibleForClaimError,
    ReservationNotFoundError,
    ReservationStatus,
    validate_reservation_transition,
)
from openlibrary.modules.ops.application.persistence import (
    AuditEvent,
    AuditedTransaction,
    OutboxEvent,
)

ORG_A = uuid4()
ORG_B = uuid4()
PATRON_1 = uuid4()
PATRON_2 = uuid4()
PATRON_3 = uuid4()
LIBRARIAN_ID = uuid4()

ACTOR_PATRON_1 = Principal(PATRON_1, ORG_A, uuid4())
ACTOR_PATRON_2 = Principal(PATRON_2, ORG_A, uuid4())
ACTOR_PATRON_3 = Principal(PATRON_3, ORG_A, uuid4())
ACTOR_LIBRARIAN = Principal(LIBRARIAN_ID, ORG_A, uuid4())


class _AllowAllAuthorizer(AuthorizationPort):
    def require(self, principal: Principal, permission: str) -> None:
        pass


class _DenyAllAuthorizer(AuthorizationPort):
    def require(self, principal: Principal, permission: str) -> None:
        raise AuthorizationDenied(f"Permission denied: {permission}")


class _ConfigurableAuthorizer(AuthorizationPort):
    def __init__(self, allowed: set[tuple[UUID, str]] | None = None) -> None:
        self._allowed = allowed or set()

    def allow(self, principal: Principal, permission: str) -> None:
        self._allowed.add((principal.user_id, permission))

    def require(self, principal: Principal, permission: str) -> None:
        if (principal.user_id, permission) not in self._allowed:
            raise AuthorizationDenied(f"Permission denied: {permission}")


@dataclass
class _InMemoryReservationStore(ReservationStore):
    reservations: dict[UUID, Reservation] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def create_reservation(self, reservation: Reservation) -> Reservation:
        with self._lock:
            self.reservations[reservation.reservation_id] = reservation
            return reservation

    def get_reservation(
        self, organization_id: UUID, reservation_id: UUID
    ) -> Reservation:
        with self._lock:
            res = self.reservations.get(reservation_id)
            if res is None or res.organization_id != organization_id:
                raise ReservationNotFoundError(reservation_id)
            return res

    def update_reservation(self, reservation: Reservation) -> Reservation:
        with self._lock:
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
        with self._lock:
            results = [
                r
                for r in self.reservations.values()
                if r.organization_id == organization_id
            ]
            if book_id is not None:
                results = [r for r in results if r.book_id == book_id]
            if requester_user_id is not None:
                results = [
                    r for r in results if r.requester_user_id == requester_user_id
                ]
            if status is not None:
                results = [r for r in results if r.status == status]
            return sorted(
                results,
                key=lambda r: (r.queue_position, r.created_at, r.reservation_id),
            )

    def get_next_queue_position(self, organization_id: UUID, book_id: UUID) -> int:
        with self._lock:
            existing = [
                r.queue_position
                for r in self.reservations.values()
                if r.organization_id == organization_id and r.book_id == book_id
            ]
            return (max(existing) + 1) if existing else 1

    def get_next_pending_reservation(
        self, organization_id: UUID, book_id: UUID
    ) -> Reservation | None:
        with self._lock:
            pending = [
                r
                for r in self.reservations.values()
                if r.organization_id == organization_id
                and r.book_id == book_id
                and r.status == ReservationStatus.PENDING
            ]
            if not pending:
                return None
            pending.sort(
                key=lambda r: (r.queue_position, r.created_at, r.reservation_id)
            )
            return pending[0]

    def get_active_reservation_for_user_and_book(
        self, organization_id: UUID, book_id: UUID, user_id: UUID
    ) -> Reservation | None:
        with self._lock:
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
        with self._lock:
            return [
                r
                for r in self.reservations.values()
                if r.organization_id == organization_id
                and r.status == ReservationStatus.HELD
                and r.hold_expires_at is not None
                and r.hold_expires_at <= now
            ]


@dataclass
class _InMemoryCopyStore(CopyStatusStore):
    copies: dict[UUID, BookCopy] = field(default_factory=dict)
    history: list[CopyStatusHistory] = field(default_factory=list)
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def get_copy(self, organization_id: UUID, copy_id: UUID) -> BookCopy:
        with self._lock:
            copy = self.copies.get(copy_id)
            if copy is None or copy.organization_id != organization_id:
                raise KeyError(copy_id)
            return copy

    def update_copy_status(
        self, organization_id: UUID, copy_id: UUID, to_status: str
    ) -> BookCopy:
        with self._lock:
            copy = self.get_copy(organization_id, copy_id)
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
                updated_at=datetime.now(timezone.utc),
            )
            self.copies[copy_id] = updated
            return updated

    def append_history(self, history: CopyStatusHistory) -> None:
        with self._lock:
            self.history.append(history)

    def get_copy_for_update_in_connection(
        self, connection: Any, organization_id: UUID, copy_id: UUID
    ) -> BookCopy:
        return self.get_copy(organization_id, copy_id)

    def get_available_copy_for_book(
        self, organization_id: UUID, book_id: UUID
    ) -> BookCopy | None:
        with self._lock:
            for copy in self.copies.values():
                if (
                    copy.organization_id == organization_id
                    and copy.book_id == book_id
                    and copy.status == CopyStatus.AVAILABLE
                ):
                    return copy
            return None


@dataclass
class _RecordingTransaction(AuditedTransaction):
    audit_events: list[AuditEvent] = field(default_factory=list)
    outbox_events: list[OutboxEvent] = field(default_factory=list)

    def run(
        self,
        connection: Any,
        mutation: Any,
        audit_event: AuditEvent,
        outbox_events: tuple[OutboxEvent, ...] = (),
    ) -> Any:
        result = mutation(connection)
        self.audit_events.append(audit_event)
        self.outbox_events.extend(outbox_events)
        return result


def test_reservation_status_transition_rules() -> None:
    # Valid transitions
    validate_reservation_transition(ReservationStatus.PENDING, ReservationStatus.HELD)
    validate_reservation_transition(
        ReservationStatus.PENDING, ReservationStatus.CANCELLED
    )
    validate_reservation_transition(ReservationStatus.HELD, ReservationStatus.FULFILLED)
    validate_reservation_transition(ReservationStatus.HELD, ReservationStatus.CANCELLED)
    validate_reservation_transition(ReservationStatus.HELD, ReservationStatus.EXPIRED)

    # Invalid transitions
    with pytest.raises(InvalidReservationStatusTransitionError):
        validate_reservation_transition(
            ReservationStatus.PENDING, ReservationStatus.FULFILLED
        )
    with pytest.raises(InvalidReservationStatusTransitionError):
        validate_reservation_transition(
            ReservationStatus.FULFILLED, ReservationStatus.PENDING
        )
    with pytest.raises(InvalidReservationStatusTransitionError):
        validate_reservation_transition(
            ReservationStatus.CANCELLED, ReservationStatus.HELD
        )
    with pytest.raises(InvalidReservationStatusTransitionError):
        validate_reservation_transition(
            ReservationStatus.EXPIRED, ReservationStatus.HELD
        )


def test_create_reservation_deterministic_queue_position() -> None:
    store = _InMemoryReservationStore()
    copy_store = _InMemoryCopyStore()
    tx = _RecordingTransaction()
    book_id = uuid4()

    service = ReservationService(
        reservation_store=store,
        copy_store=copy_store,
        authorizer=_AllowAllAuthorizer(),
        transaction=tx,
    )

    r1 = service.create_reservation(actor=ACTOR_PATRON_1, book_id=book_id)
    r2 = service.create_reservation(actor=ACTOR_PATRON_2, book_id=book_id)
    r3 = service.create_reservation(actor=ACTOR_PATRON_3, book_id=book_id)

    assert r1.queue_position == 1
    assert r2.queue_position == 2
    assert r3.queue_position == 3
    assert r1.status == ReservationStatus.PENDING
    assert r2.status == ReservationStatus.PENDING
    assert r3.status == ReservationStatus.PENDING

    assert len(tx.audit_events) == 3
    assert all(a.action == "reservation.created" for a in tx.audit_events)
    assert len(tx.outbox_events) == 3
    assert all(
        o.event_type == "circulation.reservation_created" for o in tx.outbox_events
    )


def test_create_reservation_rejects_duplicate_active_reservation() -> None:
    store = _InMemoryReservationStore()
    copy_store = _InMemoryCopyStore()
    tx = _RecordingTransaction()
    book_id = uuid4()

    service = ReservationService(
        reservation_store=store,
        copy_store=copy_store,
        authorizer=_AllowAllAuthorizer(),
        transaction=tx,
    )

    service.create_reservation(actor=ACTOR_PATRON_1, book_id=book_id)

    with pytest.raises(ActiveReservationLimitExceededError):
        service.create_reservation(actor=ACTOR_PATRON_1, book_id=book_id)


def test_create_reservation_auto_allocates_when_copy_available() -> None:
    store = _InMemoryReservationStore()
    copy_store = _InMemoryCopyStore()
    tx = _RecordingTransaction()
    book_id = uuid4()
    copy_id = uuid4()

    # Seed an available copy
    copy_store.copies[copy_id] = BookCopy(
        copy_id=copy_id,
        organization_id=ORG_A,
        book_id=book_id,
        barcode="BC-001",
        location_id=uuid4(),
        status=CopyStatus.AVAILABLE,
        condition_code="good",
        acquired_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    service = ReservationService(
        reservation_store=store,
        copy_store=copy_store,
        authorizer=_AllowAllAuthorizer(),
        transaction=tx,
        hold_duration_hours=48,
    )

    r1 = service.create_reservation(actor=ACTOR_PATRON_1, book_id=book_id)
    assert r1.status == ReservationStatus.HELD
    assert r1.copy_id == copy_id
    assert r1.hold_expires_at is not None
    assert copy_store.copies[copy_id].status == CopyStatus.RESERVED

    # Outbox events include created and allocated
    event_types = [o.event_type for o in tx.outbox_events]
    assert "circulation.reservation_created" in event_types
    assert "circulation.reservation_allocated" in event_types


def test_cancel_held_reservation_frees_copy_and_advances_queue() -> None:
    store = _InMemoryReservationStore()
    copy_store = _InMemoryCopyStore()
    tx = _RecordingTransaction()
    book_id = uuid4()
    copy_id = uuid4()

    copy_store.copies[copy_id] = BookCopy(
        copy_id=copy_id,
        organization_id=ORG_A,
        book_id=book_id,
        barcode="BC-001",
        location_id=uuid4(),
        status=CopyStatus.AVAILABLE,
        condition_code="good",
        acquired_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    service = ReservationService(
        reservation_store=store,
        copy_store=copy_store,
        authorizer=_AllowAllAuthorizer(),
        transaction=tx,
    )

    r1 = service.create_reservation(actor=ACTOR_PATRON_1, book_id=book_id)
    r2 = service.create_reservation(actor=ACTOR_PATRON_2, book_id=book_id)

    assert r1.status == ReservationStatus.HELD
    assert r1.copy_id == copy_id
    assert r2.status == ReservationStatus.PENDING

    # Patron 1 cancels held reservation
    cancelled_r1 = service.cancel_reservation(
        actor=ACTOR_PATRON_1, reservation_id=r1.reservation_id
    )
    assert cancelled_r1.status == ReservationStatus.CANCELLED

    # Checkpoint: Next pending reservation (r2) is automatically advanced to HELD!
    updated_r2 = store.get_reservation(ORG_A, r2.reservation_id)
    assert updated_r2.status == ReservationStatus.HELD
    assert updated_r2.copy_id == copy_id
    assert copy_store.copies[copy_id].status == CopyStatus.RESERVED


def test_claim_held_reservation() -> None:
    store = _InMemoryReservationStore()
    copy_store = _InMemoryCopyStore()
    tx = _RecordingTransaction()
    book_id = uuid4()
    copy_id = uuid4()

    copy_store.copies[copy_id] = BookCopy(
        copy_id=copy_id,
        organization_id=ORG_A,
        book_id=book_id,
        barcode="BC-001",
        location_id=uuid4(),
        status=CopyStatus.AVAILABLE,
        condition_code="good",
        acquired_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    service = ReservationService(
        reservation_store=store,
        copy_store=copy_store,
        authorizer=_AllowAllAuthorizer(),
        transaction=tx,
    )

    r1 = service.create_reservation(actor=ACTOR_PATRON_1, book_id=book_id)
    assert r1.status == ReservationStatus.HELD

    # Claim reservation
    claimed = service.claim_reservation(
        actor=ACTOR_PATRON_1, reservation_id=r1.reservation_id
    )
    assert claimed.status == ReservationStatus.FULFILLED
    assert copy_store.copies[copy_id].status == CopyStatus.BORROWED


def test_claim_pending_reservation_raises_error() -> None:
    store = _InMemoryReservationStore()
    copy_store = _InMemoryCopyStore()
    tx = _RecordingTransaction()
    book_id = uuid4()

    service = ReservationService(
        reservation_store=store,
        copy_store=copy_store,
        authorizer=_AllowAllAuthorizer(),
        transaction=tx,
    )

    r1 = service.create_reservation(actor=ACTOR_PATRON_1, book_id=book_id)
    assert r1.status == ReservationStatus.PENDING

    with pytest.raises(ReservationNotEligibleForClaimError):
        service.claim_reservation(
            actor=ACTOR_PATRON_1, reservation_id=r1.reservation_id
        )


def test_expire_holds_advances_exactly_one_eligible_next_reservation() -> None:
    store = _InMemoryReservationStore()
    copy_store = _InMemoryCopyStore()
    tx = _RecordingTransaction()
    book_id = uuid4()
    copy_id = uuid4()

    copy_store.copies[copy_id] = BookCopy(
        copy_id=copy_id,
        organization_id=ORG_A,
        book_id=book_id,
        barcode="BC-001",
        location_id=uuid4(),
        status=CopyStatus.AVAILABLE,
        condition_code="good",
        acquired_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    service = ReservationService(
        reservation_store=store,
        copy_store=copy_store,
        authorizer=_AllowAllAuthorizer(),
        transaction=tx,
    )

    r1 = service.create_reservation(actor=ACTOR_PATRON_1, book_id=book_id)
    r2 = service.create_reservation(actor=ACTOR_PATRON_2, book_id=book_id)
    r3 = service.create_reservation(actor=ACTOR_PATRON_3, book_id=book_id)

    assert r1.status == ReservationStatus.HELD
    assert r2.status == ReservationStatus.PENDING
    assert r3.status == ReservationStatus.PENDING

    # Manually backdate hold_expires_at
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    r1_expired_state = Reservation(
        reservation_id=r1.reservation_id,
        organization_id=r1.organization_id,
        book_id=r1.book_id,
        requester_user_id=r1.requester_user_id,
        copy_id=r1.copy_id,
        queue_position=r1.queue_position,
        status=ReservationStatus.HELD,
        hold_expires_at=past,
        created_at=r1.created_at,
        updated_at=r1.updated_at,
    )
    store.update_reservation(r1_expired_state)

    # Run hold expiration
    expired_count = service.expire_holds(actor=ACTOR_LIBRARIAN)
    assert expired_count == 1

    # Checkpoint: r1 expired, r2 advanced to HELD, r3 remains PENDING
    assert (
        store.get_reservation(ORG_A, r1.reservation_id).status
        == ReservationStatus.EXPIRED
    )
    assert (
        store.get_reservation(ORG_A, r2.reservation_id).status == ReservationStatus.HELD
    )
    assert store.get_reservation(ORG_A, r2.reservation_id).copy_id == copy_id
    assert (
        store.get_reservation(ORG_A, r3.reservation_id).status
        == ReservationStatus.PENDING
    )
    assert store.get_reservation(ORG_A, r3.reservation_id).copy_id is None
