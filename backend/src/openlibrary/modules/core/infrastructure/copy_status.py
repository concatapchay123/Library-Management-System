"""SQL Server persistence for copy status transitions and append-only history."""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from openlibrary.modules.core.application.copy_status import (
    CopyStatusHistory,
    CopyStatusStore,
)
from openlibrary.modules.core.application.inventory import BookCopy
from openlibrary.modules.core.infrastructure.inventory import _copy_from_row
from openlibrary.modules.core.infrastructure.tenancy import SqlServerTenantContext


class SqlServerCopyStatusStore(CopyStatusStore):
    """Execute parameterized copy status updates and history appends under tenant context."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._tenant_context: SqlServerTenantContext | None = None

    def get_copy(self, organization_id: UUID, copy_id: UUID) -> BookCopy:
        with self._tenant_connection(organization_id) as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT copy_id, organization_id, book_id, barcode, "
                        "location_id, status, condition_code, acquired_at, "
                        "created_at, updated_at FROM core.book_copies "
                        "WHERE copy_id = :copy_id"
                    ),
                    {"copy_id": str(copy_id)},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise KeyError(copy_id)
        return _copy_from_row(row)

    def get_available_copy_for_book(
        self, organization_id: UUID, book_id: UUID
    ) -> BookCopy | None:
        """Find an available copy for a book title."""
        with self._tenant_connection(organization_id) as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT TOP 1 copy_id, organization_id, book_id, barcode, "
                        "location_id, status, condition_code, acquired_at, "
                        "created_at, updated_at FROM core.book_copies "
                        "WHERE book_id = :book_id AND status = 'available' "
                        "ORDER BY copy_id ASC"
                    ),
                    {"book_id": str(book_id)},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return _copy_from_row(row)

    def update_copy_status(
        self,
        organization_id: UUID,
        copy_id: UUID,
        to_status: str,
    ) -> BookCopy:
        with self._tenant_connection(organization_id) as connection:
            result = connection.execute(
                text(
                    "UPDATE core.book_copies SET status = :status, "
                    "updated_at = SYSUTCDATETIME() WHERE copy_id = :copy_id"
                ),
                {"copy_id": str(copy_id), "status": to_status},
            )
            if result.rowcount != 1:
                raise KeyError(copy_id)
            row = (
                connection.execute(
                    text(
                        "SELECT copy_id, organization_id, book_id, barcode, "
                        "location_id, status, condition_code, acquired_at, "
                        "created_at, updated_at FROM core.book_copies "
                        "WHERE copy_id = :copy_id"
                    ),
                    {"copy_id": str(copy_id)},
                )
                .mappings()
                .one()
            )
        return _copy_from_row(row)

    def append_history(self, record: CopyStatusHistory) -> CopyStatusHistory:
        with self._tenant_connection(record.organization_id) as connection:
            connection.execute(
                text(
                    "INSERT INTO core.copy_status_history (history_id, organization_id, "
                    "copy_id, from_status, to_status, reason, actor_id, created_at) "
                    "VALUES (:history_id, :organization_id, :copy_id, :from_status, "
                    ":to_status, :reason, :actor_id, :created_at)"
                ),
                _history_params(record),
            )
        return record

    def list_history_for_copy(
        self, organization_id: UUID, copy_id: UUID
    ) -> list[CopyStatusHistory]:
        statement = (
            "SELECT history_id, organization_id, copy_id, from_status, to_status, "
            "reason, actor_id, created_at FROM core.copy_status_history "
            "WHERE copy_id = :copy_id ORDER BY created_at DESC, history_id DESC"
        )
        with self._tenant_connection(organization_id) as connection:
            rows = connection.execute(
                text(statement), {"copy_id": str(copy_id)}
            ).mappings()
            return [_history_from_row(row) for row in rows]

    def record_transition_in_connection(
        self,
        connection: Connection,
        *,
        organization_id: UUID,
        copy_id: UUID,
        to_status: str,
        history_record: CopyStatusHistory,
    ) -> BookCopy:
        """Update copy status and append history atomically inside an active transaction."""
        result = connection.execute(
            text(
                "UPDATE core.book_copies SET status = :status, "
                "updated_at = SYSUTCDATETIME() WHERE copy_id = :copy_id"
            ),
            {"copy_id": str(copy_id), "status": to_status},
        )
        if result.rowcount != 1:
            raise KeyError(copy_id)

        connection.execute(
            text(
                "INSERT INTO core.copy_status_history (history_id, organization_id, "
                "copy_id, from_status, to_status, reason, actor_id, created_at) "
                "VALUES (:history_id, :organization_id, :copy_id, :from_status, "
                ":to_status, :reason, :actor_id, :created_at)"
            ),
            _history_params(history_record),
        )

        row = (
            connection.execute(
                text(
                    "SELECT copy_id, organization_id, book_id, barcode, "
                    "location_id, status, condition_code, acquired_at, "
                    "created_at, updated_at FROM core.book_copies "
                    "WHERE copy_id = :copy_id"
                ),
                {"copy_id": str(copy_id)},
            )
            .mappings()
            .one()
        )
        return _copy_from_row(row)

    def get_copy_for_update_in_connection(
        self,
        connection: Connection,
        organization_id: UUID,
        copy_id: UUID,
    ) -> BookCopy:
        """Lock the copy row within the transaction using UPDLOCK and ROWLOCK."""
        row = (
            connection.execute(
                text(
                    "SELECT copy_id, organization_id, book_id, barcode, "
                    "location_id, status, condition_code, acquired_at, "
                    "created_at, updated_at FROM core.book_copies WITH (UPDLOCK, ROWLOCK) "
                    "WHERE copy_id = :copy_id"
                ),
                {"copy_id": str(copy_id)},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise KeyError(copy_id)
        return _copy_from_row(row)

    def _tenant_connection(
        self, organization_id: UUID
    ) -> AbstractContextManager[Connection]:
        if self._tenant_context is None:
            self._tenant_context = SqlServerTenantContext(self._database_url)
        return self._tenant_context.connection(organization_id)


def _history_params(record: CopyStatusHistory) -> dict[str, object]:
    return {
        "history_id": str(record.history_id),
        "organization_id": str(record.organization_id),
        "copy_id": str(record.copy_id),
        "from_status": record.from_status,
        "to_status": record.to_status,
        "reason": record.reason,
        "actor_id": str(record.actor_id),
        "created_at": record.created_at,
    }


def _history_from_row(row: RowMapping) -> CopyStatusHistory:
    return CopyStatusHistory(
        history_id=UUID(str(row["history_id"])),
        organization_id=UUID(str(row["organization_id"])),
        copy_id=UUID(str(row["copy_id"])),
        from_status=str(row["from_status"]),
        to_status=str(row["to_status"]),
        reason=str(row["reason"]),
        actor_id=UUID(str(row["actor_id"])),
        created_at=row["created_at"]
        if isinstance(row["created_at"], datetime)
        else datetime.fromisoformat(str(row["created_at"])),
    )
