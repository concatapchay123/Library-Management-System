"""Public HTTP adapter for credential validation."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps

from flask import Blueprint, Response, g, jsonify, request

from openlibrary.app.correlation import request_id
from openlibrary.app.errors import authentication_failure_response
from openlibrary.modules.core.application.access_tokens import (
    AccessTokenService,
    Principal,
    TokenVerificationError,
)
from openlibrary.modules.core.application.login import LoginService


def create_auth_blueprint(
    login_service: LoginService, access_tokens: AccessTokenService
) -> Blueprint:
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
        return jsonify(
            {
                "access_token": access_tokens.issue(result),
                "token_type": "Bearer",
                "expires_in": access_tokens.expires_in,
            }
        )

    @auth.get("/me")
    @_require_principal(access_tokens)
    def me() -> Response:
        principal = _principal_from_request()
        return jsonify(
            {
                "user_id": str(principal.user_id),
                "organization_id": str(principal.organization_id),
                "session_id": str(principal.session_id),
            }
        )

    return auth


def _string_value(payload: dict[object, object], key: str) -> str:
    """Keep malformed request values inside the uniform authentication path."""
    value = payload.get(key, "")
    return value if isinstance(value, str) else ""


def _require_principal(
    access_tokens: AccessTokenService,
) -> Callable[[Callable[[], Response]], Callable[[], Response]]:
    """Install the bearer boundary before a protected route receives control."""

    def decorator(view: Callable[[], Response]) -> Callable[[], Response]:
        @wraps(view)
        def protected() -> Response:
            token = _bearer_token(request.headers.get("Authorization"))
            if token is None:
                return authentication_failure_response()
            try:
                g.principal = access_tokens.verify(token)
            except TokenVerificationError:
                return authentication_failure_response()
            return view()

        return protected

    return decorator


def _bearer_token(authorization: str | None) -> str | None:
    if authorization is None:
        return None
    scheme, separator, token = authorization.partition(" ")
    if scheme != "Bearer" or not separator or not token or " " in token:
        return None
    return token


def _principal_from_request() -> Principal:
    principal = g.get("principal")
    if not isinstance(principal, Principal):
        raise RuntimeError("Protected route executed without a verified principal")
    return principal
