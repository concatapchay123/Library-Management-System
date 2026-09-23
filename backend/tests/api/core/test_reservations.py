"""API and route tests for reservation endpoints."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest

from openlibrary.app.config import AppConfig
from openlibrary.app.factory import create_app
from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.authorization import AuthorizationDenied
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
    ReservationNotFoundError,
    ReservationStatus,
)
from openlibrary.modules.ops.application.persistence import (
    AuditEvent,
    OutboxEvent,
)

ORGANIZATION_A = uuid4()
ORGANIZATION_B = uuid4()
PATRON_A = Principal(uuid4(), ORGANIZATION_A, uuid4())
PATRON_A2 = Principal(uuid4(), ORGANIZATION_A, uuid4())
LIBRARIAN_A = Principal(uuid4(), ORGANIZATION_A, uuid4())
PATRON_B = Principal(uuid4(), ORGANIZATION_B, uuid4())


@dataclass
class _InMemoryReservationStore(ReservationStore):
    reservations: dict[UUID, Reservation] = field(default_factory=dict)

    def create_reservation(self, reservation: Reservation) -> Reservation:
        self.reservations[reservation.reservation_id] = reservation
        return reservation

    def get_reservation(
        self, organization_id: UUID, reservation_id: UUID
    ) -> Reservation:
        res = self.reservations.get(reservation_id)
        if res is None or res.organization_id != organization_id:
            raise ReservationNotFoundError(reservation_id)
        return res

    def update_reservation(self, reservation: Reservation) -> Reservation:
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
        results = [
            r
            for r in self.reservations.values()
            if r.organization_id == organization_id
        ]
        if book_id is not None:
            results = [r for r in results if r.book_id == book_id]
        if requester_user_id is not None:
            results = [r for r in results if r.requester_user_id == requester_user_id]
        if status is not None:
            results = [r for r in results if r.status == status]
        return sorted(
            results, key=lambda r: (r.queue_position, r.created_at, r.reservation_id)
        )

    def get_next_queue_position(self, organization_id: UUID, book_id: UUID) -> int:
        existing = [
            r.queue_position
            for r in self.reservations.values()
            if r.organization_id == organization_id and r.book_id == book_id
        ]
        return (max(existing) + 1) if existing else 1

    def get_next_pending_reservation(
        self, organization_id: UUID, book_id: UUID
    ) -> Reservation | None:
        pending = [
            r
            for r in self.reservations.values()
            if r.organization_id == organization_id
            and r.book_id == book_id
            and r.status == ReservationStatus.PENDING
        ]
        if not pending:
            return None
        pending.sort(key=lambda r: (r.queue_position, r.created_at, r.reservation_id))
        return pending[0]

    def get_active_reservation_for_user_and_book(
        self, organization_id: UUID, book_id: UUID, user_id: UUID
    ) -> Reservation | None:
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

    def get_copy(self, organization_id: UUID, copy_id: UUID) -> BookCopy:
        copy = self.copies.get(copy_id)
        if copy is None or copy.organization_id != organization_id:
            raise KeyError(copy_id)
        return copy

    def update_copy_status(
        self, organization_id: UUID, copy_id: UUID, to_status: str
    ) -> BookCopy:
        copy = self.get_copy(organization_id, copy_id)
        now = datetime.now(timezone.utc)
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
            updated_at=now,
        )
        self.copies[copy_id] = updated
        return updated

    def append_history(self, record: CopyStatusHistory) -> CopyStatusHistory:
        self.history.append(record)
        return record

    def get_available_copy_for_book(
        self, organization_id: UUID, book_id: UUID
    ) -> BookCopy | None:
        for copy in self.copies.values():
            if (
                copy.organization_id == organization_id
                and copy.book_id == book_id
                and copy.status == CopyStatus.AVAILABLE
            ):
                return copy
        return None


@dataclass
class _RecordingAuditedTransaction:
    audit_events: list[AuditEvent] = field(default_factory=list)
    outbox_events: list[OutboxEvent] = field(default_factory=list)

    def run(
        self,
        connection: Any,
        mutation: Any,
        audit_event: AuditEvent,
        outbox_events: Any,
    ) -> Any:
        result = mutation(connection)
        self.audit_events.append(audit_event)
        self.outbox_events.extend(outbox_events)
        return result


class _StaticAuthorizer:
    def __init__(self, allowed: set[tuple[UUID, str]] | None = None) -> None:
        self._allowed = allowed if allowed is not None else set()

    def allow(self, principal: Principal, permission: str) -> None:
        self._allowed.add((principal.user_id, permission))

    def require(self, principal: Principal, permission: str) -> None:
        if (principal.user_id, permission) not in self._allowed:
            raise AuthorizationDenied(f"Permission {permission} denied")


class _StubAccessTokenService:
    def verify(self, token: str) -> Principal:
        if token == "patron-a-token":
            return PATRON_A
        if token == "patron-a2-token":
            return PATRON_A2
        if token == "librarian-a-token":
            return LIBRARIAN_A
        if token == "patron-b-token":
            return PATRON_B
        raise ValueError(f"Unknown token: {token}")


@pytest.fixture
def reservation_env() -> dict[str, Any]:
    copy_store = _InMemoryCopyStore()
    reservation_store = _InMemoryReservationStore()
    authorizer = _StaticAuthorizer()
    tx = _RecordingAuditedTransaction()

    # Permissions
    authorizer.allow(PATRON_A, "reservation.create")
    authorizer.allow(PATRON_A, "reservation.read")
    authorizer.allow(PATRON_A2, "reservation.create")
    authorizer.allow(PATRON_A2, "reservation.read")
    authorizer.allow(PATRON_B, "reservation.create")
    authorizer.allow(PATRON_B, "reservation.read")

    authorizer.allow(LIBRARIAN_A, "reservation.create")
    authorizer.allow(LIBRARIAN_A, "reservation.read")
    authorizer.allow(LIBRARIAN_A, "reservation.manage")

    service = ReservationService(
        reservation_store=reservation_store,
        copy_store=copy_store,
        authorizer=authorizer,  # type: ignore[arg-type]
        transaction=tx,  # type: ignore[arg-type]
    )

    access_tokens = _StubAccessTokenService()
    app = create_app(
        AppConfig(
            readiness_probe=lambda: True,
            access_tokens=access_tokens,  # type: ignore[arg-type]
            authorization=authorizer,  # type: ignore[arg-type]
            reservation_service=service,
        )
    )
    client = app.test_client()

    book_id = uuid4()
    return {
        "client": client,
        "service": service,
        "store": reservation_store,
        "copy_store": copy_store,
        "authorizer": authorizer,
        "tx": tx,
        "book_id": book_id,
    }


def test_create_reservation_success(reservation_env: dict[str, Any]) -> None:
    client = reservation_env["client"]
    book_id = reservation_env["book_id"]

    res = client.post(
        "/api/v1/reservations",
        headers={"Authorization": "Bearer patron-a-token"},
        json={"book_id": str(book_id)},
    )
    assert res.status_code == 201
    data = res.get_json()
    assert data["book_id"] == str(book_id)
    assert data["requester_user_id"] == str(PATRON_A.user_id)
    assert data["queue_position"] == 1
    assert data["status"] == "pending"


def test_create_reservation_unauthorized(reservation_env: dict[str, Any]) -> None:
    client = reservation_env["client"]
    book_id = reservation_env["book_id"]

    res = client.post(
        "/api/v1/reservations",
        json={"book_id": str(book_id)},
    )
    assert res.status_code == 401


def test_create_reservation_duplicate_conflict(reservation_env: dict[str, Any]) -> None:
    client = reservation_env["client"]
    book_id = reservation_env["book_id"]

    res1 = client.post(
        "/api/v1/reservations",
        headers={"Authorization": "Bearer patron-a-token"},
        json={"book_id": str(book_id)},
    )
    assert res1.status_code == 201

    res2 = client.post(
        "/api/v1/reservations",
        headers={"Authorization": "Bearer patron-a-token"},
        json={"book_id": str(book_id)},
    )
    assert res2.status_code == 409
    assert res2.headers.get("Content-Type") == "application/problem+json"


def test_list_reservations_tenant_isolation(reservation_env: dict[str, Any]) -> None:
    client = reservation_env["client"]
    book_id = reservation_env["book_id"]

    # Patron A in Tenant A creates reservation
    client.post(
        "/api/v1/reservations",
        headers={"Authorization": "Bearer patron-a-token"},
        json={"book_id": str(book_id)},
    )

    # Patron B in Tenant B lists reservations
    res = client.get(
        "/api/v1/reservations",
        headers={"Authorization": "Bearer patron-b-token"},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["items"] == []


def test_cancel_reservation_endpoint(reservation_env: dict[str, Any]) -> None:
    client = reservation_env["client"]
    book_id = reservation_env["book_id"]

    create_res = client.post(
        "/api/v1/reservations",
        headers={"Authorization": "Bearer patron-a-token"},
        json={"book_id": str(book_id)},
    )
    res_id = create_res.get_json()["reservation_id"]

    cancel_res = client.post(
        f"/api/v1/reservations/{res_id}/cancel",
        headers={"Authorization": "Bearer patron-a-token"},
    )
    assert cancel_res.status_code == 200
    assert cancel_res.get_json()["status"] == "cancelled"
