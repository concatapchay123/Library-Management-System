"""Tenant-scoped inventory use cases: locations and physical copies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID, uuid4

from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.authorization import (
    AuthorizationDenied,
    AuthorizationPort,
)


class DuplicateBarcodeError(Exception):
    """Raised when a barcode already exists in the tenant."""


class DuplicateLocationCodeError(Exception):
    """Raised when a location code already exists in the tenant."""


@dataclass(frozen=True, slots=True)
class Location:
    """A physical or logical place where books are stored."""

    location_id: UUID
    organization_id: UUID
    name: str
    code: str
    parent_location_id: UUID | None
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class BookCopy:
    """A single, individually tracked physical copy of a bibliographic book."""

    copy_id: UUID
    organization_id: UUID
    book_id: UUID
    barcode: str
    location_id: UUID
    status: str
    condition_code: str
    acquired_at: datetime
    created_at: datetime
    updated_at: datetime


class InventoryStore(Protocol):
    """Persistence contract for tenant-scoped locations and copies."""

    def create_location(self, location: Location, *, actor: Principal) -> Location: ...

    def get_location(self, organization_id: UUID, location_id: UUID) -> Location: ...

    def update_location(self, location: Location, *, actor: Principal) -> Location: ...

    def list_locations(self, organization_id: UUID) -> list[Location]: ...

    def create_copy(self, copy: BookCopy, *, actor: Principal) -> BookCopy: ...

    def get_copy(self, organization_id: UUID, copy_id: UUID) -> BookCopy: ...

    def update_copy(self, copy: BookCopy, *, actor: Principal) -> BookCopy: ...

    def list_book_copies(
        self, organization_id: UUID, book_id: UUID
    ) -> list[BookCopy]: ...


class InventoryService:
    """Own validation, tenancy and authorization policy for locations and copies."""

    _MANAGE_PERMISSION = "inventory.manage"
    _READ_PERMISSIONS = ("inventory.manage", "inventory.read", "catalog.read")

    def __init__(self, store: InventoryStore, authorizer: AuthorizationPort) -> None:
        self._store = store
        self._authorizer = authorizer

    def _require_manage(self, actor: Principal) -> None:
        self._authorizer.require(actor, self._MANAGE_PERMISSION)

    def _require_read(self, actor: Principal) -> None:
        # Allow any of the read or manage permissions
        for perm in self._READ_PERMISSIONS:
            try:
                self._authorizer.require(actor, perm)
                return
            except AuthorizationDenied:
                continue
        raise AuthorizationDenied("inventory.manage or catalog.read required")

    def create_location(
        self,
        *,
        actor: Principal,
        name: str,
        code: str,
        parent_location_id: UUID | None = None,
    ) -> Location:
        self._require_manage(actor)
        cleaned_name = _clean_string(name, "location name", 255)
        cleaned_code = _clean_string(code, "location code", 64)
        if parent_location_id is not None:
            # Verify parent location belongs to same tenant
            self._store.get_location(actor.organization_id, parent_location_id)
        now = datetime.now(timezone.utc)
        location = Location(
            location_id=uuid4(),
            organization_id=actor.organization_id,
            name=cleaned_name,
            code=cleaned_code,
            parent_location_id=parent_location_id,
            status="active",
            created_at=now,
            updated_at=now,
        )
        return self._store.create_location(location, actor=actor)

    def get_location(self, *, actor: Principal, location_id: UUID) -> Location:
        self._require_read(actor)
        return self._store.get_location(actor.organization_id, location_id)

    def update_location(
        self,
        *,
        actor: Principal,
        location_id: UUID,
        name: str,
        code: str,
        parent_location_id: UUID | None = None,
        status: str = "active",
    ) -> Location:
        self._require_manage(actor)
        current = self._store.get_location(actor.organization_id, location_id)
        cleaned_name = _clean_string(name, "location name", 255)
        cleaned_code = _clean_string(code, "location code", 64)
        cleaned_status = _clean_string(status, "location status", 32)
        if parent_location_id is not None:
            if parent_location_id == location_id:
                raise ValueError("Location cannot be its own parent")
            self._store.get_location(actor.organization_id, parent_location_id)
        now = datetime.now(timezone.utc)
        updated = Location(
            location_id=location_id,
            organization_id=actor.organization_id,
            name=cleaned_name,
            code=cleaned_code,
            parent_location_id=parent_location_id,
            status=cleaned_status,
            created_at=current.created_at,
            updated_at=now,
        )
        return self._store.update_location(updated, actor=actor)

    def list_locations(self, *, actor: Principal) -> list[Location]:
        self._require_read(actor)
        return self._store.list_locations(actor.organization_id)

    def create_copy(
        self,
        *,
        actor: Principal,
        book_id: UUID,
        location_id: UUID,
        barcode: str,
        condition_code: str = "good",
        acquired_at: datetime | None = None,
    ) -> BookCopy:
        self._require_manage(actor)
        cleaned_barcode = _clean_string(barcode, "barcode", 64)
        cleaned_condition = _clean_string(condition_code, "condition code", 32)
        now = datetime.now(timezone.utc)
        copy_acquired = acquired_at if acquired_at is not None else now
        copy = BookCopy(
            copy_id=uuid4(),
            organization_id=actor.organization_id,
            book_id=book_id,
            barcode=cleaned_barcode,
            location_id=location_id,
            status="available",
            condition_code=cleaned_condition,
            acquired_at=copy_acquired,
            created_at=now,
            updated_at=now,
        )
        return self._store.create_copy(copy, actor=actor)

    def get_copy(self, *, actor: Principal, copy_id: UUID) -> BookCopy:
        self._require_read(actor)
        return self._store.get_copy(actor.organization_id, copy_id)

    def update_copy(
        self,
        *,
        actor: Principal,
        copy_id: UUID,
        location_id: UUID | None = None,
        condition_code: str | None = None,
    ) -> BookCopy:
        self._require_manage(actor)
        current = self._store.get_copy(actor.organization_id, copy_id)
        target_location_id = (
            location_id if location_id is not None else current.location_id
        )
        target_condition = (
            _clean_string(condition_code, "condition code", 32)
            if condition_code is not None
            else current.condition_code
        )
        now = datetime.now(timezone.utc)
        updated = BookCopy(
            copy_id=copy_id,
            organization_id=actor.organization_id,
            book_id=current.book_id,
            barcode=current.barcode,
            location_id=target_location_id,
            status=current.status,
            condition_code=target_condition,
            acquired_at=current.acquired_at,
            created_at=current.created_at,
            updated_at=now,
        )
        return self._store.update_copy(updated, actor=actor)

    def list_book_copies(self, *, actor: Principal, book_id: UUID) -> list[BookCopy]:
        self._require_read(actor)
        return self._store.list_book_copies(actor.organization_id, book_id)


def _clean_string(value: str, label: str, max_length: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Invalid {label}: expected string")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > max_length:
        raise ValueError(
            f"Invalid {label}: must be between 1 and {max_length} characters"
        )
    return cleaned
