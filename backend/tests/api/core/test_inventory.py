"""Contract and API tests for tenant-scoped locations and book copies."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest

from datetime import datetime, timezone

from openlibrary.app.config import AppConfig
from openlibrary.app.factory import create_app
from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.authorization import AuthorizationDenied
from openlibrary.modules.core.application.books import Book
from openlibrary.modules.core.application.copy_status import (
    CopyStatusHistory,
    CopyStatusService,
)
from openlibrary.modules.core.application.inventory import (
    BookCopy,
    DuplicateBarcodeError,
    DuplicateLocationCodeError,
    InventoryService,
    Location,
)
from openlibrary.modules.core.domain.copy_status import CopyStatus
from openlibrary.modules.ops.application.persistence import (
    AuditEvent,
    AuditedTransaction,
    OutboxEvent,
)

ORGANIZATION_A = uuid4()
ORGANIZATION_B = uuid4()
ACTOR_A = Principal(uuid4(), ORGANIZATION_A, uuid4())
ACTOR_B = Principal(uuid4(), ORGANIZATION_B, uuid4())


@dataclass
class _InMemoryInventoryStore:
    locations: dict[UUID, Location] = field(default_factory=dict)
    copies: dict[UUID, BookCopy] = field(default_factory=dict)
    books: dict[UUID, Book] = field(default_factory=dict)
    history: list[CopyStatusHistory] = field(default_factory=list)

    def create_location(self, location: Location, *, actor: Principal) -> Location:
        assert location.organization_id == actor.organization_id
        for existing in self.locations.values():
            if (
                existing.organization_id == location.organization_id
                and existing.code == location.code
            ):
                raise DuplicateLocationCodeError(f"Duplicate code: {location.code}")
        if location.parent_location_id is not None:
            parent = self.locations.get(location.parent_location_id)
            if parent is None or parent.organization_id != location.organization_id:
                raise KeyError(location.parent_location_id)
        self.locations[location.location_id] = location
        return location

    def get_location(self, organization_id: UUID, location_id: UUID) -> Location:
        loc = self.locations.get(location_id)
        if loc is None or loc.organization_id != organization_id:
            raise KeyError(location_id)
        return loc

    def update_location(self, location: Location, *, actor: Principal) -> Location:
        assert location.organization_id == actor.organization_id
        self.get_location(actor.organization_id, location.location_id)
        for existing in self.locations.values():
            if (
                existing.organization_id == location.organization_id
                and existing.code == location.code
                and existing.location_id != location.location_id
            ):
                raise DuplicateLocationCodeError(f"Duplicate code: {location.code}")
        if location.parent_location_id is not None:
            parent = self.locations.get(location.parent_location_id)
            if parent is None or parent.organization_id != location.organization_id:
                raise KeyError(location.parent_location_id)
        self.locations[location.location_id] = location
        return location

    def list_locations(self, organization_id: UUID) -> list[Location]:
        return [
            loc
            for loc in self.locations.values()
            if loc.organization_id == organization_id
        ]

    def create_copy(self, copy: BookCopy, *, actor: Principal) -> BookCopy:
        assert copy.organization_id == actor.organization_id
        # Verify book belongs to tenant
        book = self.books.get(copy.book_id)
        if book is None or book.organization_id != copy.organization_id:
            raise KeyError(f"Book {copy.book_id} not found in tenant")
        # Verify location belongs to tenant
        loc = self.locations.get(copy.location_id)
        if loc is None or loc.organization_id != copy.organization_id:
            raise KeyError(f"Location {copy.location_id} not found in tenant")
        # Verify barcode uniqueness in tenant
        for existing in self.copies.values():
            if (
                existing.organization_id == copy.organization_id
                and existing.barcode == copy.barcode
            ):
                raise DuplicateBarcodeError(f"Duplicate barcode: {copy.barcode}")
        self.copies[copy.copy_id] = copy
        return copy

    def get_copy(self, organization_id: UUID, copy_id: UUID) -> BookCopy:
        copy = self.copies.get(copy_id)
        if copy is None or copy.organization_id != organization_id:
            raise KeyError(copy_id)
        return copy

    def update_copy(self, copy: BookCopy, *, actor: Principal) -> BookCopy:
        assert copy.organization_id == actor.organization_id
        # Must exist in tenant
        self.get_copy(actor.organization_id, copy.copy_id)
        # Location must exist in tenant
        loc = self.locations.get(copy.location_id)
        if loc is None or loc.organization_id != copy.organization_id:
            raise KeyError(f"Location {copy.location_id} not found in tenant")
        self.copies[copy.copy_id] = copy
        return copy

    def list_book_copies(self, organization_id: UUID, book_id: UUID) -> list[BookCopy]:
        # Verify book belongs to tenant
        book = self.books.get(book_id)
        if book is None or book.organization_id != organization_id:
            raise KeyError(book_id)
        return [
            c
            for c in self.copies.values()
            if c.organization_id == organization_id and c.book_id == book_id
        ]

    def update_copy_status(
        self, organization_id: UUID, copy_id: UUID, to_status: str
    ) -> BookCopy:
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

    def append_history(self, record: CopyStatusHistory) -> CopyStatusHistory:
        self.history.append(record)
        return record

    def list_history_for_copy(
        self, organization_id: UUID, copy_id: UUID
    ) -> list[CopyStatusHistory]:
        return [
            h
            for h in self.history
            if h.organization_id == organization_id and h.copy_id == copy_id
        ]


class _InMemoryAuditedTx(AuditedTransaction):
    def __init__(self) -> None:
        self.audit_events: list[AuditEvent] = []
        self.outbox_events: list[OutboxEvent] = []

    def run(
        self,
        connection: object,
        mutation: object,
        audit_event: AuditEvent,
        outbox_events: object,
    ) -> object:
        result = mutation(connection)  # type: ignore[operator]
        self.audit_events.append(audit_event)
        return result


class _Authorizer:
    def __init__(self, allowed: set[str]) -> None:
        self.allowed = allowed

    def require(self, principal: Principal, permission: str) -> None:
        if permission not in self.allowed:
            raise AuthorizationDenied(f"Permission {permission} denied")


class _AccessTokens:
    def verify(self, token: str) -> Principal:
        return {"tenant-a": ACTOR_A, "tenant-b": ACTOR_B}[token]


def _make_book(org_id: UUID, title: str = "Test Book") -> Book:
    return Book(
        book_id=uuid4(),
        organization_id=org_id,
        title=title,
        title_sort_key=title.casefold(),
        isbn=None,
        authors=("Author",),
        published_year=2024,
    )


def test_barcode_duplication_rejected_within_tenant_and_allowed_across_tenants() -> (
    None
):
    store = _InMemoryInventoryStore()
    service = InventoryService(store, _Authorizer({"inventory.manage", "catalog.read"}))

    book_a = _make_book(ORGANIZATION_A, "Book in Tenant A")
    book_b = _make_book(ORGANIZATION_B, "Book in Tenant B")
    store.books[book_a.book_id] = book_a
    store.books[book_b.book_id] = book_b

    loc_a = service.create_location(
        actor=ACTOR_A, name="Main Stack", code="MAIN-STACK", parent_location_id=None
    )
    loc_b = service.create_location(
        actor=ACTOR_B, name="Branch Stack", code="BRANCH-STACK", parent_location_id=None
    )

    # Tenant A creates copy with barcode BARCODE-001
    copy_a1 = service.create_copy(
        actor=ACTOR_A,
        book_id=book_a.book_id,
        location_id=loc_a.location_id,
        barcode="BARCODE-001",
        condition_code="new",
    )
    assert copy_a1.barcode == "BARCODE-001"

    # Tenant A creating another copy with SAME barcode must fail
    with pytest.raises(DuplicateBarcodeError):
        service.create_copy(
            actor=ACTOR_A,
            book_id=book_a.book_id,
            location_id=loc_a.location_id,
            barcode="BARCODE-001",
            condition_code="good",
        )

    # Tenant B creating copy with the SAME barcode across tenants must SUCCEED
    copy_b1 = service.create_copy(
        actor=ACTOR_B,
        book_id=book_b.book_id,
        location_id=loc_b.location_id,
        barcode="BARCODE-001",
        condition_code="new",
    )
    assert copy_b1.barcode == "BARCODE-001"
    assert copy_b1.organization_id == ORGANIZATION_B


def test_one_bibliographic_book_can_own_multiple_physical_copies() -> None:
    store = _InMemoryInventoryStore()
    service = InventoryService(store, _Authorizer({"inventory.manage", "catalog.read"}))

    book = _make_book(ORGANIZATION_A, "Multi-Copy Title")
    store.books[book.book_id] = book

    loc = service.create_location(
        actor=ACTOR_A, name="Shelf 1", code="SHELF-1", parent_location_id=None
    )

    copy_1 = service.create_copy(
        actor=ACTOR_A,
        book_id=book.book_id,
        location_id=loc.location_id,
        barcode="COPY-001",
        condition_code="new",
    )
    copy_2 = service.create_copy(
        actor=ACTOR_A,
        book_id=book.book_id,
        location_id=loc.location_id,
        barcode="COPY-002",
        condition_code="good",
    )

    copies = service.list_book_copies(actor=ACTOR_A, book_id=book.book_id)
    assert len(copies) == 2
    assert {c.copy_id for c in copies} == {copy_1.copy_id, copy_2.copy_id}
    assert {c.barcode for c in copies} == {"COPY-001", "COPY-002"}


def test_location_tenant_isolation_and_cross_tenant_denial() -> None:
    store = _InMemoryInventoryStore()
    service = InventoryService(store, _Authorizer({"inventory.manage", "catalog.read"}))

    loc_a = service.create_location(
        actor=ACTOR_A, name="Location A", code="LOC-A", parent_location_id=None
    )
    loc_b = service.create_location(
        actor=ACTOR_B, name="Location B", code="LOC-B", parent_location_id=None
    )

    # Tenant A listing locations does not see Tenant B's location
    locations_a = service.list_locations(actor=ACTOR_A)
    assert [loc.location_id for loc in locations_a] == [loc_a.location_id]

    # Tenant A cannot fetch Tenant B's location
    with pytest.raises(KeyError):
        service.get_location(actor=ACTOR_A, location_id=loc_b.location_id)

    # Tenant A cannot update Tenant B's location
    with pytest.raises(KeyError):
        service.update_location(
            actor=ACTOR_A,
            location_id=loc_b.location_id,
            name="Hacked Name",
            code="LOC-B",
            parent_location_id=None,
            status="active",
        )

    # Tenant A cannot set parent_location_id to Tenant B's location
    with pytest.raises(KeyError):
        service.create_location(
            actor=ACTOR_A,
            name="Sub Loc",
            code="SUB-LOC",
            parent_location_id=loc_b.location_id,
        )

    # Tenant A cannot assign a copy to Tenant B's location
    book_a = _make_book(ORGANIZATION_A)
    store.books[book_a.book_id] = book_a
    with pytest.raises(KeyError):
        service.create_copy(
            actor=ACTOR_A,
            book_id=book_a.book_id,
            location_id=loc_b.location_id,
            barcode="BC-TENANT-LEAK",
            condition_code="good",
        )


def test_copy_condition_update_and_location_assignment() -> None:
    store = _InMemoryInventoryStore()
    service = InventoryService(store, _Authorizer({"inventory.manage", "catalog.read"}))

    book = _make_book(ORGANIZATION_A)
    store.books[book.book_id] = book

    loc_1 = service.create_location(
        actor=ACTOR_A, name="Floor 1", code="FL-1", parent_location_id=None
    )
    loc_2 = service.create_location(
        actor=ACTOR_A, name="Floor 2", code="FL-2", parent_location_id=None
    )

    copy = service.create_copy(
        actor=ACTOR_A,
        book_id=book.book_id,
        location_id=loc_1.location_id,
        barcode="BC-MOVE",
        condition_code="new",
    )
    assert copy.condition_code == "new"
    assert copy.location_id == loc_1.location_id

    # Update condition to damaged and reassign to Floor 2
    updated = service.update_copy(
        actor=ACTOR_A,
        copy_id=copy.copy_id,
        location_id=loc_2.location_id,
        condition_code="damaged",
    )
    assert updated.condition_code == "damaged"
    assert updated.location_id == loc_2.location_id

    fetched = service.get_copy(actor=ACTOR_A, copy_id=copy.copy_id)
    assert fetched.condition_code == "damaged"
    assert fetched.location_id == loc_2.location_id


def test_authorization_protection_for_inventory() -> None:
    store = _InMemoryInventoryStore()
    read_only_service = InventoryService(store, _Authorizer({"catalog.read"}))
    manage_service = InventoryService(store, _Authorizer({"inventory.manage"}))

    book = _make_book(ORGANIZATION_A)
    store.books[book.book_id] = book

    # Read-only actor cannot create location
    with pytest.raises(AuthorizationDenied):
        read_only_service.create_location(
            actor=ACTOR_A, name="Loc", code="L", parent_location_id=None
        )

    loc = manage_service.create_location(
        actor=ACTOR_A, name="Loc", code="L", parent_location_id=None
    )

    # Read-only actor cannot create copy
    with pytest.raises(AuthorizationDenied):
        read_only_service.create_copy(
            actor=ACTOR_A,
            book_id=book.book_id,
            location_id=loc.location_id,
            barcode="BC-1",
            condition_code="new",
        )

    copy = manage_service.create_copy(
        actor=ACTOR_A,
        book_id=book.book_id,
        location_id=loc.location_id,
        barcode="BC-1",
        condition_code="new",
    )

    # Read-only actor cannot update copy
    with pytest.raises(AuthorizationDenied):
        read_only_service.update_copy(
            actor=ACTOR_A,
            copy_id=copy.copy_id,
            location_id=loc.location_id,
            condition_code="fair",
        )


def test_inventory_http_endpoints_and_tenant_isolation() -> None:
    store = _InMemoryInventoryStore()
    service = InventoryService(store, _Authorizer({"inventory.manage", "catalog.read"}))

    book_a = _make_book(ORGANIZATION_A, "Title A")
    store.books[book_a.book_id] = book_a

    app = create_app(
        AppConfig(
            readiness_probe=lambda: True,
            access_tokens=_AccessTokens(),  # type: ignore[arg-type]
            inventory=service,
        )
    )
    client = app.test_client()

    # 1. Create Location via POST /api/v1/locations
    resp_loc = client.post(
        "/api/v1/locations",
        headers={"Authorization": "Bearer tenant-a"},
        json={"name": "Science Wing", "code": "SCI-WING"},
    )
    assert resp_loc.status_code == 201
    loc_data = resp_loc.get_json()
    loc_id = loc_data["location_id"]
    assert loc_data["code"] == "SCI-WING"

    # Duplicate location code within tenant returns 409
    resp_dup_loc = client.post(
        "/api/v1/locations",
        headers={"Authorization": "Bearer tenant-a"},
        json={"name": "Science Wing 2", "code": "SCI-WING"},
    )
    assert resp_dup_loc.status_code == 409
    assert resp_dup_loc.mimetype == "application/problem+json"

    # 2. List Locations via GET /api/v1/locations
    resp_loc_list = client.get(
        "/api/v1/locations",
        headers={"Authorization": "Bearer tenant-a"},
    )
    assert resp_loc_list.status_code == 200
    assert len(resp_loc_list.get_json()["items"]) == 1

    # Tenant B sees empty list
    resp_loc_b = client.get(
        "/api/v1/locations",
        headers={"Authorization": "Bearer tenant-b"},
    )
    assert resp_loc_b.status_code == 200
    assert resp_loc_b.get_json()["items"] == []

    # 3. Create Copy via POST /api/v1/books/<book_id>/copies
    resp_copy1 = client.post(
        f"/api/v1/books/{book_a.book_id}/copies",
        headers={"Authorization": "Bearer tenant-a"},
        json={
            "location_id": loc_id,
            "barcode": "BC-100",
            "condition_code": "new",
        },
    )
    assert resp_copy1.status_code == 201
    copy1_data = resp_copy1.get_json()
    assert copy1_data["barcode"] == "BC-100"
    copy1_id = copy1_data["copy_id"]

    # 4. Create second Copy for same book
    resp_copy2 = client.post(
        f"/api/v1/books/{book_a.book_id}/copies",
        headers={"Authorization": "Bearer tenant-a"},
        json={
            "location_id": loc_id,
            "barcode": "BC-200",
            "condition_code": "good",
        },
    )
    assert resp_copy2.status_code == 201

    # Duplicate barcode in same tenant returns 409
    resp_dup_bc = client.post(
        f"/api/v1/books/{book_a.book_id}/copies",
        headers={"Authorization": "Bearer tenant-a"},
        json={
            "location_id": loc_id,
            "barcode": "BC-100",
            "condition_code": "poor",
        },
    )
    assert resp_dup_bc.status_code == 409
    assert resp_dup_bc.mimetype == "application/problem+json"

    # 5. List copies for book via GET /api/v1/books/<book_id>/copies
    resp_copies = client.get(
        f"/api/v1/books/{book_a.book_id}/copies",
        headers={"Authorization": "Bearer tenant-a"},
    )
    assert resp_copies.status_code == 200
    copies_items = resp_copies.get_json()["items"]
    assert len(copies_items) == 2

    # 6. Update copy condition via PATCH /api/v1/copies/<copy_id> or /api/v1/books/<book_id>/copies/<copy_id>
    resp_patch = client.patch(
        f"/api/v1/copies/{copy1_id}",
        headers={"Authorization": "Bearer tenant-a"},
        json={"condition_code": "fair"},
    )
    assert resp_patch.status_code == 200
    assert resp_patch.get_json()["condition_code"] == "fair"

    # 7. Tenant B cannot get Tenant A's copy
    resp_b_get = client.get(
        f"/api/v1/copies/{copy1_id}",
        headers={"Authorization": "Bearer tenant-b"},
    )
    assert resp_b_get.status_code == 404

    # 8. Malformed UUID returns 400
    resp_bad_uuid = client.get(
        "/api/v1/copies/invalid-uuid",
        headers={"Authorization": "Bearer tenant-a"},
    )
    assert resp_bad_uuid.status_code == 400


def test_copy_status_http_endpoints_and_history() -> None:
    store = _InMemoryInventoryStore()
    inv_service = InventoryService(
        store, _Authorizer({"inventory.manage", "inventory.read", "catalog.read"})
    )
    tx = _InMemoryAuditedTx()
    status_service = CopyStatusService(
        store=store,
        authorizer=_Authorizer({"inventory.manage", "inventory.read", "catalog.read"}),
        transaction=tx,
    )

    book = _make_book(ORGANIZATION_A, "Status Test Title")
    store.books[book.book_id] = book

    loc = inv_service.create_location(
        actor=ACTOR_A, name="Main Shelf", code="MAIN-SH", parent_location_id=None
    )
    copy = inv_service.create_copy(
        actor=ACTOR_A,
        book_id=book.book_id,
        location_id=loc.location_id,
        barcode="BC-STATUS-001",
    )
    assert copy.status == CopyStatus.AVAILABLE

    app = create_app(
        AppConfig(
            readiness_probe=lambda: True,
            access_tokens=_AccessTokens(),  # type: ignore[arg-type]
            inventory=inv_service,
            copy_status=status_service,
        )
    )
    client = app.test_client()

    # 1. POST /api/v1/copies/<copy_id>/status: transition to maintenance
    resp_trans = client.post(
        f"/api/v1/copies/{copy.copy_id}/status",
        headers={"Authorization": "Bearer tenant-a"},
        json={
            "to_status": CopyStatus.MAINTENANCE,
            "reason": "Routine rebinding and spine repair",
        },
    )
    assert resp_trans.status_code == 200
    data = resp_trans.get_json()
    assert data["status"] == CopyStatus.MAINTENANCE

    # Exactly 1 audit record written
    assert len(tx.audit_events) == 1
    assert tx.audit_events[0].action == "copy.status_changed"

    # 2. GET /api/v1/copies/<copy_id>/history
    resp_hist = client.get(
        f"/api/v1/copies/{copy.copy_id}/history",
        headers={"Authorization": "Bearer tenant-a"},
    )
    assert resp_hist.status_code == 200
    hist_items = resp_hist.get_json()["items"]
    assert len(hist_items) == 1
    assert hist_items[0]["from_status"] == CopyStatus.AVAILABLE
    assert hist_items[0]["to_status"] == CopyStatus.MAINTENANCE
    assert hist_items[0]["reason"] == "Routine rebinding and spine repair"
    assert hist_items[0]["actor_id"] == str(ACTOR_A.user_id)

    # 3. Rejected transition: maintenance -> borrowed returns 409 Problem Details
    resp_rejected = client.post(
        f"/api/v1/copies/{copy.copy_id}/status",
        headers={"Authorization": "Bearer tenant-a"},
        json={
            "to_status": CopyStatus.BORROWED,
            "reason": "Attempting invalid checkout from maintenance",
        },
    )
    assert resp_rejected.status_code == 409
    assert resp_rejected.mimetype == "application/problem+json"
    problem = resp_rejected.get_json()
    assert (
        problem["type"]
        == "https://openlibraryos.example/problems/invalid-copy-status-transition"
    )
    assert problem["status"] == 409
    assert "Cannot transition copy status" in problem["detail"]

    # 4. Nested route: POST /api/v1/books/<book_id>/copies/<copy_id>/status: restore to available
    resp_nested = client.post(
        f"/api/v1/books/{book.book_id}/copies/{copy.copy_id}/status",
        headers={"Authorization": "Bearer tenant-a"},
        json={
            "to_status": CopyStatus.AVAILABLE,
            "reason": "Maintenance complete, returned to circulation",
        },
    )
    assert resp_nested.status_code == 200
    assert resp_nested.get_json()["status"] == CopyStatus.AVAILABLE

    # 5. Nested route: GET /api/v1/books/<book_id>/copies/<copy_id>/history
    resp_nested_hist = client.get(
        f"/api/v1/books/{book.book_id}/copies/{copy.copy_id}/history",
        headers={"Authorization": "Bearer tenant-a"},
    )
    assert resp_nested_hist.status_code == 200
    assert len(resp_nested_hist.get_json()["items"]) == 2

    # 6. Invalid payload: empty reason returns 400
    resp_bad = client.post(
        f"/api/v1/copies/{copy.copy_id}/status",
        headers={"Authorization": "Bearer tenant-a"},
        json={"to_status": CopyStatus.DAMAGED, "reason": "  "},
    )
    assert resp_bad.status_code == 400
    assert resp_bad.mimetype == "application/problem+json"

    # 7. Tenant isolation: Tenant B cannot transition Tenant A's copy
    resp_tenant_b = client.post(
        f"/api/v1/copies/{copy.copy_id}/status",
        headers={"Authorization": "Bearer tenant-b"},
        json={"to_status": CopyStatus.DAMAGED, "reason": "Tenant cross test"},
    )
    assert resp_tenant_b.status_code == 404
