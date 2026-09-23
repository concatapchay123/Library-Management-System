"""Consumer contract tests for circulation loan endpoints."""

from __future__ import annotations

import json
from pathlib import Path


def load_contract() -> dict[str, object]:
    path = Path(__file__).resolve().parents[3] / "contracts" / "openapi" / "v1.yaml"
    return json.loads(path.read_text(encoding="utf-8"))


def test_loans_contract_exposes_full_lifecycle_endpoints() -> None:
    contract = load_contract()
    paths = contract["paths"]

    # 1. Base loans endpoints
    assert {"get", "post"} <= set(paths["/loans"])
    assert paths["/loans"]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/LoanPage"}
    assert paths["/loans"]["post"]["responses"]["201"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/Loan"}
    assert "409" in paths["/loans"]["post"]["responses"]

    # 2. Desk checkout endpoint
    assert "post" in paths["/loans/desk-checkout"]
    assert paths["/loans/desk-checkout"]["post"]["responses"]["201"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/Loan"}
    assert "409" in paths["/loans/desk-checkout"]["post"]["responses"]

    # 3. Item and lifecycle action endpoints
    assert "get" in paths["/loans/{loan_id}"]
    assert paths["/loans/{loan_id}"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/Loan"}

    assert "post" in paths["/loans/{loan_id}/approve"]
    assert paths["/loans/{loan_id}/approve"]["post"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/Loan"}
    assert "409" in paths["/loans/{loan_id}/approve"]["post"]["responses"]

    assert "post" in paths["/loans/{loan_id}/reject"]
    assert paths["/loans/{loan_id}/reject"]["post"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/Loan"}
    assert "409" in paths["/loans/{loan_id}/reject"]["post"]["responses"]

    assert "post" in paths["/loans/{loan_id}/checkout"]
    assert paths["/loans/{loan_id}/checkout"]["post"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/Loan"}
    assert "409" in paths["/loans/{loan_id}/checkout"]["post"]["responses"]

    assert "post" in paths["/loans/{loan_id}/return"]
    assert paths["/loans/{loan_id}/return"]["post"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/Loan"}
    assert "409" in paths["/loans/{loan_id}/return"]["post"]["responses"]

    # 4. Schemas validation
    schemas = contract["components"]["schemas"]
    assert schemas["Loan"]["required"] == [
        "loan_id",
        "organization_id",
        "copy_id",
        "borrower_user_id",
        "status",
        "requested_at",
    ]
    assert schemas["LoanPage"]["required"] == ["items"]
    assert schemas["LoanRequestWrite"]["required"] == ["copy_id"]
    assert schemas["DeskCheckoutWrite"]["required"] == ["copy_id", "borrower_user_id"]

    # 5. Idempotency contract validation
    headers = contract["components"]["headers"]
    assert "Idempotency-Key" in headers
    assert "Idempotency-Replayed" in headers

    for endpoint in [
        "/loans/desk-checkout",
        "/loans/{loan_id}/checkout",
        "/loans/{loan_id}/return",
    ]:
        op_params = paths[endpoint]["post"].get("parameters", [])
        assert any(p.get("name") == "Idempotency-Key" for p in op_params)
        responses = paths[endpoint]["post"]["responses"]
        for code in ["200", "201"]:
            if code in responses:
                assert "Idempotency-Replayed" in responses[code]["headers"]
