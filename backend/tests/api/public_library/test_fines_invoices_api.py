"""HTTP API tests for public library fines, invoices, payments, and allocations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from flask import Flask

from openlibrary.app.correlation import install_request_correlation
from openlibrary.app.errors import install_problem_details_handlers
from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.authorization import (
    AuthorizationDenied,
    AuthorizationPort,
)
from openlibrary.modules.public_library.api import create_public_library_blueprint
from openlibrary.modules.public_library.application import (
    PublicLibraryFinanceService,
    PublicLibraryService,
)
from openlibrary.modules.public_library.domain import (
    Member,
    MemberStatus,
)
from tests.integration.public_library.test_fines_invoices import (
    _InMemoryPublicLibraryFinanceStore,
)


class _StubAccessTokenService:
    def __init__(self, principal: Principal) -> None:
        self.principal = principal

    def verify(self, token: str) -> Principal:
        from openlibrary.modules.core.application.access_tokens import (
            TokenVerificationError,
        )

        if token == "valid-token":
            return self.principal
        raise TokenVerificationError("Invalid token")


class _ConfigurableAuthorizer(AuthorizationPort):
    def __init__(self, granted_permissions: set[str]) -> None:
        self.granted_permissions = granted_permissions

    def require(self, actor: Principal, permission: str) -> None:
        if permission not in self.granted_permissions:
            raise AuthorizationDenied(f"Permission '{permission}' denied")


def _build_test_client(
    store: _InMemoryPublicLibraryFinanceStore,
    permissions: set[str] | None = None,
) -> tuple[Any, UUID, UUID]:
    org_id = uuid4()
    user_id = uuid4()
    principal = Principal(user_id=user_id, organization_id=org_id, session_id=uuid4())
    store.edition_enabled_orgs.add(org_id)

    access_tokens = _StubAccessTokenService(principal)
    perms = (
        permissions
        if permissions is not None
        else {
            "public_library.read",
            "public_library.manage",
        }
    )
    authorizer = _ConfigurableAuthorizer(perms)
    service = PublicLibraryService(store=store, authorizer=authorizer)
    finance_service = PublicLibraryFinanceService(store=store, authorizer=authorizer)

    app = Flask(__name__)
    install_request_correlation(app)
    install_problem_details_handlers(app)

    app.register_blueprint(
        create_public_library_blueprint(
            service=service,
            access_tokens=access_tokens,  # type: ignore[arg-type]
            tenant_request_context=None,
            url_prefix="/api/v1/public-library",
            finance_service=finance_service,
        )
    )

    return app.test_client(), org_id, user_id


def _create_test_member(
    store: _InMemoryPublicLibraryFinanceStore, org_id: UUID
) -> Member:
    member_id = uuid4()
    member = Member(
        member_id=member_id,
        organization_id=org_id,
        user_id=uuid4(),
        member_number="MEM-001",
        status=MemberStatus.ACTIVE,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    store.create_member(member)
    return member


def test_assess_fine_endpoint_success_and_retrieval() -> None:
    store = _InMemoryPublicLibraryFinanceStore()
    client, org_id, _ = _build_test_client(store)
    member = _create_test_member(store, org_id)

    resp = client.post(
        "/api/v1/public-library/fines",
        headers={"Authorization": "Bearer valid-token"},
        json={
            "member_id": str(member.member_id),
            "amount": "25.5000",
            "currency": "USD",
            "reason": "Overdue book loan",
        },
    )
    assert resp.status_code == 201
    fine_data = resp.get_json()
    assert fine_data["amount"] == "25.5000"
    assert fine_data["currency"] == "USD"
    assert fine_data["status"] == "assessed"
    assert fine_data["member_id"] == str(member.member_id)
    fine_id = fine_data["fine_id"]

    # Get by ID
    get_resp = client.get(
        f"/api/v1/public-library/fines/{fine_id}",
        headers={"Authorization": "Bearer valid-token"},
    )
    assert get_resp.status_code == 200
    assert get_resp.get_json()["fine_id"] == fine_id

    # List fines
    list_resp = client.get(
        "/api/v1/public-library/fines",
        headers={"Authorization": "Bearer valid-token"},
    )
    assert list_resp.status_code == 200
    items = list_resp.get_json()["items"]
    assert len(items) == 1
    assert items[0]["fine_id"] == fine_id


def test_assess_fine_endpoint_rejects_floating_point() -> None:
    store = _InMemoryPublicLibraryFinanceStore()
    client, org_id, _ = _build_test_client(store)
    member = _create_test_member(store, org_id)

    resp = client.post(
        "/api/v1/public-library/fines",
        headers={"Authorization": "Bearer valid-token"},
        json={
            "member_id": str(member.member_id),
            "amount": 25.50,  # JSON numeric float
            "currency": "USD",
            "reason": "Late return",
        },
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert "Floating-point money amounts are rejected" in body["detail"]


def test_calculate_overdue_fine_endpoint() -> None:
    store = _InMemoryPublicLibraryFinanceStore()
    client, org_id, _ = _build_test_client(store)

    due_at = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    return_at = datetime.now(timezone.utc).isoformat()

    # Success with decimal string
    resp = client.post(
        "/api/v1/public-library/fines/calculate",
        headers={"Authorization": "Bearer valid-token"},
        json={
            "due_at": due_at,
            "effective_return_at": return_at,
            "daily_rate": "2.0000",
            "currency": "USD",
            "max_fine": "20.0000",
        },
    )
    assert resp.status_code == 200
    calc_data = resp.get_json()
    assert calc_data["currency"] == "USD"
    assert Decimal(calc_data["amount"]) == Decimal("10.0000")

    # Reject float in daily_rate
    resp_float = client.post(
        "/api/v1/public-library/fines/calculate",
        headers={"Authorization": "Bearer valid-token"},
        json={
            "due_at": due_at,
            "effective_return_at": return_at,
            "daily_rate": 2.50,
            "currency": "USD",
        },
    )
    assert resp_float.status_code == 400
    assert "Floating-point" in resp_float.get_json()["detail"]


def test_waive_fine_endpoint() -> None:
    store = _InMemoryPublicLibraryFinanceStore()
    client, org_id, _ = _build_test_client(store)
    member = _create_test_member(store, org_id)

    assess_resp = client.post(
        "/api/v1/public-library/fines",
        headers={"Authorization": "Bearer valid-token"},
        json={
            "member_id": str(member.member_id),
            "amount": "10.0000",
            "currency": "USD",
            "reason": "Damaged cover",
        },
    )
    fine_id = assess_resp.get_json()["fine_id"]

    # Waive fine
    waive_resp = client.post(
        f"/api/v1/public-library/fines/{fine_id}/waive",
        headers={"Authorization": "Bearer valid-token"},
        json={"reason": "Customer service courtesy"},
    )
    assert waive_resp.status_code == 200
    assert waive_resp.get_json()["status"] == "waived"

    # Attempting to waive again should return 409 Conflict
    waive_again = client.post(
        f"/api/v1/public-library/fines/{fine_id}/waive",
        headers={"Authorization": "Bearer valid-token"},
        json={"reason": "Repeat waiver"},
    )
    assert waive_again.status_code == 409


def test_issue_invoice_endpoint_and_immutability() -> None:
    store = _InMemoryPublicLibraryFinanceStore()
    client, org_id, _ = _build_test_client(store)
    member = _create_test_member(store, org_id)

    # Issue invoice
    issue_resp = client.post(
        "/api/v1/public-library/invoices",
        headers={"Authorization": "Bearer valid-token"},
        json={
            "member_id": str(member.member_id),
            "currency": "USD",
            "tax": "2.0000",
            "lines": [
                {
                    "description": "Lost book replacement",
                    "quantity": 1,
                    "unit_price": "30.0000",
                    "amount": "30.0000",
                },
                {
                    "description": "Processing fee",
                    "quantity": 1,
                    "unit_price": "5.0000",
                    "amount": "5.0000",
                },
            ],
        },
    )
    assert issue_resp.status_code == 201
    inv_data = issue_resp.get_json()
    assert inv_data["subtotal"] == "35.0000"
    assert inv_data["tax"] == "2.0000"
    assert inv_data["total"] == "37.0000"
    assert inv_data["status"] == "issued"
    assert len(inv_data["lines"]) == 2
    invoice_id = inv_data["invoice_id"]

    # Verify immutability: attempting to modify lines returns 409 Financial Conflict
    mod_resp = client.put(
        f"/api/v1/public-library/invoices/{invoice_id}/lines",
        headers={"Authorization": "Bearer valid-token"},
        json={"lines": []},
    )
    assert mod_resp.status_code == 409
    assert "immutable" in mod_resp.get_json()["detail"]

    # Void invoice
    void_resp = client.post(
        f"/api/v1/public-library/invoices/{invoice_id}/void",
        headers={"Authorization": "Bearer valid-token"},
        json={"reason": "Incorrect assessment"},
    )
    assert void_resp.status_code == 200
    assert void_resp.get_json()["status"] == "void"


def test_payment_and_allocation_lifecycle() -> None:
    store = _InMemoryPublicLibraryFinanceStore()
    client, org_id, _ = _build_test_client(store)
    member = _create_test_member(store, org_id)

    # Assess fine: 20.00 USD
    fine_resp = client.post(
        "/api/v1/public-library/fines",
        headers={"Authorization": "Bearer valid-token"},
        json={
            "member_id": str(member.member_id),
            "amount": "20.0000",
            "currency": "USD",
            "reason": "Late fee",
        },
    )
    fine_id = fine_resp.get_json()["fine_id"]

    # Record payment: 50.00 USD
    pay_resp = client.post(
        "/api/v1/public-library/payments",
        headers={"Authorization": "Bearer valid-token"},
        json={
            "member_id": str(member.member_id),
            "amount": "50.0000",
            "currency": "USD",
            "provider": "manual",
        },
    )
    assert pay_resp.status_code == 201
    pay_data = pay_resp.get_json()
    assert pay_data["amount"] == "50.0000"
    payment_id = pay_data["payment_id"]

    # Allocate partial payment: 12.00 USD to fine
    alloc_resp = client.post(
        "/api/v1/public-library/allocations",
        headers={"Authorization": "Bearer valid-token"},
        json={
            "payment_id": payment_id,
            "fine_id": fine_id,
            "amount": "12.0000",
        },
    )
    assert alloc_resp.status_code == 201
    alloc_data = alloc_resp.get_json()
    assert alloc_data["amount"] == "12.0000"
    alloc_id = alloc_data["allocation_id"]

    # Verify fine is now partially_paid
    fine_after = client.get(
        f"/api/v1/public-library/fines/{fine_id}",
        headers={"Authorization": "Bearer valid-token"},
    ).get_json()
    assert fine_after["status"] == "partially_paid"

    # Get allocation by ID
    get_alloc = client.get(
        f"/api/v1/public-library/allocations/{alloc_id}",
        headers={"Authorization": "Bearer valid-token"},
    )
    assert get_alloc.status_code == 200

    # List fine allocations
    fine_allocs = client.get(
        f"/api/v1/public-library/fines/{fine_id}/allocations",
        headers={"Authorization": "Bearer valid-token"},
    )
    assert fine_allocs.status_code == 200
    assert len(fine_allocs.get_json()["items"]) == 1

    # List payment allocations
    pay_allocs = client.get(
        f"/api/v1/public-library/payments/{payment_id}/allocations",
        headers={"Authorization": "Bearer valid-token"},
    )
    assert pay_allocs.status_code == 200
    assert len(pay_allocs.get_json()["items"]) == 1

    # Over-allocation: allocate 10.00 USD more (total 22.00 > 20.00 fine) -> 409 Conflict
    over_resp = client.post(
        "/api/v1/public-library/allocations",
        headers={"Authorization": "Bearer valid-token"},
        json={
            "payment_id": payment_id,
            "fine_id": fine_id,
            "amount": "10.0000",
        },
    )
    assert over_resp.status_code == 409
    assert "exceeds" in over_resp.get_json()["detail"]


def test_allocation_rejects_floating_point() -> None:
    store = _InMemoryPublicLibraryFinanceStore()
    client, org_id, _ = _build_test_client(store)
    _ = _create_test_member(store, org_id)

    resp = client.post(
        "/api/v1/public-library/allocations",
        headers={"Authorization": "Bearer valid-token"},
        json={
            "payment_id": str(uuid4()),
            "fine_id": str(uuid4()),
            "amount": 10.50,  # float
        },
    )
    assert resp.status_code == 400
    assert "Floating-point money amounts are rejected" in resp.get_json()["detail"]


def test_finance_endpoints_require_permissions() -> None:
    store = _InMemoryPublicLibraryFinanceStore()
    # Read-only user without manage permission
    client, org_id, _ = _build_test_client(store, permissions={"public_library.read"})
    member = _create_test_member(store, org_id)

    # Attempt to assess fine without public_library.manage
    resp = client.post(
        "/api/v1/public-library/fines",
        headers={"Authorization": "Bearer valid-token"},
        json={
            "member_id": str(member.member_id),
            "amount": "10.0000",
            "currency": "USD",
            "reason": "Fine",
        },
    )
    assert resp.status_code == 403
