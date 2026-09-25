"""Application service, allocator, and ports for the reservation queue."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import logging
from typing import Any, Protocol
from uuid import UUID, uuid4

from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.authorization import (
    AuthorizationDenied,
    AuthorizationPort,
)
from openlibrary.modules.core.application.copy_status import (
    CopyStatusHistory,
    CopyStatusStore,
)
from openlibrary.modules.core.domain.copy_status import (
    CopyStatus,
    validate_transition,
)
from openlibrary.modules.core.domain.reservations import (
    ActiveReservationLimitExceededError,
    ReservationNotEligibleForClaimError,
    ReservationStatus,
    validate_reservation_transition,
)
from openlibrary.modules.ops.application.dispatcher import ConsumerDeduplicationPort
from openlibrary.modules.ops.application.persistence import (
    AuditEvent,
    AuditedTransaction,
    ClaimedOutboxEvent,
    OutboxEvent,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Reservation:
    """Persistent representation of a patron reservation."""

    reservation_id: UUID
    organization_id: UUID
    book_id: UUID
    requester_user_id: UUID
    queue_position: int
    status: str
    created_at: datetime
    updated_at: datetime
    copy_id: UUID | None = None
    hold_expires_at: datetime | None = None


class ReservationStore(Protocol):
    """Port for tenant-scoped reservation persistence."""

    def create_reservation(self, reservation: Reservation) -> Reservation:
        """Create a new reservation."""
        ...

    def get_reservation(
        self, organization_id: UUID, reservation_id: UUID
    ) -> Reservation:
        """Retrieve a reservation by ID within the tenant context."""
        ...

    def update_reservation(self, reservation: Reservation) -> Reservation:
        """Update an existing reservation record."""
        ...

    def list_reservations(
        self,
        organization_id: UUID,
        *,
        book_id: UUID | None = None,
        requester_user_id: UUID | None = None,
        status: str | None = None,
    ) -> list[Reservation]:
        """List reservations within the tenant matching criteria."""
        ...

    def get_next_queue_position(self, organization_id: UUID, book_id: UUID) -> int:
        """Determine next sequential queue position for a book in this tenant."""
        ...

    def get_next_pending_reservation(
        self, organization_id: UUID, book_id: UUID
    ) -> Reservation | None:
        """Fetch the top pending reservation in queue for a book."""
        ...

    def get_active_reservation_for_user_and_book(
        self, organization_id: UUID, book_id: UUID, user_id: UUID
    ) -> Reservation | None:
        """Return active (pending or held) reservation if one exists for user and book."""
        ...

    def list_expired_holds(
        self, organization_id: UUID, now: datetime
    ) -> list[Reservation]:
        """List all held reservations where hold_expires_at is on or before now."""
        ...


class ReservationAllocator:
    """Allocates available copies to eligible pending reservations deterministically."""

    def __init__(
        self,
        *,
        reservation_store: ReservationStore,
        copy_store: CopyStatusStore,
        transaction: AuditedTransaction | None = None,
        connection_provider: Callable[[UUID], AbstractContextManager[object]]
        | None = None,
        hold_duration_hours: int = 48,
    ) -> None:
        self._reservation_store = reservation_store
        self._copy_store = copy_store
        self._transaction = transaction
        self._connection_provider = connection_provider
        self._hold_duration_hours = hold_duration_hours

    def allocate_copy_for_book(
        self,
        *,
        organization_id: UUID,
        book_id: UUID,
        copy_id: UUID,
        trigger_event_id: UUID | None = None,
    ) -> Reservation | None:
        """Allocate available copy to top pending reservation for the book."""
        if self._connection_provider is not None:
            with self._connection_provider(organization_id) as conn:
                return self.allocate_copy_for_book_in_connection(
                    conn,
                    organization_id=organization_id,
                    book_id=book_id,
                    copy_id=copy_id,
                    trigger_event_id=trigger_event_id,
                )
        return self.allocate_copy_for_book_in_connection(
            None,
            organization_id=organization_id,
            book_id=book_id,
            copy_id=copy_id,
            trigger_event_id=trigger_event_id,
        )

    def allocate_copy_for_book_in_connection(
        self,
        connection: object,
        *,
        organization_id: UUID,
        book_id: UUID,
        copy_id: UUID,
        trigger_event_id: UUID | None = None,
    ) -> Reservation | None:
        """Atomically lock copy, find top pending reservation, and transition both to held/reserved."""
        if hasattr(self._copy_store, "get_copy_for_update_in_connection"):
            copy = getattr(self._copy_store, "get_copy_for_update_in_connection")(
                connection, organization_id, copy_id
            )
        else:
            copy = self._copy_store.get_copy(organization_id, copy_id)

        if copy is None or copy.status != CopyStatus.AVAILABLE:
            return None

        # Lock and retrieve next eligible pending reservation
        if hasattr(
            self._reservation_store,
            "get_next_pending_reservation_for_update_in_connection",
        ):
            top_res = getattr(
                self._reservation_store,
                "get_next_pending_reservation_for_update_in_connection",
            )(connection, organization_id, book_id)
        else:
            top_res = self._reservation_store.get_next_pending_reservation(
                organization_id, book_id
            )

        if top_res is None:
            return None

        now = datetime.now(timezone.utc)
        hold_expires_at = now + timedelta(hours=self._hold_duration_hours)

        validate_reservation_transition(top_res.status, ReservationStatus.HELD)
        validate_transition(copy.status, CopyStatus.RESERVED)

        updated_res = Reservation(
            reservation_id=top_res.reservation_id,
            organization_id=organization_id,
            book_id=book_id,
            requester_user_id=top_res.requester_user_id,
            queue_position=top_res.queue_position,
            status=ReservationStatus.HELD,
            created_at=top_res.created_at,
            updated_at=now,
            copy_id=copy_id,
            hold_expires_at=hold_expires_at,
        )

        history_record = CopyStatusHistory(
            history_id=uuid4(),
            organization_id=organization_id,
            copy_id=copy.copy_id,
            from_status=copy.status,
            to_status=CopyStatus.RESERVED,
            reason=f"Held for reservation {top_res.reservation_id}",
            actor_id=top_res.requester_user_id,
            created_at=now,
        )

        # Mutate copy and reservation
        if hasattr(self._copy_store, "record_transition_in_connection"):
            getattr(self._copy_store, "record_transition_in_connection")(
                connection,
                organization_id=organization_id,
                copy_id=copy.copy_id,
                to_status=CopyStatus.RESERVED,
                history_record=history_record,
            )
        else:
            self._copy_store.update_copy_status(
                organization_id, copy.copy_id, CopyStatus.RESERVED
            )
            self._copy_store.append_history(history_record)

        if hasattr(self._reservation_store, "record_update_reservation_in_connection"):
            saved_res = getattr(
                self._reservation_store, "record_update_reservation_in_connection"
            )(connection, updated_res)
        else:
            saved_res = self._reservation_store.update_reservation(updated_res)

        audit_correlation = trigger_event_id or uuid4()
        audit_event = AuditEvent(
            action="reservation.allocated",
            entity_type="reservation",
            entity_id=saved_res.reservation_id,
            payload={
                "reservation_id": str(saved_res.reservation_id),
                "copy_id": str(copy_id),
                "book_id": str(book_id),
                "requester_user_id": str(saved_res.requester_user_id),
                "hold_expires_at": hold_expires_at.isoformat(),
                "status": ReservationStatus.HELD,
            },
            correlation_id=audit_correlation,
            actor_user_id=saved_res.requester_user_id,
            actor_type="system",
        )
        outbox_event = OutboxEvent(
            event_type="circulation.reservation_allocated",
            aggregate_type="reservation",
            aggregate_id=saved_res.reservation_id,
            payload_version=1,
            payload={
                "reservation_id": str(saved_res.reservation_id),
                "organization_id": str(organization_id),
                "book_id": str(book_id),
                "copy_id": str(copy_id),
                "requester_user_id": str(saved_res.requester_user_id),
                "hold_expires_at": hold_expires_at.isoformat(),
            },
            correlation_id=audit_correlation,
            idempotency_key=f"reservation:{saved_res.reservation_id}:allocated:{trigger_event_id or now.isoformat()}",
        )

        if self._transaction is not None and connection is not None:
            if hasattr(self._transaction, "record_events_in_connection"):
                getattr(self._transaction, "record_events_in_connection")(
                    connection, audit_event, (outbox_event,)
                )

        return saved_res  # type: ignore[no-any-return]


class ReservationService:
    """Manages reservation lifecycle: create, cancel, claim, and durable hold expiry."""

    _PERM_CREATE = "reservation.create"
    _PERM_READ = "reservation.read"
    _PERM_MANAGE = "reservation.manage"
    _PERM_CHECKOUT = "circulation.checkout"

    def __init__(
        self,
        *,
        reservation_store: ReservationStore,
        copy_store: CopyStatusStore,
        authorizer: AuthorizationPort,
        transaction: AuditedTransaction | None = None,
        connection_provider: Callable[[UUID], AbstractContextManager[object]]
        | None = None,
        hold_duration_hours: int = 48,
    ) -> None:
        self._reservation_store = reservation_store
        self._copy_store = copy_store
        self._authorizer = authorizer
        self._transaction = transaction
        self._connection_provider = connection_provider
        self._hold_duration_hours = hold_duration_hours
        self._allocator = ReservationAllocator(
            reservation_store=reservation_store,
            copy_store=copy_store,
            transaction=transaction,
            connection_provider=connection_provider,
            hold_duration_hours=hold_duration_hours,
        )

    def _require_perm(self, actor: Principal, permission: str) -> None:
        self._authorizer.require(actor, permission)

    def _allows(self, actor: Principal, permission: str) -> bool:
        try:
            self._authorizer.require(actor, permission)
            return True
        except AuthorizationDenied:
            return False

    def create_reservation(
        self,
        *,
        actor: Principal,
        book_id: UUID,
        copy_id: UUID | None = None,
        requester_user_id: UUID | None = None,
        correlation_id: UUID | None = None,
    ) -> Reservation:
        """Create a reservation with server-side deterministic queue position and auto-hold."""
        target_requester = requester_user_id or actor.user_id
        if target_requester != actor.user_id:
            self._require_perm(actor, self._PERM_MANAGE)
        else:
            self._require_perm(actor, self._PERM_CREATE)

        # Checkpoint: user cannot have duplicate active reservations for the same book
        existing = self._reservation_store.get_active_reservation_for_user_and_book(
            actor.organization_id, book_id, target_requester
        )
        if existing is not None:
            raise ActiveReservationLimitExceededError()

        now = datetime.now(timezone.utc)
        queue_pos = self._reservation_store.get_next_queue_position(
            actor.organization_id, book_id
        )

        reservation_id = uuid4()
        initial_status = ReservationStatus.PENDING
        allocated_copy_id: UUID | None = None
        hold_expires_at: datetime | None = None

        # Check if an available copy exists immediately for auto-allocation
        candidate_copy = None
        if hasattr(self._copy_store, "get_available_copy_for_book"):
            candidate_copy = self._copy_store.get_available_copy_for_book(
                actor.organization_id, book_id
            )

        events_to_emit: list[OutboxEvent] = []
        if candidate_copy is not None:
            initial_status = ReservationStatus.HELD
            allocated_copy_id = candidate_copy.copy_id
            hold_expires_at = now + timedelta(hours=self._hold_duration_hours)

        reservation = Reservation(
            reservation_id=reservation_id,
            organization_id=actor.organization_id,
            book_id=book_id,
            requester_user_id=target_requester,
            copy_id=allocated_copy_id,
            queue_position=queue_pos,
            status=initial_status,
            hold_expires_at=hold_expires_at,
            created_at=now,
            updated_at=now,
        )

        audit_correlation = correlation_id or uuid4()
        audit_event = AuditEvent(
            action="reservation.created",
            entity_type="reservation",
            entity_id=reservation_id,
            payload={
                "reservation_id": str(reservation_id),
                "book_id": str(book_id),
                "requester_user_id": str(target_requester),
                "queue_position": queue_pos,
                "status": initial_status,
                "copy_id": str(allocated_copy_id) if allocated_copy_id else None,
            },
            correlation_id=audit_correlation,
            actor_user_id=actor.user_id,
            actor_type="user",
        )
        events_to_emit.append(
            OutboxEvent(
                event_type="circulation.reservation_created",
                aggregate_type="reservation",
                aggregate_id=reservation_id,
                payload_version=1,
                payload={
                    "reservation_id": str(reservation_id),
                    "organization_id": str(actor.organization_id),
                    "book_id": str(book_id),
                    "requester_user_id": str(target_requester),
                    "queue_position": queue_pos,
                },
                correlation_id=audit_correlation,
                idempotency_key=f"reservation:{reservation_id}:created",
            )
        )
        if initial_status == ReservationStatus.HELD and allocated_copy_id is not None:
            events_to_emit.append(
                OutboxEvent(
                    event_type="circulation.reservation_allocated",
                    aggregate_type="reservation",
                    aggregate_id=reservation_id,
                    payload_version=1,
                    payload={
                        "reservation_id": str(reservation_id),
                        "organization_id": str(actor.organization_id),
                        "book_id": str(book_id),
                        "copy_id": str(allocated_copy_id),
                        "requester_user_id": str(target_requester),
                        "hold_expires_at": hold_expires_at.isoformat()
                        if hold_expires_at
                        else None,
                    },
                    correlation_id=audit_correlation,
                    idempotency_key=f"reservation:{reservation_id}:allocated",
                )
            )

        def _mutation(connection: object) -> Reservation:
            if candidate_copy is not None:
                history_record = CopyStatusHistory(
                    history_id=uuid4(),
                    organization_id=actor.organization_id,
                    copy_id=candidate_copy.copy_id,
                    from_status=candidate_copy.status,
                    to_status=CopyStatus.RESERVED,
                    reason=f"Held for reservation {reservation_id}",
                    actor_id=target_requester,
                    created_at=now,
                )
                if hasattr(self._copy_store, "record_transition_in_connection"):
                    getattr(self._copy_store, "record_transition_in_connection")(
                        connection,
                        organization_id=actor.organization_id,
                        copy_id=candidate_copy.copy_id,
                        to_status=CopyStatus.RESERVED,
                        history_record=history_record,
                    )
                else:
                    self._copy_store.update_copy_status(
                        actor.organization_id,
                        candidate_copy.copy_id,
                        CopyStatus.RESERVED,
                    )
                    self._copy_store.append_history(history_record)

            if hasattr(
                self._reservation_store, "record_create_reservation_in_connection"
            ):
                return getattr(  # type: ignore[no-any-return]
                    self._reservation_store,
                    "record_create_reservation_in_connection",
                )(connection, reservation)
            return self._reservation_store.create_reservation(reservation)

        if self._transaction is not None:
            if self._connection_provider is not None:
                with self._connection_provider(actor.organization_id) as conn:
                    return self._transaction.run(
                        conn,  # type: ignore[arg-type]
                        _mutation,
                        audit_event,
                        tuple(events_to_emit),
                    )
            return self._transaction.run(
                None,  # type: ignore[arg-type]
                _mutation,
                audit_event,
                tuple(events_to_emit),
            )
        return _mutation(None)

    def cancel_reservation(
        self,
        *,
        actor: Principal,
        reservation_id: UUID,
        correlation_id: UUID | None = None,
    ) -> Reservation:
        """Cancel a reservation. If held, frees the copy and advances next in queue without reordering unrelated entries."""
        current = self._reservation_store.get_reservation(
            actor.organization_id, reservation_id
        )
        if current.requester_user_id != actor.user_id:
            self._require_perm(actor, self._PERM_MANAGE)
        else:
            self._require_perm(actor, self._PERM_CREATE)

        validate_reservation_transition(current.status, ReservationStatus.CANCELLED)

        now = datetime.now(timezone.utc)
        updated = Reservation(
            reservation_id=current.reservation_id,
            organization_id=current.organization_id,
            book_id=current.book_id,
            requester_user_id=current.requester_user_id,
            copy_id=current.copy_id,
            queue_position=current.queue_position,
            status=ReservationStatus.CANCELLED,
            hold_expires_at=None,
            created_at=current.created_at,
            updated_at=now,
        )

        audit_correlation = correlation_id or uuid4()
        audit_event = AuditEvent(
            action="reservation.cancelled",
            entity_type="reservation",
            entity_id=reservation_id,
            payload={
                "reservation_id": str(reservation_id),
                "book_id": str(current.book_id),
                "status": ReservationStatus.CANCELLED,
            },
            correlation_id=audit_correlation,
            actor_user_id=actor.user_id,
            actor_type="user",
        )
        outbox_event = OutboxEvent(
            event_type="circulation.reservation_cancelled",
            aggregate_type="reservation",
            aggregate_id=reservation_id,
            payload_version=1,
            payload={
                "reservation_id": str(reservation_id),
                "organization_id": str(actor.organization_id),
                "book_id": str(current.book_id),
            },
            correlation_id=audit_correlation,
            idempotency_key=f"reservation:{reservation_id}:cancelled",
        )

        def _mutation(connection: object) -> Reservation:
            if hasattr(
                self._reservation_store, "record_update_reservation_in_connection"
            ):
                res = getattr(
                    self._reservation_store,
                    "record_update_reservation_in_connection",
                )(connection, updated)
            else:
                res = self._reservation_store.update_reservation(updated)

            # If reservation was held, free copy and advance to next pending reservation!
            if current.status == ReservationStatus.HELD and current.copy_id is not None:
                history_record = CopyStatusHistory(
                    history_id=uuid4(),
                    organization_id=actor.organization_id,
                    copy_id=current.copy_id,
                    from_status=CopyStatus.RESERVED,
                    to_status=CopyStatus.AVAILABLE,
                    reason=f"Hold released due to reservation cancellation {reservation_id}",
                    actor_id=actor.user_id,
                    created_at=now,
                )
                if hasattr(self._copy_store, "record_transition_in_connection"):
                    getattr(self._copy_store, "record_transition_in_connection")(
                        connection,
                        organization_id=actor.organization_id,
                        copy_id=current.copy_id,
                        to_status=CopyStatus.AVAILABLE,
                        history_record=history_record,
                    )
                else:
                    self._copy_store.update_copy_status(
                        actor.organization_id,
                        current.copy_id,
                        CopyStatus.AVAILABLE,
                    )
                    self._copy_store.append_history(history_record)

                # Allocate the newly freed copy to the next eligible in queue!
                self._allocator.allocate_copy_for_book_in_connection(
                    connection,
                    organization_id=actor.organization_id,
                    book_id=current.book_id,
                    copy_id=current.copy_id,
                    trigger_event_id=audit_correlation,
                )

            return res  # type: ignore[no-any-return]

        if self._transaction is not None:
            if self._connection_provider is not None:
                with self._connection_provider(actor.organization_id) as conn:
                    return self._transaction.run(
                        conn,  # type: ignore[arg-type]
                        _mutation,
                        audit_event,
                        (outbox_event,),
                    )
            return self._transaction.run(
                None,  # type: ignore[arg-type]
                _mutation,
                audit_event,
                (outbox_event,),
            )
        return _mutation(None)

    def claim_reservation(
        self,
        *,
        actor: Principal,
        reservation_id: UUID,
        correlation_id: UUID | None = None,
    ) -> Reservation:
        """Claim a held reservation, transitioning reservation to fulfilled and copy to borrowed."""
        current = self._reservation_store.get_reservation(
            actor.organization_id, reservation_id
        )
        if current.requester_user_id != actor.user_id:
            if not self._allows(actor, self._PERM_MANAGE):
                self._require_perm(actor, self._PERM_CHECKOUT)

        if current.status != ReservationStatus.HELD or current.copy_id is None:
            raise ReservationNotEligibleForClaimError(reservation_id, current.status)

        validate_reservation_transition(current.status, ReservationStatus.FULFILLED)

        copy = self._copy_store.get_copy(actor.organization_id, current.copy_id)
        validate_transition(copy.status, CopyStatus.BORROWED)

        now = datetime.now(timezone.utc)
        updated = Reservation(
            reservation_id=current.reservation_id,
            organization_id=current.organization_id,
            book_id=current.book_id,
            requester_user_id=current.requester_user_id,
            copy_id=current.copy_id,
            queue_position=current.queue_position,
            status=ReservationStatus.FULFILLED,
            hold_expires_at=None,
            created_at=current.created_at,
            updated_at=now,
        )

        history_record = CopyStatusHistory(
            history_id=uuid4(),
            organization_id=actor.organization_id,
            copy_id=copy.copy_id,
            from_status=copy.status,
            to_status=CopyStatus.BORROWED,
            reason=f"Claimed from reservation {reservation_id}",
            actor_id=actor.user_id,
            created_at=now,
        )

        audit_correlation = correlation_id or uuid4()
        audit_event = AuditEvent(
            action="reservation.claimed",
            entity_type="reservation",
            entity_id=reservation_id,
            payload={
                "reservation_id": str(reservation_id),
                "copy_id": str(current.copy_id),
                "book_id": str(current.book_id),
                "status": ReservationStatus.FULFILLED,
            },
            correlation_id=audit_correlation,
            actor_user_id=actor.user_id,
            actor_type="user",
        )
        outbox_event = OutboxEvent(
            event_type="circulation.reservation_claimed",
            aggregate_type="reservation",
            aggregate_id=reservation_id,
            payload_version=1,
            payload={
                "reservation_id": str(reservation_id),
                "organization_id": str(actor.organization_id),
                "copy_id": str(current.copy_id),
                "borrower_user_id": str(current.requester_user_id),
            },
            correlation_id=audit_correlation,
            idempotency_key=f"reservation:{reservation_id}:claimed",
        )

        def _mutation(connection: object) -> Reservation:
            if hasattr(self._copy_store, "record_transition_in_connection"):
                getattr(self._copy_store, "record_transition_in_connection")(
                    connection,
                    organization_id=actor.organization_id,
                    copy_id=copy.copy_id,
                    to_status=CopyStatus.BORROWED,
                    history_record=history_record,
                )
            else:
                self._copy_store.update_copy_status(
                    actor.organization_id, copy.copy_id, CopyStatus.BORROWED
                )
                self._copy_store.append_history(history_record)

            if hasattr(
                self._reservation_store, "record_update_reservation_in_connection"
            ):
                return getattr(  # type: ignore[no-any-return]
                    self._reservation_store,
                    "record_update_reservation_in_connection",
                )(connection, updated)
            return self._reservation_store.update_reservation(updated)

        if self._transaction is not None:
            if self._connection_provider is not None:
                with self._connection_provider(actor.organization_id) as conn:
                    return self._transaction.run(
                        conn,  # type: ignore[arg-type]
                        _mutation,
                        audit_event,
                        (outbox_event,),
                    )
            return self._transaction.run(
                None,  # type: ignore[arg-type]
                _mutation,
                audit_event,
                (outbox_event,),
            )
        return _mutation(None)

    def expire_holds(
        self,
        *,
        actor: Principal,
        now: datetime | None = None,
        correlation_id: UUID | None = None,
    ) -> int:
        """Durable hold expiry sweep: marks holds expired, frees copies, and advances next in queue."""
        effective_now = now or datetime.now(timezone.utc)
        expired_holds = self._reservation_store.list_expired_holds(
            actor.organization_id, effective_now
        )
        if not expired_holds:
            return 0

        expired_count = 0
        for hold in expired_holds:
            if hold.copy_id is None:
                continue

            held_copy_id: UUID = hold.copy_id
            audit_correlation = correlation_id or uuid4()
            updated = Reservation(
                reservation_id=hold.reservation_id,
                organization_id=hold.organization_id,
                book_id=hold.book_id,
                requester_user_id=hold.requester_user_id,
                copy_id=held_copy_id,
                queue_position=hold.queue_position,
                status=ReservationStatus.EXPIRED,
                hold_expires_at=hold.hold_expires_at,
                created_at=hold.created_at,
                updated_at=effective_now,
            )

            history_record = CopyStatusHistory(
                history_id=uuid4(),
                organization_id=actor.organization_id,
                copy_id=held_copy_id,
                from_status=CopyStatus.RESERVED,
                to_status=CopyStatus.AVAILABLE,
                reason=f"Hold expired on reservation {hold.reservation_id}",
                actor_id=actor.user_id,
                created_at=effective_now,
            )

            audit_event = AuditEvent(
                action="reservation.expired",
                entity_type="reservation",
                entity_id=hold.reservation_id,
                payload={
                    "reservation_id": str(hold.reservation_id),
                    "copy_id": str(held_copy_id),
                    "book_id": str(hold.book_id),
                    "status": ReservationStatus.EXPIRED,
                },
                correlation_id=audit_correlation,
                actor_user_id=actor.user_id,
                actor_type="system",
            )
            outbox_event = OutboxEvent(
                event_type="circulation.reservation_expired",
                aggregate_type="reservation",
                aggregate_id=hold.reservation_id,
                payload_version=1,
                payload={
                    "reservation_id": str(hold.reservation_id),
                    "organization_id": str(actor.organization_id),
                    "copy_id": str(held_copy_id),
                    "book_id": str(hold.book_id),
                },
                correlation_id=audit_correlation,
                idempotency_key=f"reservation:{hold.reservation_id}:expired",
            )

            def _expire_mutation(connection: object) -> None:
                # 1. Update reservation to expired
                if hasattr(
                    self._reservation_store,
                    "record_update_reservation_in_connection",
                ):
                    getattr(
                        self._reservation_store,
                        "record_update_reservation_in_connection",
                    )(connection, updated)
                else:
                    self._reservation_store.update_reservation(updated)

                # 2. Release copy to available
                if hasattr(self._copy_store, "record_transition_in_connection"):
                    getattr(self._copy_store, "record_transition_in_connection")(
                        connection,
                        organization_id=actor.organization_id,
                        copy_id=held_copy_id,
                        to_status=CopyStatus.AVAILABLE,
                        history_record=history_record,
                    )
                else:
                    self._copy_store.update_copy_status(
                        actor.organization_id,
                        held_copy_id,
                        CopyStatus.AVAILABLE,
                    )
                    self._copy_store.append_history(history_record)

                # 3. Checkpoint: Expired hold advances exactly one eligible next reservation!
                self._allocator.allocate_copy_for_book_in_connection(
                    connection,
                    organization_id=actor.organization_id,
                    book_id=hold.book_id,
                    copy_id=held_copy_id,
                    trigger_event_id=audit_correlation,
                )

            if self._transaction is not None:
                if self._connection_provider is not None:
                    with self._connection_provider(actor.organization_id) as conn:
                        self._transaction.run(
                            conn,  # type: ignore[arg-type]
                            _expire_mutation,
                            audit_event,
                            (outbox_event,),
                        )
                else:
                    self._transaction.run(
                        None,  # type: ignore[arg-type]
                        _expire_mutation,
                        audit_event,
                        (outbox_event,),
                    )
            else:
                _expire_mutation(None)

            expired_count += 1

        return expired_count

    def get_reservation(self, *, actor: Principal, reservation_id: UUID) -> Reservation:
        """Fetch a single reservation enforcing tenant isolation and authorization."""
        res = self._reservation_store.get_reservation(
            actor.organization_id, reservation_id
        )
        if res.requester_user_id != actor.user_id:
            if not self._allows(actor, self._PERM_MANAGE):
                self._require_perm(actor, self._PERM_READ)
        return res

    def list_reservations(
        self,
        *,
        actor: Principal,
        book_id: UUID | None = None,
        requester_user_id: UUID | None = None,
        status: str | None = None,
    ) -> list[Reservation]:
        """List reservations within tenant, filtered by patron ownership if not staff."""
        target_requester = requester_user_id
        if not self._allows(actor, self._PERM_MANAGE):
            target_requester = actor.user_id
        return self._reservation_store.list_reservations(
            actor.organization_id,
            book_id=book_id,
            requester_user_id=target_requester,
            status=status,
        )


def handle_loan_returned_allocation(
    *args: Any,
    connection: Any = None,
    event: ClaimedOutboxEvent | None = None,
    allocator: ReservationAllocator | None = None,
    reservation_allocator: ReservationAllocator | None = None,
    copy_store: CopyStatusStore | None = None,
    deduplication_port: ConsumerDeduplicationPort | None = None,
) -> Reservation | None:
    """Dispatcher consumer handler for circulation.loan_returned outbox events."""
    resolved_conn = connection
    resolved_event = event
    for arg in args:
        if isinstance(arg, ClaimedOutboxEvent):
            resolved_event = arg
        elif resolved_conn is None:
            resolved_conn = arg

    if resolved_event is None or resolved_conn is None:
        return None

    actual_allocator = allocator or reservation_allocator
    if actual_allocator is None:
        raise ValueError("allocator or reservation_allocator is required")

    actual_copy_store = copy_store or getattr(actual_allocator, "_copy_store", None)
    if actual_copy_store is None:
        raise ValueError("copy_store is required")

    org_id = resolved_event.organization_id
    payload: dict[str, Any] = {}
    if hasattr(resolved_event, "payload_json") and getattr(resolved_event, "payload_json"):
        try:
            payload = json.loads(getattr(resolved_event, "payload_json"))
        except Exception:
            payload = {}
    elif hasattr(resolved_event, "payload") and isinstance(getattr(resolved_event, "payload"), dict):
        payload = getattr(resolved_event, "payload")

    raw_copy_id = payload.get("copy_id")
    if not raw_copy_id:
        return None

    copy_id = UUID(str(raw_copy_id))

    # Consumer replay deduplication check
    if deduplication_port is not None:
        if deduplication_port.is_processed(
            resolved_conn,
            organization_id=org_id,
            outbox_event_id=resolved_event.event_id,
            job_type="circulation.loan_returned.reservation_allocation",
        ):
            return None

    copy = actual_copy_store.get_copy(org_id, copy_id)
    allocated = actual_allocator.allocate_copy_for_book_in_connection(
        resolved_conn,
        organization_id=org_id,
        book_id=copy.book_id,
        copy_id=copy_id,
        trigger_event_id=resolved_event.event_id,
    )

    if deduplication_port is not None:
        deduplication_port.record_processed(
            resolved_conn,
            organization_id=org_id,
            outbox_event_id=resolved_event.event_id,
            job_type="circulation.loan_returned.reservation_allocation",
            payload_version=resolved_event.payload_version,
        )

    return allocated
