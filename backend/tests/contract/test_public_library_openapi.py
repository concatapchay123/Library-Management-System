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
