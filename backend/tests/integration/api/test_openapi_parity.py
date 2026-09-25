"""Route parity integration gate: verifies all registered Flask routes match OpenAPI contract (M-02)."""

from __future__ import annotations

from pathlib import Path
import re
import yaml

from openlibrary.app.config import AppConfig
from openlibrary.app.factory import create_app


def test_flask_routes_match_openapi_contract() -> None:
    """Every registered API endpoint under /api/v1 must be documented in OpenAPI specification."""
    app = create_app(AppConfig(readiness_probe=lambda: True))

    openapi_path = Path(__file__).resolve().parents[4] / "contracts" / "openapi" / "v1.yaml"
    assert openapi_path.is_file(), f"OpenAPI contract missing at {openapi_path}"

    spec = yaml.safe_load(openapi_path.read_text(encoding="utf-8"))
    openapi_paths = set(spec.get("paths", {}).keys())

    unmapped_routes = set()
    for rule in app.url_map.iter_rules():
        r = rule.rule
        if rule.endpoint == "static" or r.startswith("/static"):
            continue
        if r.startswith("/api/v1"):
            r = r[len("/api/v1") :]

        # Normalize Flask route parameter format <[type:]param> to OpenAPI {param}
        normalized = re.sub(r"<(?:[^:]+:)?([^>]+)>", r"{\1}", r)
        if normalized not in openapi_paths:
            unmapped_routes.add(normalized)

    assert not unmapped_routes, (
        f"Detected undocumented API routes in Flask app: {sorted(unmapped_routes)}. "
        "All registered endpoints must be documented in contracts/openapi/v1.yaml"
    )
