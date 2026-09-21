"""Compatibility checks for a published OpenAPI major version."""

import json
from pathlib import Path
import subprocess
import sys


CHECKER_PATH = (
    Path(__file__).resolve().parents[3]
    / "contracts"
    / "openapi"
    / "check_compatibility.py"
)


def write_contract(
    path: Path, paths: dict[str, object], schemas: dict[str, object] | None = None
) -> None:
    """Write the JSON-compatible YAML subset used by the local gate."""
    path.write_text(
        json.dumps(
            {
                "openapi": "3.1.0",
                "paths": paths,
                "components": {"schemas": schemas or {}},
            }
        ),
        encoding="utf-8",
    )


def test_compatibility_check_rejects_removed_v1_operation(tmp_path: Path) -> None:
    """Removing a published operation must require a new API major version."""
    baseline = tmp_path / "baseline.yaml"
    candidate = tmp_path / "candidate.yaml"
    write_contract(baseline, {"/health/live": {"get": {"responses": {"200": {}}}}})
    write_contract(candidate, {})

    result = subprocess.run(
        [sys.executable, str(CHECKER_PATH), str(baseline), str(candidate)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "removed operation GET /health/live" in result.stdout


def test_compatibility_check_rejects_a_new_required_parameter(tmp_path: Path) -> None:
    """Making an existing request stricter must not silently break V1 clients."""
    baseline = tmp_path / "baseline.yaml"
    candidate = tmp_path / "candidate.yaml"
    write_contract(
        baseline,
        {
            "/health/live": {
                "get": {
                    "parameters": [],
                    "responses": {"200": {}},
                }
            }
        },
    )
    write_contract(
        candidate,
        {
            "/health/live": {
                "get": {
                    "parameters": [{"in": "query", "name": "locale", "required": True}],
                    "responses": {"200": {}},
                }
            }
        },
    )

    result = subprocess.run(
        [sys.executable, str(CHECKER_PATH), str(baseline), str(candidate)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "added required parameter query locale to GET /health/live" in result.stdout


def test_compatibility_check_rejects_a_new_required_schema_property(
    tmp_path: Path,
) -> None:
    """A newly required response field must not silently break V1 clients."""
    baseline = tmp_path / "baseline.yaml"
    candidate = tmp_path / "candidate.yaml"
    write_contract(
        baseline,
        {},
        {
            "AccessToken": {
                "type": "object",
                "properties": {"access_token": {}},
                "required": [],
            }
        },
    )
    write_contract(
        candidate,
        {},
        {
            "AccessToken": {
                "type": "object",
                "properties": {"access_token": {}, "expires_in": {}},
                "required": ["expires_in"],
            }
        },
    )

    result = subprocess.run(
        [sys.executable, str(CHECKER_PATH), str(baseline), str(candidate)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "added required property expires_in to schema AccessToken" in result.stdout
