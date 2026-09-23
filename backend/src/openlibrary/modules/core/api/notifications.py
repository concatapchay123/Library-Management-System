"""Protected HTTP adapters for the in-app notification lifecycle."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from flask import Blueprint, Response, jsonify, request

from openlibrary.app.correlation import request_id
from openlibrary.modules.core.api.auth import (
    _principal_from_request,
    _require_principal,
)
from openlibrary.modules.core.application.access_tokens import AccessTokenService
from openlibrary.modules.core.application.authorization import AuthorizationDenied
from openlibrary.modules.core.application.notifications import (
    Notification,
    NotificationService,
)
from openlibrary.modules.core.domain.notifications import (
    NotificationNotFoundError,
)
from openlibrary.modules.core.infrastructure.tenancy import TenantRequestContext


def create_notifications_blueprint(
    service: NotificationService,
    access_tokens: AccessTokenService,
    tenant_request_context: TenantRequestContext | None = None,
    url_prefix: str = "/api/v1/notifications",
    name: str = "notifications",
) -> Blueprint:
    """Expose notification endpoints under tenant and user authorization."""
    notifications = Blueprint(name, __name__, url_prefix=url_prefix)

    @notifications.get("")
    @_require_principal(access_tokens, tenant_request_context)
    def list_notifications() -> Response:
        status = request.args.get("status")
        raw_limit = request.args.get("limit", "50")
        try:
            limit = int(raw_limit)
        except ValueError:
            return _bad_request("Field 'limit' must be an integer.")

        try:
            items = service.list_notifications(
                actor=_principal_from_request(),
                status=status,
                limit=limit,
            )
            return jsonify(
                {
                    "items": [_notification_response(item) for item in items],
                    "total": len(items),
                }
            )
        except ValueError as err:
            return _bad_request(str(err))
        except AuthorizationDenied as err:
            return _problem_response(403, "Forbidden", str(err))

    @notifications.post("/<notification_id>/read")
    @_require_principal(access_tokens, tenant_request_context)
    def mark_notification_read(notification_id: str) -> Response:
        try:
            notif_uuid = UUID(notification_id)
        except ValueError:
            return _bad_request("Invalid 'notification_id' UUID format.")

        try:
            updated = service.mark_notification_read(
                actor=_principal_from_request(),
                notification_id=notif_uuid,
            )
            return jsonify(_notification_response(updated))
        except NotificationNotFoundError as err:
            return _problem_response(
                err.status_code, err.title, str(err), type_uri=err.problem_type
            )
        except AuthorizationDenied as err:
            return _problem_response(403, "Forbidden", str(err))

    return notifications


def _notification_response(notification: Notification) -> dict[str, Any]:
    return {
        "notification_id": str(notification.notification_id),
        "organization_id": str(notification.organization_id),
        "user_id": str(notification.user_id),
        "channel": notification.channel,
        "type": notification.type,
        "payload": dict(notification.payload),
        "status": notification.status,
        "read_at": notification.read_at.isoformat() if notification.read_at else None,
        "created_at": notification.created_at.isoformat(),
    }


def _problem_response(
    status: int, title: str, detail: str, *, type_uri: str | None = None
) -> Response:
    if type_uri is None:
        type_suffix = "bad-request"
        if status == 404:
            type_suffix = "not-found"
        elif status == 409:
            type_suffix = "conflict"
        elif status == 403:
            type_suffix = "forbidden"
        type_uri = f"https://openlibraryos.example/problems/{type_suffix}"
    response = jsonify(
        {
            "type": type_uri,
            "title": title,
            "status": status,
            "detail": detail,
            "instance": request.path,
            "request_id": request_id(),
        }
    )
    response.status_code = status
    response.mimetype = "application/problem+json"
    return response


def _bad_request(detail: str = "Invalid request payload.") -> Response:
    return _problem_response(400, "Bad Request", detail)
