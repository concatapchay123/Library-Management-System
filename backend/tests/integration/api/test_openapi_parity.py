"""Route parity integration gate: verifies all registered Flask routes match OpenAPI contract (M-01)."""

from __future__ import annotations

from pathlib import Path
import re
from unittest.mock import MagicMock
import yaml

from openlibrary.app.config import AppConfig
from openlibrary.app.factory import create_app


def _create_full_app():
    """Create an application with all functional blueprints registered using mocks."""
    mock = MagicMock()
    config = AppConfig(
        readiness_probe=lambda: True,
        login_service=mock,
        access_tokens=mock,
        refresh_sessions=mock,
        authorization=mock,
        tenant_request_context=mock,
        organization_settings=mock,
        book_catalog=mock,
        inventory=mock,
        copy_status=mock,
        loan_service=mock,
        reservation_service=mock,
        notification_service=mock,
        education_service=mock,
        public_library_service=mock,
        public_library_finance_service=mock,
        worker_health_service=mock,
    )
    return create_app(config)


def test_flask_routes_match_openapi_contract() -> None:
    """Every registered API endpoint under /api/v1 must be documented in OpenAPI specification."""
    app = _create_full_app()

    openapi_path = (
        Path(__file__).resolve().parents[4] / "contracts" / "openapi" / "v1.yaml"
    )
    assert openapi_path.is_file(), f"OpenAPI contract missing at {openapi_path}"

    spec = yaml.safe_load(openapi_path.read_text(encoding="utf-8"))
    openapi_paths = set(spec.get("paths", {}).keys())

    # Documented backward-compatibility aliases or nested convenience aliases
    known_aliases = {
        "/public-library/plans",
        "/public-library/plans/{plan_id}",
        "/public-library/plans/seed",
        "/books/{book_id}/copies/{copy_id}/status",
        "/books/{book_id}/copies/{copy_id}/history",
    }

    unmapped_routes = set()
    flask_paths = set()

    for rule in app.url_map.iter_rules():
        r = rule.rule
        if rule.endpoint == "static" or r.startswith("/static"):
            continue
        if r.startswith("/api/v1"):
            r = r[len("/api/v1") :]

        # Normalize Flask route parameter format <[type:]param> to OpenAPI {param}
        normalized = re.sub(r"<(?:[^:]+:)?([^>]+)>", r"{\1}", r)
        flask_paths.add(normalized)

        if normalized not in openapi_paths and normalized not in known_aliases:
            unmapped_routes.add(normalized)

    assert not unmapped_routes, (
        f"Detected undocumented API routes in Flask app: {sorted(unmapped_routes)}. "
        "All registered endpoints must be documented in contracts/openapi/v1.yaml"
    )

    # Reverse direction: all OpenAPI paths must exist in Flask
    missing_in_flask = openapi_paths - flask_paths
    assert not missing_in_flask, (
        f"OpenAPI paths missing from Flask implementation: {sorted(missing_in_flask)}"
    )
