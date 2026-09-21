"""Fail closed when a published OpenAPI version removes client behavior."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
import sys


HTTP_METHODS = frozenset({"delete", "get", "head", "options", "patch", "post", "put", "trace"})


def load_contract(path: Path) -> Mapping[str, object]:
    """Read the JSON-compatible YAML contract used by this repository."""
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("openapi") != "3.1.0":
        raise ValueError(f"{path} is not an OpenAPI 3.1 contract")
    return document


def find_breaking_changes(
    baseline: Mapping[str, object], candidate: Mapping[str, object]
) -> list[str]:
    """Return breaking removals and stricter request requirements in one API major."""
    changes: list[str] = []
    baseline_paths = _mapping(baseline.get("paths"))
    candidate_paths = _mapping(candidate.get("paths"))
    for path, baseline_item in baseline_paths.items():
        candidate_item = _mapping(candidate_paths.get(path))
        if not candidate_item:
            changes.extend(
                f"removed operation {method.upper()} {path}"
                for method in _operations(baseline_item)
            )
            continue
        for method, baseline_operation in _operations(baseline_item).items():
            candidate_operation = _operations(candidate_item).get(method)
            label = f"{method.upper()} {path}"
            if candidate_operation is None:
                changes.append(f"removed operation {label}")
                continue
            changes.extend(_required_parameter_changes(baseline_operation, candidate_operation, label))
            changes.extend(_response_changes(baseline_operation, candidate_operation, label))
    changes.extend(_schema_changes(baseline, candidate))
    return changes


def _operations(path_item: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    return {
        method: _mapping(operation)
        for method, operation in path_item.items()
        if method.lower() in HTTP_METHODS and isinstance(operation, dict)
    }


def _required_parameter_changes(
    baseline: Mapping[str, object], candidate: Mapping[str, object], label: str
) -> list[str]:
    baseline_parameters = _parameters(baseline)
    changes: list[str] = []
    for key, parameter in _parameters(candidate).items():
        if parameter.get("required") and not baseline_parameters.get(key, {}).get("required"):
            location, name = key
            changes.append(f"added required parameter {location} {name} to {label}")
    if _mapping(candidate.get("requestBody")).get("required") and not _mapping(
        baseline.get("requestBody")
    ).get("required"):
        changes.append(f"made request body required for {label}")
    return changes


def _parameters(operation: Mapping[str, object]) -> dict[tuple[str, str], Mapping[str, object]]:
    parameters: dict[tuple[str, str], Mapping[str, object]] = {}
    raw_parameters = operation.get("parameters", [])
    if not isinstance(raw_parameters, list):
        return parameters
    for parameter in raw_parameters:
        value = _mapping(parameter)
        location = value.get("in")
        name = value.get("name")
        if isinstance(location, str) and isinstance(name, str):
            parameters[(location, name)] = value
    return parameters


def _response_changes(
    baseline: Mapping[str, object], candidate: Mapping[str, object], label: str
) -> list[str]:
    baseline_responses = _mapping(baseline.get("responses"))
    candidate_responses = _mapping(candidate.get("responses"))
    return [
        f"removed response {status} from {label}"
        for status in baseline_responses
        if status not in candidate_responses
    ]


def _schema_changes(
    baseline: Mapping[str, object], candidate: Mapping[str, object]
) -> list[str]:
    baseline_schemas = _mapping(_mapping(baseline.get("components")).get("schemas"))
    candidate_schemas = _mapping(_mapping(candidate.get("components")).get("schemas"))
    changes: list[str] = []
    for name, baseline_schema in baseline_schemas.items():
        candidate_schema = _mapping(candidate_schemas.get(name))
        if not candidate_schema:
            changes.append(f"removed schema {name}")
            continue
        baseline_properties = _mapping(_mapping(baseline_schema).get("properties"))
        candidate_properties = _mapping(candidate_schema.get("properties"))
        changes.extend(
            f"removed property {property_name} from schema {name}"
            for property_name in baseline_properties
            if property_name not in candidate_properties
        )
        baseline_required = _strings(_mapping(baseline_schema).get("required"))
        candidate_required = _strings(candidate_schema.get("required"))
        changes.extend(
            f"added required property {property_name} to schema {name}"
            for property_name in candidate_required - baseline_required
        )
    return changes


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, dict) else {}


def _strings(value: object) -> set[str]:
    return {item for item in value if isinstance(item, str)} if isinstance(value, list) else set()


def main(arguments: list[str]) -> int:
    """Compare baseline then candidate, returning nonzero for breaking V1 changes."""
    if len(arguments) != 2:
        print("usage: check_compatibility.py BASELINE CANDIDATE", file=sys.stderr)
        return 2
    try:
        changes = find_breaking_changes(
            load_contract(Path(arguments[0])), load_contract(Path(arguments[1]))
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"OpenAPI compatibility check failed: {error}", file=sys.stderr)
        return 2
    if changes:
        print("Breaking OpenAPI compatibility changes detected:")
        print(*changes, sep="\n")
        return 1
    print("OpenAPI compatibility check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
