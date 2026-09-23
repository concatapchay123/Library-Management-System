"""Contract and API tests for core circulation loan lifecycle."""

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
from openlibrary.modules.core.application.copy_status import CopyStatusHistory
from openlibrary.modules.core.application.inventory import BookCopy
from openlibrary.modules.core.application.loans import (
    Loan,
    LoanService,
)
from openlibrary.modules.core.domain.copy_status import CopyStatus
from openlibrary.modules.core.domain.loans import LoanStatus
from openlibrary.modules.ops.application.persistence import (
    AuditEvent,
    OutboxEvent,
)

ORGANIZATION_A = uuid4()
ORGANIZATION_B = uuid4()
BORROWER_A = Principal(uuid4(), ORGANIZATION_A, uuid4())
LIBRARIAN_A = Principal(uuid4(), ORGANIZATION_A, uuid4())
BORROWER_B = Principal(uuid4(), ORGANIZATION_B, uuid4())


@dataclass
class _InMemoryLoanStore:
    loans: dict[UUID, Loan] = field(default_factory=dict)

    def create_loan(self, loan: Loan) -> Loan:
        self.loans[loan.loan_id] = loan
        return loan

    def get_loan(self, organization_id: UUID, loan_id: UUID) -> Loan:
        loan = self.loans.get(loan_id)
        if loan is None or loan.organization_id != organization_id:
            raise KeyError(loan_id)
        return loan

    def update_loan(self, loan: Loan) -> Loan:
        if (
            loan.loan_id not in self.loans
            or self.loans[loan.loan_id].organization_id != loan.organization_id
        ):
            raise KeyError(loan.loan_id)
        self.loans[loan.loan_id] = loan
        return loan

    def list_loans(
        self,
        organization_id: UUID,
        *,
        borrower_user_id: UUID | None = None,
        copy_id: UUID | None = None,
        status: str | None = None,
    ) -> list[Loan]:
        results = [
            loan_item
            for loan_item in self.loans.values()
            if loan_item.organization_id == organization_id
        ]
        if borrower_user_id is not None:
            results = [
                loan_item
                for loan_item in results
                if loan_item.borrower_user_id == borrower_user_id
            ]
        if copy_id is not None:
            results = [
                loan_item for loan_item in results if loan_item.copy_id == copy_id
            ]
        if status is not None:
            results = [loan_item for loan_item in results if loan_item.status == status]
        return sorted(results, key=lambda loan_item: loan_item.created_at, reverse=True)

    def count_active_loans_for_borrower(
        self, organization_id: UUID, borrower_user_id: UUID
    ) -> int:
        return sum(
            1
            for loan_item in self.loans.values()
            if loan_item.organization_id == organization_id
            and loan_item.borrower_user_id == borrower_user_id
            and loan_item.status == LoanStatus.CHECKED_OUT
        )

    def get_active_loan_for_copy(
        self, organization_id: UUID, copy_id: UUID
    ) -> Loan | None:
        for loan_item in self.loans.values():
            if (
                loan_item.organization_id == organization_id
                and loan_item.copy_id == copy_id
                and loan_item.status == LoanStatus.CHECKED_OUT
            ):
                return loan_item
        return None


@dataclass
class _InMemoryCopyStore:
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

    def list_history_for_copy(
        self, organization_id: UUID, copy_id: UUID
    ) -> list[CopyStatusHistory]:
        return [
            h
            for h in self.history
            if h.organization_id == organization_id and h.copy_id == copy_id
        ]


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
        if token == "borrower-a-token":
            return BORROWER_A
        if token == "librarian-a-token":
            return LIBRARIAN_A
        if token == "borrower-b-token":
            return BORROWER_B
        raise ValueError(f"Unknown token: {token}")


@pytest.fixture
def loan_env() -> dict[str, Any]:
    copy_store = _InMemoryCopyStore()
    loan_store = _InMemoryLoanStore()
    authorizer = _StaticAuthorizer()
    tx = _RecordingAuditedTransaction()

    # Seed borrower permissions
    authorizer.allow(BORROWER_A, "circulation.request")
    authorizer.allow(BORROWER_A, "circulation.read")
    authorizer.allow(BORROWER_B, "circulation.request")
    authorizer.allow(BORROWER_B, "circulation.read")

    # Seed librarian permissions
    authorizer.allow(LIBRARIAN_A, "circulation.request")
    authorizer.allow(LIBRARIAN_A, "circulation.approve")
    authorizer.allow(LIBRARIAN_A, "circulation.checkout")
    authorizer.allow(LIBRARIAN_A, "circulation.return")
    authorizer.allow(LIBRARIAN_A, "circulation.read")
    authorizer.allow(LIBRARIAN_A, "circulation.manage")

    # Seed a copy in Tenant A
    now = datetime.now(timezone.utc)
    copy_id = uuid4()
    book_id = uuid4()
    loc_id = uuid4()
    copy = BookCopy(
        copy_id=copy_id,
        organization_id=ORGANIZATION_A,
        book_id=book_id,
        barcode="BC-001",
        location_id=loc_id,
        status=CopyStatus.AVAILABLE,
        condition_code="good",
        acquired_at=now,
        created_at=now,
        updated_at=now,
    )
    copy_store.copies[copy_id] = copy

    loan_service = LoanService(
        loan_store=loan_store,
        copy_store=copy_store,
        authorizer=authorizer,
        transaction=tx,
    )

    app = create_app(
        AppConfig(
            readiness_probe=lambda: True,
            access_tokens=_StubAccessTokenService(),  # type: ignore[arg-type]
            authorization=authorizer,  # type: ignore[arg-type]
            loan_service=loan_service,
        )
    )

    return {
        "client": app.test_client(),
        "loan_store": loan_store,
        "copy_store": copy_store,
        "copy_id": copy_id,
        "tx": tx,
    }


def test_self_service_loan_request_success(loan_env: dict[str, Any]) -> None:
    client = loan_env["client"]
    copy_id = loan_env["copy_id"]
    tx = loan_env["tx"]

    res = client.post(
        "/api/v1/loans",
        headers={"Authorization": "Bearer borrower-a-token"},
        json={"copy_id": str(copy_id)},
    )
    assert res.status_code == 201
    data = res.get_json()
    assert data["copy_id"] == str(copy_id)
    assert data["borrower_user_id"] == str(BORROWER_A.user_id)
    assert data["status"] == "requested"
    assert data["request_status"] == "pending"
    assert data["loan_status"] == "requested"

    # Verifies audit and outbox records written atomically
    assert any(
        a.action == "loan.requested" and a.entity_id == UUID(data["loan_id"])
        for a in tx.audit_events
    )
    assert any(
        o.event_type == "circulation.loan_requested"
        and o.aggregate_id == UUID(data["loan_id"])
        for o in tx.outbox_events
    )


def test_self_service_request_cannot_checkout_without_approval(
    loan_env: dict[str, Any],
) -> None:
    client = loan_env["client"]
    copy_id = loan_env["copy_id"]

    # 1. Borrower requests copy
    req_res = client.post(
        "/api/v1/loans",
        headers={"Authorization": "Bearer borrower-a-token"},
        json={"copy_id": str(copy_id)},
    )
    assert req_res.status_code == 201
    loan_id = req_res.get_json()["loan_id"]

    # 2. Attempt to checkout directly while in 'requested' state
    co_res = client.post(
        f"/api/v1/loans/{loan_id}/checkout",
        headers={"Authorization": "Bearer librarian-a-token"},
        json={},
    )
    assert co_res.status_code == 409
    body = co_res.get_json()
    assert (
        body["type"]
        == "https://openlibraryos.example/problems/invalid-loan-status-transition"
    )
    assert "requested" in body["detail"]

    # Copy remains available
    copy = loan_env["copy_store"].get_copy(ORGANIZATION_A, copy_id)
    assert copy.status == CopyStatus.AVAILABLE


def test_approval_and_checkout_lifecycle(loan_env: dict[str, Any]) -> None:
    client = loan_env["client"]
    copy_id = loan_env["copy_id"]
    tx = loan_env["tx"]

    # 1. Request
    req_res = client.post(
        "/api/v1/loans",
        headers={"Authorization": "Bearer borrower-a-token"},
        json={"copy_id": str(copy_id)},
    )
    loan_id = req_res.get_json()["loan_id"]

    # 2. Librarian approval
    app_res = client.post(
        f"/api/v1/loans/{loan_id}/approve",
        headers={"Authorization": "Bearer librarian-a-token"},
        json={},
    )
    assert app_res.status_code == 200
    app_data = app_res.get_json()
    assert app_data["status"] == "approved"
    assert app_data["approved_at"] is not None

    # Audit & outbox check
    assert any(a.action == "loan.approved" for a in tx.audit_events)
    assert any(o.event_type == "circulation.loan_approved" for o in tx.outbox_events)

    # 3. Checkout approved loan
    co_res = client.post(
        f"/api/v1/loans/{loan_id}/checkout",
        headers={"Authorization": "Bearer librarian-a-token"},
        json={"duration_days": 14},
    )
    assert co_res.status_code == 200
    co_data = co_res.get_json()
    assert co_data["status"] == "checked_out"
    assert co_data["checked_out_at"] is not None
    assert co_data["due_at"] is not None

    # Copy status must be borrowed atomically
    copy = loan_env["copy_store"].get_copy(ORGANIZATION_A, copy_id)
    assert copy.status == CopyStatus.BORROWED
    assert any(
        h.to_status == CopyStatus.BORROWED for h in loan_env["copy_store"].history
    )


def test_desk_checkout_invokes_approval_and_same_checkout_service(
    loan_env: dict[str, Any],
) -> None:
    client = loan_env["client"]
    copy_id = loan_env["copy_id"]
    tx = loan_env["tx"]

    # Desk checkout for borrower A
    res = client.post(
        "/api/v1/loans/desk-checkout",
        headers={"Authorization": "Bearer librarian-a-token"},
        json={
            "copy_id": str(copy_id),
            "borrower_user_id": str(BORROWER_A.user_id),
            "duration_days": 21,
        },
    )
    assert res.status_code == 201
    data = res.get_json()
    assert data["status"] == "checked_out"
    assert data["approved_at"] is not None
    assert data["checked_out_at"] is not None
    assert data["due_at"] is not None

    # Copy status must be borrowed
    copy = loan_env["copy_store"].get_copy(ORGANIZATION_A, copy_id)
    assert copy.status == CopyStatus.BORROWED

    # Invariants evidence: explicit approval occurred before checkout
    actions = [a.action for a in tx.audit_events]
    assert "loan.requested" in actions
    assert "loan.approved" in actions
    assert "loan.checked_out" in actions


def test_desk_checkout_fails_if_copy_not_available(loan_env: dict[str, Any]) -> None:
    client = loan_env["client"]
    copy_id = loan_env["copy_id"]

    # Set copy to borrowed first
    loan_env["copy_store"].update_copy_status(
        ORGANIZATION_A, copy_id, CopyStatus.BORROWED
    )

    res = client.post(
        "/api/v1/loans/desk-checkout",
        headers={"Authorization": "Bearer librarian-a-token"},
        json={
            "copy_id": str(copy_id),
            "borrower_user_id": str(BORROWER_A.user_id),
        },
    )
    assert res.status_code == 409
    body = res.get_json()
    assert body["type"] in (
        "https://openlibraryos.example/problems/copy-not-available",
        "https://openlibraryos.example/problems/invalid-copy-status-transition",
    )


def test_return_changes_loan_and_copy_state_atomically(
    loan_env: dict[str, Any],
) -> None:
    client = loan_env["client"]
    copy_id = loan_env["copy_id"]
    tx = loan_env["tx"]

    # 1. Desk checkout
    co_res = client.post(
        "/api/v1/loans/desk-checkout",
        headers={"Authorization": "Bearer librarian-a-token"},
        json={
            "copy_id": str(copy_id),
            "borrower_user_id": str(BORROWER_A.user_id),
        },
    )
    loan_id = co_res.get_json()["loan_id"]

    # 2. Return loan
    ret_res = client.post(
        f"/api/v1/loans/{loan_id}/return",
        headers={"Authorization": "Bearer librarian-a-token"},
        json={},
    )
    assert ret_res.status_code == 200
    ret_data = ret_res.get_json()
    assert ret_data["status"] == "returned"
    assert ret_data["returned_at"] is not None

    # Copy status must be available atomically
    copy = loan_env["copy_store"].get_copy(ORGANIZATION_A, copy_id)
    assert copy.status == CopyStatus.AVAILABLE

    # Check copy status history append
    history = loan_env["copy_store"].list_history_for_copy(ORGANIZATION_A, copy_id)
    assert any(
        h.from_status == CopyStatus.BORROWED and h.to_status == CopyStatus.AVAILABLE
        for h in history
    )

    # Check audit & outbox records
    assert any(
        a.action == "loan.returned" and a.entity_id == UUID(loan_id)
        for a in tx.audit_events
    )
    assert any(
        o.event_type == "circulation.loan_returned" and o.aggregate_id == UUID(loan_id)
        for o in tx.outbox_events
    )


def test_invalid_lifecycle_transitions_return_stable_errors(
    loan_env: dict[str, Any],
) -> None:
    client = loan_env["client"]
    copy_id = loan_env["copy_id"]

    # Request loan
    req_res = client.post(
        "/api/v1/loans",
        headers={"Authorization": "Bearer borrower-a-token"},
        json={"copy_id": str(copy_id)},
    )
    loan_id = req_res.get_json()["loan_id"]

    # Attempting to return a loan in requested state fails
    ret_res = client.post(
        f"/api/v1/loans/{loan_id}/return",
        headers={"Authorization": "Bearer librarian-a-token"},
        json={},
    )
    assert ret_res.status_code == 409
    assert (
        ret_res.get_json()["type"]
        == "https://openlibraryos.example/problems/invalid-loan-status-transition"
    )


def test_rejection_lifecycle(loan_env: dict[str, Any]) -> None:
    client = loan_env["client"]
    copy_id = loan_env["copy_id"]
    tx = loan_env["tx"]

    # Request loan
    req_res = client.post(
        "/api/v1/loans",
        headers={"Authorization": "Bearer borrower-a-token"},
        json={"copy_id": str(copy_id)},
    )
    loan_id = req_res.get_json()["loan_id"]

    # Reject loan
    rej_res = client.post(
        f"/api/v1/loans/{loan_id}/reject",
        headers={"Authorization": "Bearer librarian-a-token"},
        json={"reason": "Copy reserved for reference only"},
    )
    assert rej_res.status_code == 200
    rej_data = rej_res.get_json()
    assert rej_data["status"] == "rejected"
    assert rej_data["request_status"] == "rejected"

    assert any(a.action == "loan.rejected" for a in tx.audit_events)
    assert any(o.event_type == "circulation.loan_rejected" for o in tx.outbox_events)


def test_tenant_isolation_loans(loan_env: dict[str, Any]) -> None:
    client = loan_env["client"]
    copy_id = loan_env["copy_id"]

    # Borrower A creates loan in Tenant A
    req_res = client.post(
        "/api/v1/loans",
        headers={"Authorization": "Bearer borrower-a-token"},
        json={"copy_id": str(copy_id)},
    )
    loan_id = req_res.get_json()["loan_id"]

    # Borrower B (Tenant B) cannot get or approve Tenant A's loan
    get_res = client.get(
        f"/api/v1/loans/{loan_id}",
        headers={"Authorization": "Bearer borrower-b-token"},
    )
    assert get_res.status_code == 404


def test_list_and_get_loans_filtering(loan_env: dict[str, Any]) -> None:
    client = loan_env["client"]
    copy_id = loan_env["copy_id"]

    # Request loan
    req_res = client.post(
        "/api/v1/loans",
        headers={"Authorization": "Bearer borrower-a-token"},
        json={"copy_id": str(copy_id)},
    )
    loan_id = req_res.get_json()["loan_id"]

    # 1. Get loan by ID
    get_res = client.get(
        f"/api/v1/loans/{loan_id}",
        headers={"Authorization": "Bearer borrower-a-token"},
    )
    assert get_res.status_code == 200
    assert get_res.get_json()["loan_id"] == loan_id

    # 2. List loans with filters as librarian
    list_res = client.get(
        f"/api/v1/loans?borrower_user_id={BORROWER_A.user_id}&status=requested",
        headers={"Authorization": "Bearer librarian-a-token"},
    )
    assert list_res.status_code == 200
    items = list_res.get_json()["items"]
    assert len(items) == 1
    assert items[0]["loan_id"] == loan_id

    # 3. List loans as borrower (scoped only to self)
    list_borrower_res = client.get(
        "/api/v1/loans",
        headers={"Authorization": "Bearer borrower-a-token"},
    )
    assert list_borrower_res.status_code == 200
    b_items = list_borrower_res.get_json()["items"]
    assert all(item["borrower_user_id"] == str(BORROWER_A.user_id) for item in b_items)


def test_authorization_denied_on_unauthorized_endpoints(
    loan_env: dict[str, Any],
) -> None:
    client = loan_env["client"]
    copy_id = loan_env["copy_id"]

    # Borrower A attempts to approve or checkout (lacks circulation.approve and circulation.checkout)
    app_res = client.post(
        f"/api/v1/loans/{uuid4()}/approve",
        headers={"Authorization": "Bearer borrower-a-token"},
        json={},
    )
    assert app_res.status_code == 403

    co_res = client.post(
        f"/api/v1/loans/{uuid4()}/checkout",
        headers={"Authorization": "Bearer borrower-a-token"},
        json={},
    )
    assert co_res.status_code == 403

    desk_res = client.post(
        "/api/v1/loans/desk-checkout",
        headers={"Authorization": "Bearer borrower-a-token"},
        json={
            "copy_id": str(copy_id),
            "borrower_user_id": str(BORROWER_A.user_id),
        },
    )
    assert desk_res.status_code == 403


def test_active_loan_limit_exceeded(loan_env: dict[str, Any]) -> None:
    client = loan_env["client"]
    copy_store = loan_env["copy_store"]
    loan_store = loan_env["loan_store"]

    now = datetime.now(timezone.utc)
    # Seed 5 active loans for BORROWER_A
    for _ in range(5):
        cid = uuid4()
        copy_store.copies[cid] = BookCopy(
            copy_id=cid,
            organization_id=ORGANIZATION_A,
            book_id=uuid4(),
            barcode=f"BC-{uuid4().hex[:6]}",
            location_id=uuid4(),
            status=CopyStatus.BORROWED,
            condition_code="good",
            acquired_at=now,
            created_at=now,
            updated_at=now,
        )
        lid = uuid4()
        loan_store.create_loan(
            Loan(
                loan_id=lid,
                organization_id=ORGANIZATION_A,
                copy_id=cid,
                borrower_user_id=BORROWER_A.user_id,
                status=LoanStatus.CHECKED_OUT,
                loan_status=LoanStatus.CHECKED_OUT,
                request_status="fulfilled",
                requested_at=now,
                created_at=now,
                updated_at=now,
            )
        )

    # 6th request attempt must fail
    res = client.post(
        "/api/v1/loans",
        headers={"Authorization": "Bearer borrower-a-token"},
        json={"copy_id": str(loan_env["copy_id"])},
    )
    assert res.status_code == 409
    assert (
        res.get_json()["type"]
        == "https://openlibraryos.example/problems/loan-not-eligible"
    )
