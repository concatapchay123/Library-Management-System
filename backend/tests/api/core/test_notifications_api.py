"""API and route tests for in-app notification endpoints."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest
from flask import Flask
from werkzeug.test import Client

from openlibrary.app.config import AppConfig
from openlibrary.app.factory import create_app
from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.authorization import AuthorizationDenied
from openlibrary.modules.core.application.notifications import (
    Notification,
    NotificationService,
    NotificationStore,
)
from openlibrary.modules.core.domain.notifications import (
    NotificationStatus,
)


ORGANIZATION_A = uuid4()
ORGANIZATION_B = uuid4()
PATRON_A = Principal(uuid4(), ORGANIZATION_A, uuid4())
PATRON_A2 = Principal(uuid4(), ORGANIZATION_A, uuid4())
PATRON_B = Principal(uuid4(), ORGANIZATION_B, uuid4())


@dataclass
class _InMemoryNotificationStore(NotificationStore):
    notifications: dict[tuple[UUID, UUID, UUID], Notification] = field(
        default_factory=dict
    )

    def create_notification(
        self,
        notification: Notification,
        *,
        outbox_event_id: UUID | None = None,
    ) -> Notification:
        key = (
            notification.organization_id,
            notification.user_id,
            notification.notification_id,
        )
        self.notifications[key] = notification
        return notification

    def create_notification_in_connection(
        self,
        connection: object,
        notification: Notification,
        *,
        outbox_event_id: UUID | None = None,
    ) -> Notification:
        return self.create_notification(notification, outbox_event_id=outbox_event_id)

    def list_notifications(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        status: str | None = None,
        limit: int = 50,
    ) -> list[Notification]:
        results: list[Notification] = []
        for (org_id, u_id, _), notif in self.notifications.items():
            if org_id == organization_id and u_id == user_id:
                if status is None or notif.status == status:
                    results.append(notif)
        results.sort(key=lambda n: n.created_at, reverse=True)
        return results[:limit]

    def get_notification(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        notification_id: UUID,
    ) -> Notification | None:
        return self.notifications.get((organization_id, user_id, notification_id))

    def mark_as_read(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        notification_id: UUID,
        read_at: datetime,
    ) -> Notification | None:
        key = (organization_id, user_id, notification_id)
        existing = self.notifications.get(key)
        if existing is None:
            return None
        updated = Notification(
            notification_id=existing.notification_id,
            organization_id=existing.organization_id,
            user_id=existing.user_id,
            type=existing.type,
            payload=existing.payload,
            channel=existing.channel,
            status=NotificationStatus.READ,
            read_at=existing.read_at or read_at,
            created_at=existing.created_at,
            outbox_event_id=existing.outbox_event_id,
        )
        self.notifications[key] = updated
        return updated


class _StaticAuthorizer:
    def __init__(self, allowed: set[tuple[UUID, str]] | None = None) -> None:
        self._allowed = allowed if allowed is not None else set()

    def allow(self, principal: Principal, permission: str) -> None:
        self._allowed.add((principal.user_id, permission))

    def require(self, principal: Principal, permission: str) -> None:
        if (principal.user_id, permission) not in self._allowed:
            raise AuthorizationDenied(f"Permission {permission} denied")


class _StubAccessTokenService:
    def verify(self, token: str) -> Principal:
        if token == "patron-a-token":
            return PATRON_A
        if token == "patron-a2-token":
            return PATRON_A2
        if token == "patron-b-token":
            return PATRON_B
        from openlibrary.modules.core.application.access_tokens import (
            TokenVerificationError,
        )

        raise TokenVerificationError(f"Unknown token: {token}")


@pytest.fixture
def notif_env() -> dict[str, Any]:
    store = _InMemoryNotificationStore()
    authorizer = _StaticAuthorizer()
    access_tokens = _StubAccessTokenService()

    authorizer.allow(PATRON_A, "notification.read")
    authorizer.allow(PATRON_B, "notification.read")

    service = NotificationService(store=store, authorizer=authorizer)
    app: Flask = create_app(
        AppConfig(
            readiness_probe=lambda: True,
            access_tokens=access_tokens,  # type: ignore[arg-type]
            notification_service=service,
        )
    )
    client = app.test_client()
    return {
        "store": store,
        "authorizer": authorizer,
        "service": service,
        "client": client,
    }


def test_list_notifications_unauthenticated(notif_env: dict[str, Any]) -> None:
    client: Client = notif_env["client"]
    resp = client.get("/api/v1/notifications")
    assert resp.status_code == 401


def test_list_notifications_unauthorized(notif_env: dict[str, Any]) -> None:
    client: Client = notif_env["client"]
    resp = client.get(
        "/api/v1/notifications",
        headers={"Authorization": "Bearer patron-a2-token"},
    )
    assert resp.status_code == 403
    data = resp.get_json()
    assert data["title"] == "Forbidden"


def test_list_notifications_success_and_filters(notif_env: dict[str, Any]) -> None:
    client: Client = notif_env["client"]
    store: _InMemoryNotificationStore = notif_env["store"]

    notif_1 = Notification(
        notification_id=uuid4(),
        organization_id=ORGANIZATION_A,
        user_id=PATRON_A.user_id,
        type="circulation.loan_approved",
        payload={"loan_id": str(uuid4())},
        status=NotificationStatus.UNREAD,
    )
    notif_2 = Notification(
        notification_id=uuid4(),
        organization_id=ORGANIZATION_A,
        user_id=PATRON_A.user_id,
        type="circulation.loan_returned",
        payload={"loan_id": str(uuid4())},
        status=NotificationStatus.READ,
        read_at=datetime.now(timezone.utc),
    )
    notif_other = Notification(
        notification_id=uuid4(),
        organization_id=ORGANIZATION_B,
        user_id=PATRON_B.user_id,
        type="circulation.loan_overdue",
        payload={"loan_id": str(uuid4())},
        status=NotificationStatus.UNREAD,
    )
    store.create_notification(notif_1)
    store.create_notification(notif_2)
    store.create_notification(notif_other)

    # 1. List all for PATRON_A
    resp = client.get(
        "/api/v1/notifications",
        headers={"Authorization": "Bearer patron-a-token"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    returned_ids = {item["notification_id"] for item in data["items"]}
    assert str(notif_1.notification_id) in returned_ids
    assert str(notif_2.notification_id) in returned_ids
    assert str(notif_other.notification_id) not in returned_ids

    # 2. Filter status=unread
    resp_unread = client.get(
        "/api/v1/notifications?status=unread",
        headers={"Authorization": "Bearer patron-a-token"},
    )
    assert resp_unread.status_code == 200
    unread_data = resp_unread.get_json()
    assert unread_data["total"] == 1
    assert unread_data["items"][0]["notification_id"] == str(notif_1.notification_id)


def test_mark_notification_read_workflow(notif_env: dict[str, Any]) -> None:
    client: Client = notif_env["client"]
    store: _InMemoryNotificationStore = notif_env["store"]

    notif = Notification(
        notification_id=uuid4(),
        organization_id=ORGANIZATION_A,
        user_id=PATRON_A.user_id,
        type="circulation.loan_overdue",
        payload={"loan_id": str(uuid4())},
        status=NotificationStatus.UNREAD,
    )
    store.create_notification(notif)

    # 1. Mark as read
    resp = client.post(
        f"/api/v1/notifications/{notif.notification_id}/read",
        headers={"Authorization": "Bearer patron-a-token"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "read"
    assert data["read_at"] is not None

    # 2. Idempotent repeat
    resp_repeat = client.post(
        f"/api/v1/notifications/{notif.notification_id}/read",
        headers={"Authorization": "Bearer patron-a-token"},
    )
    assert resp_repeat.status_code == 200
    data_repeat = resp_repeat.get_json()
    assert data_repeat["status"] == "read"
    assert data_repeat["read_at"] == data["read_at"]

    # 3. Unknown notification -> 404
    resp_unknown = client.post(
        f"/api/v1/notifications/{uuid4()}/read",
        headers={"Authorization": "Bearer patron-a-token"},
    )
    assert resp_unknown.status_code == 404

    # 5. Invalid UUID format -> 400
    resp_invalid = client.post(
        "/api/v1/notifications/not-a-uuid/read",
        headers={"Authorization": "Bearer patron-a-token"},
    )
    assert resp_invalid.status_code == 400

    # 6. Another tenant user cannot mark it read -> 404
    resp_other = client.post(
        f"/api/v1/notifications/{notif.notification_id}/read",
        headers={"Authorization": "Bearer patron-b-token"},
    )
    assert resp_other.status_code == 404
