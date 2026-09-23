"""SQL Server persistence for tenant-scoped locations and book copies."""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping
from sqlalchemy.exc import IntegrityError

from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.inventory import (
    BookCopy,
    DuplicateBarcodeError,
    DuplicateLocationCodeError,
    InventoryStore,
    Location,
)
from openlibrary.modules.core.infrastructure.tenancy import SqlServerTenantContext


class SqlServerInventoryStore(InventoryStore):
    """Execute parameterized, fixed-shape location and copy SQL under tenant context."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._tenant_context: SqlServerTenantContext | None = None

    def create_location(self, location: Location, *, actor: Principal) -> Location:
        with self._tenant_connection(actor.organization_id) as connection:
            try:
                connection.execute(
                    text(
                        "INSERT INTO core.locations (location_id, organization_id, "
                        "name, code, parent_location_id, status, created_at, updated_at) "
                        "VALUES (:location_id, :organization_id, :name, :code, "
                        ":parent_location_id, :status, :created_at, :updated_at)"
                    ),
                    _location_params(location),
                )
            except IntegrityError as error:
                err_str = str(error)
                if "UQ_core_locations_organization_code" in err_str:
                    raise DuplicateLocationCodeError(
                        f"Duplicate code: {location.code}"
                    ) from error
                if "FK_core_locations_parent" in err_str:
                    raise KeyError(location.parent_location_id) from error
                raise
        return location

    def get_location(self, organization_id: UUID, location_id: UUID) -> Location:
        with self._tenant_connection(organization_id) as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT location_id, organization_id, name, code, "
                        "parent_location_id, status, created_at, updated_at "
                        "FROM core.locations WHERE location_id = :location_id"
                    ),
                    {"location_id": str(location_id)},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise KeyError(location_id)
        return _location_from_row(row)

    def update_location(self, location: Location, *, actor: Principal) -> Location:
        with self._tenant_connection(actor.organization_id) as connection:
            try:
                result = connection.execute(
                    text(
                        "UPDATE core.locations SET name = :name, code = :code, "
                        "parent_location_id = :parent_location_id, status = :status, "
                        "updated_at = SYSUTCDATETIME() "
                        "WHERE location_id = :location_id"
                    ),
                    _location_params(location),
                )
            except IntegrityError as error:
                err_str = str(error)
                if "UQ_core_locations_organization_code" in err_str:
                    raise DuplicateLocationCodeError(
                        f"Duplicate code: {location.code}"
                    ) from error
                if "FK_core_locations_parent" in err_str:
                    raise KeyError(location.parent_location_id) from error
                raise
        if result.rowcount != 1:
            raise KeyError(location.location_id)
        return location

    def list_locations(self, organization_id: UUID) -> list[Location]:
        statement = (
            "SELECT location_id, organization_id, name, code, "
            "parent_location_id, status, created_at, updated_at "
            "FROM core.locations ORDER BY name, location_id"
        )
        with self._tenant_connection(organization_id) as connection:
            rows = connection.execute(text(statement)).mappings()
            return [_location_from_row(row) for row in rows]

    def create_copy(self, copy: BookCopy, *, actor: Principal) -> BookCopy:
        with self._tenant_connection(actor.organization_id) as connection:
            try:
                connection.execute(
                    text(
                        "INSERT INTO core.book_copies (copy_id, organization_id, "
                        "book_id, barcode, location_id, status, condition_code, "
                        "acquired_at, created_at, updated_at) VALUES (:copy_id, "
                        ":organization_id, :book_id, :barcode, :location_id, "
                        ":status, :condition_code, :acquired_at, :created_at, :updated_at)"
                    ),
                    _copy_params(copy),
                )
            except IntegrityError as error:
                err_str = str(error)
                if "UQ_core_book_copies_organization_barcode" in err_str:
                    raise DuplicateBarcodeError(
                        f"Duplicate barcode: {copy.barcode}"
                    ) from error
                if "FK_core_book_copies_book" in err_str:
                    raise KeyError(copy.book_id) from error
                if "FK_core_book_copies_location" in err_str:
                    raise KeyError(copy.location_id) from error
                raise
        return copy

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

    def update_copy(self, copy: BookCopy, *, actor: Principal) -> BookCopy:
        with self._tenant_connection(actor.organization_id) as connection:
            try:
                result = connection.execute(
                    text(
                        "UPDATE core.book_copies SET location_id = :location_id, "
                        "condition_code = :condition_code, updated_at = SYSUTCDATETIME() "
                        "WHERE copy_id = :copy_id"
                    ),
                    {
                        "copy_id": str(copy.copy_id),
                        "location_id": str(copy.location_id),
                        "condition_code": copy.condition_code,
                    },
                )
            except IntegrityError as error:
                err_str = str(error)
                if "FK_core_book_copies_location" in err_str:
                    raise KeyError(copy.location_id) from error
                raise
        if result.rowcount != 1:
            raise KeyError(copy.copy_id)
        return copy

    def list_book_copies(self, organization_id: UUID, book_id: UUID) -> list[BookCopy]:
        # First verify book exists in tenant
        with self._tenant_connection(organization_id) as connection:
            book_row = (
                connection.execute(
                    text("SELECT book_id FROM core.books WHERE book_id = :book_id"),
                    {"book_id": str(book_id)},
                )
                .mappings()
                .one_or_none()
            )
            if book_row is None:
                raise KeyError(book_id)

            rows = connection.execute(
                text(
                    "SELECT copy_id, organization_id, book_id, barcode, "
                    "location_id, status, condition_code, acquired_at, "
                    "created_at, updated_at FROM core.book_copies "
                    "WHERE book_id = :book_id ORDER BY barcode, copy_id"
                ),
                {"book_id": str(book_id)},
            ).mappings()
            return [_copy_from_row(row) for row in rows]

    def _tenant_connection(
        self, organization_id: UUID
    ) -> AbstractContextManager[Connection]:
        if self._tenant_context is None:
            self._tenant_context = SqlServerTenantContext(self._database_url)
        return self._tenant_context.connection(organization_id)


def _location_params(location: Location) -> dict[str, object]:
    return {
        "location_id": str(location.location_id),
        "organization_id": str(location.organization_id),
        "name": location.name,
        "code": location.code,
        "parent_location_id": str(location.parent_location_id)
        if location.parent_location_id is not None
        else None,
        "status": location.status,
        "created_at": location.created_at,
        "updated_at": location.updated_at,
    }


def _location_from_row(row: RowMapping) -> Location:
    return Location(
        location_id=UUID(str(row["location_id"])),
        organization_id=UUID(str(row["organization_id"])),
        name=str(row["name"]),
        code=str(row["code"]),
        parent_location_id=UUID(str(row["parent_location_id"]))
        if row["parent_location_id"] is not None
        else None,
        status=str(row["status"]),
        created_at=row["created_at"]
        if isinstance(row["created_at"], datetime)
        else datetime.fromisoformat(str(row["created_at"])),
        updated_at=row["updated_at"]
        if isinstance(row["updated_at"], datetime)
        else datetime.fromisoformat(str(row["updated_at"])),
    )


def _copy_params(copy: BookCopy) -> dict[str, object]:
    return {
        "copy_id": str(copy.copy_id),
        "organization_id": str(copy.organization_id),
        "book_id": str(copy.book_id),
        "barcode": copy.barcode,
        "location_id": str(copy.location_id),
        "status": copy.status,
        "condition_code": copy.condition_code,
        "acquired_at": copy.acquired_at,
        "created_at": copy.created_at,
        "updated_at": copy.updated_at,
    }


def _copy_from_row(row: RowMapping) -> BookCopy:
    return BookCopy(
        copy_id=UUID(str(row["copy_id"])),
        organization_id=UUID(str(row["organization_id"])),
        book_id=UUID(str(row["book_id"])),
        barcode=str(row["barcode"]),
        location_id=UUID(str(row["location_id"])),
        status=str(row["status"]),
        condition_code=str(row["condition_code"]),
        acquired_at=row["acquired_at"]
        if isinstance(row["acquired_at"], datetime)
        else datetime.fromisoformat(str(row["acquired_at"])),
        created_at=row["created_at"]
        if isinstance(row["created_at"], datetime)
        else datetime.fromisoformat(str(row["created_at"])),
        updated_at=row["updated_at"]
        if isinstance(row["updated_at"], datetime)
        else datetime.fromisoformat(str(row["updated_at"])),
    )
