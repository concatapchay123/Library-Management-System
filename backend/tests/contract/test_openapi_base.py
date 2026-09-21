"""Machine-readable contract tests for the versioned API foundation."""

import json
from pathlib import Path


CONTRACT_PATH = (
    Path(__file__).resolve().parents[3] / "contracts" / "openapi" / "v1.yaml"
)


def load_contract() -> dict[str, object]:
    """Load the JSON-compatible YAML contract without a test-only parser dependency."""
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def test_v1_contract_defines_health_problem_details_and_request_correlation() -> None:
    """Removing any base API guarantee must fail the release contract gate."""
    contract = load_contract()

    assert contract["openapi"] == "3.1.0"
    assert contract["servers"] == [{"url": "/api/v1"}]

    paths = contract["paths"]
    assert "/health/live" in paths
    assert "/health/ready" in paths
    assert "/auth/login" in paths
    assert paths["/auth/login"]["post"]["responses"]["200"] == {
        "$ref": "#/components/responses/AccessToken"
    }
    assert paths["/auth/me"]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/AccessPrincipal"}

    components = contract["components"]
    schemas = components["schemas"]
    assert schemas["AccessPrincipal"] == {
        "type": "object",
        "required": ["user_id", "organization_id", "session_id"],
        "properties": {
            "user_id": {"type": "string", "format": "uuid"},
            "organization_id": {"type": "string", "format": "uuid"},
            "session_id": {"type": "string", "format": "uuid"},
        },
        "additionalProperties": False,
    }
    problem_details = schemas["ProblemDetails"]
    assert problem_details["type"] == "object"
    assert set(problem_details["required"]) >= {
        "type",
        "title",
        "status",
        "request_id",
    }
    assert problem_details["properties"]["request_id"] == {
        "type": "string",
        "pattern": "^[A-Za-z0-9._-]{1,128}$",
    }

    headers = components["headers"]
    assert headers["X-Request-ID"]["schema"] == {"type": "string"}

    readiness_failure = paths["/health/ready"]["get"]["responses"]["503"]
    assert readiness_failure["headers"]["X-Request-ID"] == {
        "$ref": "#/components/headers/X-Request-ID"
    }
    assert readiness_failure["content"]["application/problem+json"]["schema"] == {
        "$ref": "#/components/schemas/ProblemDetails"
    }
