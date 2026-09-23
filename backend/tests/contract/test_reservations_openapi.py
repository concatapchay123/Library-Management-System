"""Consumer contract tests for reservation endpoints."""

from __future__ import annotations

import json
from pathlib import Path


def load_contract() -> dict[str, object]:
    path = Path(__file__).resolve().parents[3] / "contracts" / "openapi" / "v1.yaml"
    return json.loads(path.read_text(encoding="utf-8"))


def test_reservations_contract_exposes_lifecycle_endpoints() -> None:
    contract = load_contract()
    paths = contract["paths"]

    # 1. Base reservations endpoints
    assert {"get", "post"} <= set(paths["/reservations"])
    assert paths["/reservations"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/ReservationPage"}
    assert paths["/reservations"]["post"]["responses"]["201"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/Reservation"}
    assert "409" in paths["/reservations"]["post"]["responses"]

    # 2. Reservation detail endpoint
    assert "get" in paths["/reservations/{reservation_id}"]
    assert paths["/reservations/{reservation_id}"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"] == {"$ref": "#/components/schemas/Reservation"}

    # 3. Cancel and claim endpoints
    assert "post" in paths["/reservations/{reservation_id}/cancel"]
    assert paths["/reservations/{reservation_id}/cancel"]["post"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"] == {"$ref": "#/components/schemas/Reservation"}
    assert "409" in paths["/reservations/{reservation_id}/cancel"]["post"]["responses"]

    assert "post" in paths["/reservations/{reservation_id}/claim"]
    assert paths["/reservations/{reservation_id}/claim"]["post"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"] == {"$ref": "#/components/schemas/Reservation"}
    assert "409" in paths["/reservations/{reservation_id}/claim"]["post"]["responses"]

    # 4. Schemas validation
    schemas = contract["components"]["schemas"]
    assert schemas["Reservation"]["required"] == [
        "reservation_id",
        "organization_id",
        "book_id",
        "requester_user_id",
        "queue_position",
        "status",
        "created_at",
    ]
    assert schemas["ReservationPage"]["required"] == ["items"]
    assert schemas["ReservationCreateWrite"]["required"] == ["book_id"]
