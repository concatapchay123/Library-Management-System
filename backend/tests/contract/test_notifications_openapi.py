"""Consumer contract tests for notification endpoints."""

from __future__ import annotations

import json
from pathlib import Path


def load_contract() -> dict[str, object]:
    path = Path(__file__).resolve().parents[3] / "contracts" / "openapi" / "v1.yaml"
    return json.loads(path.read_text(encoding="utf-8"))


def test_notifications_contract_exposes_lifecycle_endpoints() -> None:
    contract = load_contract()
    paths = contract["paths"]

    # 1. Base notifications list endpoint
    assert "get" in paths["/notifications"]
    get_notifs = paths["/notifications"]["get"]
    assert get_notifs["operationId"] == "listNotifications"
    assert get_notifs["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/NotificationListResponse"
    }
    assert "401" in get_notifs["responses"]
    assert "403" in get_notifs["responses"]

    # 2. Mark notification read endpoint
    assert "/notifications/{notification_id}/read" in paths
    mark_read = paths["/notifications/{notification_id}/read"]["post"]
    assert mark_read["operationId"] == "markNotificationRead"
    assert mark_read["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/Notification"
    }
    assert "400" in mark_read["responses"]
    assert "401" in mark_read["responses"]
    assert "403" in mark_read["responses"]
    assert "404" in mark_read["responses"]

    # 3. Schemas validation
    schemas = contract["components"]["schemas"]
    assert schemas["Notification"]["required"] == [
        "notification_id",
        "organization_id",
        "user_id",
        "channel",
        "type",
        "payload",
        "status",
        "created_at",
    ]
    assert schemas["NotificationListResponse"]["required"] == ["items", "total"]
