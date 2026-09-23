"""Consumer contract for locations and book copies."""

import json
from pathlib import Path


def load_contract() -> dict[str, object]:
    path = Path(__file__).resolve().parents[3] / "contracts" / "openapi" / "v1.yaml"
    return json.loads(path.read_text(encoding="utf-8"))


def test_inventory_contract_exposes_locations_and_book_copies() -> None:
    contract = load_contract()
    paths = contract["paths"]

    # Locations
    assert {"get", "post"} <= set(paths["/locations"])
    assert {"get", "patch"} <= set(paths["/locations/{location_id}"])
    assert paths["/locations"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/LocationPage"}
    assert paths["/locations"]["post"]["responses"]["201"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/Location"}
    assert "409" in paths["/locations"]["post"]["responses"]

    # Book copies
    assert {"get", "post"} <= set(paths["/books/{book_id}/copies"])
    assert {"get", "patch"} <= set(paths["/books/{book_id}/copies/{copy_id}"])
    assert paths["/books/{book_id}/copies"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/BookCopyPage"}
    assert paths["/books/{book_id}/copies"]["post"]["responses"]["201"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/BookCopy"}
    assert "409" in paths["/books/{book_id}/copies"]["post"]["responses"]

    # Direct copies
    assert {"get", "patch"} <= set(paths["/copies/{copy_id}"])
    assert "post" in paths["/copies/{copy_id}/status"]
    assert paths["/copies/{copy_id}/status"]["post"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/BookCopy"}
    assert "409" in paths["/copies/{copy_id}/status"]["post"]["responses"]

    assert "get" in paths["/copies/{copy_id}/history"]
    assert paths["/copies/{copy_id}/history"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/CopyStatusHistoryPage"}

    # Schemas
    schemas = contract["components"]["schemas"]
    assert schemas["Location"]["required"] == ["location_id", "name", "code", "status"]
    assert schemas["LocationWrite"]["required"] == ["name", "code"]
    assert schemas["BookCopy"]["required"] == [
        "copy_id",
        "book_id",
        "barcode",
        "location_id",
        "status",
        "condition_code",
    ]
    assert schemas["BookCopyWrite"]["required"] == ["location_id", "barcode"]
    assert schemas["CopyStatusTransition"]["required"] == ["to_status", "reason"]
    assert schemas["CopyStatusHistoryRecord"]["required"] == [
        "history_id",
        "copy_id",
        "from_status",
        "to_status",
        "reason",
        "actor_id",
        "created_at",
    ]
    assert schemas["CopyStatusHistoryPage"]["required"] == ["items"]
