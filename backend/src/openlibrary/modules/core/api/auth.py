"""Public HTTP adapter for credential validation."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request

from openlibrary.app.correlation import request_id
from openlibrary.app.errors import authentication_failure_response
from openlibrary.modules.core.application.login import LoginService


def create_auth_blueprint(login_service: LoginService) -> Blueprint:
    """Create the public login route around an injected application service."""
    auth = Blueprint("auth", __name__, url_prefix="/api/v1/auth")

    @auth.post("/login")
    def login() -> Response:
        payload = request.get_json(silent=True)
        body = payload if isinstance(payload, dict) else {}
        result = login_service.login(
            organization_slug=_string_value(body, "organization_slug"),
            email=_string_value(body, "email"),
            password=_string_value(body, "password"),
            correlation_id=request_id(),
        )
        if result is None:
            return authentication_failure_response()
        return jsonify({"status": "authenticated"})

    return auth


def _string_value(payload: dict[object, object], key: str) -> str:
    """Keep malformed request values inside the uniform authentication path."""
    value = payload.get(key, "")
    return value if isinstance(value, str) else ""
