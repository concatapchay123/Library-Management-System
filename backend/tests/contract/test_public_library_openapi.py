"""Consumer contract tests for public library endpoints in OpenAPI v1 contract."""

from __future__ import annotations

import json
from pathlib import Path


def load_contract() -> dict[str, object]:
    path = Path(__file__).resolve().parents[3] / "contracts" / "openapi" / "v1.yaml"
    return json.loads(path.read_text(encoding="utf-8"))


def test_public_library_contract_exposes_expected_endpoints() -> None:
    contract = load_contract()
    paths = contract["paths"]

    # 1. Members endpoints
    assert "/public-library/members" in paths
    assert {"get", "post"} <= set(paths["/public-library/members"])
    assert paths["/public-library/members"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/PublicLibraryMemberList"}
    assert paths["/public-library/members"]["post"]["responses"]["201"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/PublicLibraryMember"}

    assert "/public-library/members/{member_id}" in paths
    assert "get" in paths["/public-library/members/{member_id}"]

    assert "/public-library/members/{member_id}/status" in paths
    assert "patch" in paths["/public-library/members/{member_id}/status"]

    assert "/public-library/members/by-user/{user_id}" in paths
    assert "get" in paths["/public-library/members/by-user/{user_id}"]

    # 2. Membership plans endpoints
    assert "/public-library/membership-plans" in paths
    assert {"get", "post"} <= set(paths["/public-library/membership-plans"])
    assert paths["/public-library/membership-plans"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/PublicLibraryMembershipPlanList"
    }

    assert "/public-library/membership-plans/{plan_id}" in paths
    assert {"get", "put"} <= set(paths["/public-library/membership-plans/{plan_id}"])

    assert "/public-library/membership-plans/seed" in paths
    assert "post" in paths["/public-library/membership-plans/seed"]

    # 3. Subscriptions endpoints
    assert "/public-library/subscriptions" in paths
    assert {"get", "post"} <= set(paths["/public-library/subscriptions"])
    assert paths["/public-library/subscriptions"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/PublicLibrarySubscriptionList"}

    assert "/public-library/subscriptions/{subscription_id}" in paths
    assert "get" in paths["/public-library/subscriptions/{subscription_id}"]

    assert "/public-library/subscriptions/{subscription_id}/cancel" in paths
    assert "post" in paths["/public-library/subscriptions/{subscription_id}/cancel"]

    # 4. Fines endpoints
    assert "/public-library/fines" in paths
    assert {"get", "post"} <= set(paths["/public-library/fines"])
    assert paths["/public-library/fines"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/PublicLibraryFineList"}
    assert paths["/public-library/fines"]["post"]["responses"]["201"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/PublicLibraryFine"}

    assert "/public-library/fines/{fine_id}" in paths
    assert "get" in paths["/public-library/fines/{fine_id}"]

    assert "/public-library/fines/calculate" in paths
    assert "post" in paths["/public-library/fines/calculate"]

    assert "/public-library/fines/{fine_id}/waive" in paths
    assert "post" in paths["/public-library/fines/{fine_id}/waive"]

    assert "/public-library/fines/{fine_id}/allocations" in paths
    assert "get" in paths["/public-library/fines/{fine_id}/allocations"]

    # 5. Invoices endpoints
    assert "/public-library/invoices" in paths
    assert {"get", "post"} <= set(paths["/public-library/invoices"])
    assert paths["/public-library/invoices"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/PublicLibraryInvoiceList"}
    assert paths["/public-library/invoices"]["post"]["responses"]["201"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/PublicLibraryInvoice"}

    assert "/public-library/invoices/{invoice_id}" in paths
    assert {"get", "put"} <= set(paths["/public-library/invoices/{invoice_id}"])

    assert "/public-library/invoices/{invoice_id}/void" in paths
    assert "post" in paths["/public-library/invoices/{invoice_id}/void"]

    # 6. Payments endpoints
    assert "/public-library/payments" in paths
    assert {"get", "post"} <= set(paths["/public-library/payments"])
    assert paths["/public-library/payments"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/PublicLibraryPaymentList"}
    assert paths["/public-library/payments"]["post"]["responses"]["201"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/PublicLibraryPayment"}

    assert "/public-library/payments/{payment_id}" in paths
    assert "get" in paths["/public-library/payments/{payment_id}"]

    assert "/public-library/payments/{payment_id}/allocations" in paths
    assert "get" in paths["/public-library/payments/{payment_id}/allocations"]

    # 7. Allocations endpoints
    assert "/public-library/allocations" in paths
    assert {"get", "post"} <= set(paths["/public-library/allocations"])
    assert paths["/public-library/allocations"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/PublicLibraryPaymentAllocationList"}
    assert paths["/public-library/allocations"]["post"]["responses"]["201"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/PublicLibraryPaymentAllocation"}

    assert "/public-library/allocations/{allocation_id}" in paths
    assert "get" in paths["/public-library/allocations/{allocation_id}"]
