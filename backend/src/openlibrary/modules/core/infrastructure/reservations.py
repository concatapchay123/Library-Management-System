"""SQL Server persistence for book reservations under tenant context."""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from openlibrary.modules.core.application.reservations import (
    Reservation,
    ReservationStore,
)
from openlibrary.modules.core.domain.reservations import (
    ReservationNotFoundError,
    ReservationStatus,
)
from openlibrary.modules.core.infrastructure.tenancy import SqlServerTenantContext


class SqlServerReservationStore(ReservationStore):
    """Execute parameterized reservation queries and mutations under tenant context."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._tenant_context: SqlServerTenantContext | None = None

    def create_reservation(self, reservation: Reservation) -> Reservation:
        with self._tenant_connection(reservation.organization_id) as connection:
            return self.record_create_reservation_in_connection(connection, reservation)

    def get_reservation(
        self, organization_id: UUID, reservation_id: UUID
    ) -> Reservation:
        with self._tenant_connection(organization_id) as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT reservation_id, organization_id, book_id, requester_user_id, "
                        "copy_id, queue_position, status, hold_expires_at, created_at, updated_at "
                        "FROM core.reservations WHERE reservation_id = :reservation_id"
                    ),
                    {"reservation_id": str(reservation_id)},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise ReservationNotFoundError(reservation_id)
        return _reservation_from_row(row)

    def update_reservation(self, reservation: Reservation) -> Reservation:
        with self._tenant_connection(reservation.organization_id) as connection:
            return self.record_update_reservation_in_connection(connection, reservation)

    def list_reservations(
        self,
        organization_id: UUID,
        *,
        book_id: UUID | None = None,
        requester_user_id: UUID | None = None,
        status: str | None = None,
    ) -> list[Reservation]:
        clauses = ["1=1"]
        params: dict[str, object] = {}
        if book_id is not None:
            clauses.append("book_id = :book_id")
            params["book_id"] = str(book_id)
        if requester_user_id is not None:
            clauses.append("requester_user_id = :requester_user_id")
            params["requester_user_id"] = str(requester_user_id)
        if status is not None:
            clauses.append("status = :status")
            params["status"] = status

        query = (
            "SELECT reservation_id, organization_id, book_id, requester_user_id, "
            "copy_id, queue_position, status, hold_expires_at, created_at, updated_at "
            "FROM core.reservations "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY queue_position ASC, created_at ASC, reservation_id ASC"
        )
        with self._tenant_connection(organization_id) as connection:
            rows = connection.execute(text(query), params).mappings()
            return [_reservation_from_row(row) for row in rows]

    def get_next_queue_position(self, organization_id: UUID, book_id: UUID) -> int:
        query = (
            "SELECT ISNULL(MAX(queue_position), 0) + 1 AS next_pos "
            "FROM core.reservations WHERE book_id = :book_id"
        )
        with self._tenant_connection(organization_id) as connection:
            val = connection.execute(
                text(query), {"book_id": str(book_id)}
            ).scalar_one()
            return int(val)

    def get_next_pending_reservation(
        self, organization_id: UUID, book_id: UUID
    ) -> Reservation | None:
        query = (
            "SELECT TOP 1 reservation_id, organization_id, book_id, requester_user_id, "
            "copy_id, queue_position, status, hold_expires_at, created_at, updated_at "
            "FROM core.reservations "
            "WHERE book_id = :book_id AND status = :status "
            "ORDER BY queue_position ASC, created_at ASC, reservation_id ASC"
        )
        with self._tenant_connection(organization_id) as connection:
            row = (
                connection.execute(
                    text(query),
                    {"book_id": str(book_id), "status": ReservationStatus.PENDING},
                )
                .mappings()
                .one_or_none()
            )
            return _reservation_from_row(row) if row is not None else None

    def get_next_pending_reservation_for_update_in_connection(
        self, connection: Connection, organization_id: UUID, book_id: UUID
    ) -> Reservation | None:
        query = (
            "SELECT TOP 1 reservation_id, organization_id, book_id, requester_user_id, "
            "copy_id, queue_position, status, hold_expires_at, created_at, updated_at "
            "FROM core.reservations WITH (UPDLOCK, ROWLOCK) "
            "WHERE book_id = :book_id AND status = :status "
            "ORDER BY queue_position ASC, created_at ASC, reservation_id ASC"
        )
        row = (
            connection.execute(
                text(query),
                {"book_id": str(book_id), "status": ReservationStatus.PENDING},
            )
            .mappings()
            .one_or_none()
        )
        return _reservation_from_row(row) if row is not None else None

    def get_active_reservation_for_user_and_book(
        self, organization_id: UUID, book_id: UUID, user_id: UUID
    ) -> Reservation | None:
        query = (
            "SELECT TOP 1 reservation_id, organization_id, book_id, requester_user_id, "
            "copy_id, queue_position, status, hold_expires_at, created_at, updated_at "
            "FROM core.reservations "
            "WHERE book_id = :book_id AND requester_user_id = :user_id "
            "AND status IN ('pending', 'held')"
        )
        with self._tenant_connection(organization_id) as connection:
            row = (
                connection.execute(
                    text(query),
                    {"book_id": str(book_id), "user_id": str(user_id)},
                )
                .mappings()
                .one_or_none()
            )
            return _reservation_from_row(row) if row is not None else None

    def list_expired_holds(
        self, organization_id: UUID, now: datetime
    ) -> list[Reservation]:
        query = (
            "SELECT reservation_id, organization_id, book_id, requester_user_id, "
            "copy_id, queue_position, status, hold_expires_at, created_at, updated_at "
            "FROM core.reservations "
            "WHERE status = :status AND hold_expires_at <= :now "
            "ORDER BY hold_expires_at ASC"
        )
        with self._tenant_connection(organization_id) as connection:
            rows = connection.execute(
                text(query),
                {"status": ReservationStatus.HELD, "now": now},
            ).mappings()
            return [_reservation_from_row(row) for row in rows]

    def record_create_reservation_in_connection(
        self, connection: Connection, reservation: Reservation
    ) -> Reservation:
        """Insert a new reservation atomically inside an active transaction."""
        connection.execute(
            text(
                "INSERT INTO core.reservations (reservation_id, organization_id, book_id, "
                "requester_user_id, copy_id, queue_position, status, hold_expires_at, "
                "created_at, updated_at) "
                "VALUES (:reservation_id, :organization_id, :book_id, :requester_user_id, "
                ":copy_id, :queue_position, :status, :hold_expires_at, :created_at, :updated_at)"
            ),
            _reservation_params(reservation),
        )
        return reservation

    def record_update_reservation_in_connection(
        self, connection: Connection, reservation: Reservation
    ) -> Reservation:
        """Update an existing reservation atomically inside an active transaction."""
        result = connection.execute(
            text(
                "UPDATE core.reservations SET status = :status, copy_id = :copy_id, "
                "hold_expires_at = :hold_expires_at, updated_at = SYSUTCDATETIME() "
                "WHERE reservation_id = :reservation_id"
            ),
            _reservation_update_params(reservation),
        )
        if result.rowcount != 1:
            raise ReservationNotFoundError(reservation.reservation_id)
        return reservation

    def get_reservation_for_update_in_connection(
        self, connection: Connection, organization_id: UUID, reservation_id: UUID
    ) -> Reservation:
        """Fetch and lock a reservation row for update."""
        row = (
            connection.execute(
                text(
                    "SELECT reservation_id, organization_id, book_id, requester_user_id, "
                    "copy_id, queue_position, status, hold_expires_at, created_at, updated_at "
                    "FROM core.reservations WITH (UPDLOCK, ROWLOCK) "
                    "WHERE reservation_id = :reservation_id"
                ),
                {"reservation_id": str(reservation_id)},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise ReservationNotFoundError(reservation_id)
        return _reservation_from_row(row)

    def _tenant_connection(
        self, organization_id: UUID
    ) -> AbstractContextManager[Connection]:
        if self._tenant_context is None:
            self._tenant_context = SqlServerTenantContext(self._database_url)
        return self._tenant_context.connection(organization_id)


def _reservation_params(reservation: Reservation) -> dict[str, object]:
    return {
        "reservation_id": str(reservation.reservation_id),
        "organization_id": str(reservation.organization_id),
        "book_id": str(reservation.book_id),
        "requester_user_id": str(reservation.requester_user_id),
        "copy_id": str(reservation.copy_id)
        if reservation.copy_id is not None
        else None,
        "queue_position": reservation.queue_position,
        "status": reservation.status,
        "hold_expires_at": reservation.hold_expires_at,
        "created_at": reservation.created_at,
        "updated_at": reservation.updated_at,
    }


def _reservation_update_params(reservation: Reservation) -> dict[str, object]:
    return {
        "reservation_id": str(reservation.reservation_id),
        "status": reservation.status,
        "copy_id": str(reservation.copy_id)
        if reservation.copy_id is not None
        else None,
        "hold_expires_at": reservation.hold_expires_at,
    }


def _reservation_from_row(row: RowMapping) -> Reservation:
    return Reservation(
        reservation_id=UUID(str(row["reservation_id"])),
        organization_id=UUID(str(row["organization_id"])),
        book_id=UUID(str(row["book_id"])),
        requester_user_id=UUID(str(row["requester_user_id"])),
        copy_id=UUID(str(row["copy_id"])) if row["copy_id"] is not None else None,
        queue_position=int(row["queue_position"]),
        status=str(row["status"]),
        hold_expires_at=_parse_opt_dt(row["hold_expires_at"]),
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
    )


def _parse_dt(val: object) -> datetime:
    if isinstance(val, datetime):
        return val
    return datetime.fromisoformat(str(val))


def _parse_opt_dt(val: object) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    return datetime.fromisoformat(str(val))
