"""Public HTTP adapter for credential validation."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
import hmac

from flask import Blueprint, Response, g, jsonify, request

from openlibrary.app.correlation import request_id
from openlibrary.app.errors import authentication_failure_response
from openlibrary.modules.core.application.access_tokens import (
    AccessTokenService,
    Principal,
    TokenVerificationError,
)
from openlibrary.modules.core.application.authorization import AuthorizationService
from openlibrary.modules.core.application.login import LoginService
from openlibrary.modules.core.application.refresh_sessions import (
    CsrfValidationError,
    RefreshResult,
    RefreshSessionService,
)
from openlibrary.modules.core.infrastructure.tenancy import TenantRequestContext


def create_auth_blueprint(
    login_service: LoginService,
    access_tokens: AccessTokenService,
    refresh_sessions: RefreshSessionService,
    authorization: AuthorizationService | None = None,
    tenant_request_context: TenantRequestContext | None = None,
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
        return _refresh_response(refresh_sessions.start(result), access_tokens)

    @auth.post("/refresh")
    def refresh() -> Response:
        try:
            result = refresh_sessions.rotate(
                request.cookies.get("refresh_token", ""), _csrf_token_from_request()
            )
        except CsrfValidationError:
            return _csrf_failure_response()
        if result is None:
            return authentication_failure_response()
        return _refresh_response(result, access_tokens)

    @auth.post("/logout")
    @_require_principal(access_tokens, tenant_request_context)
    def logout() -> Response:
        try:
            logged_out = refresh_sessions.logout(
                request.cookies.get("refresh_token", ""),
                _csrf_token_from_request(),
                _principal_from_request(),
            )
        except CsrfValidationError:
            return _csrf_failure_response()
        if not logged_out:
            return authentication_failure_response()
        response = Response(status=204)
        response.delete_cookie("refresh_token", path="/api/v1/auth", secure=True)
        response.delete_cookie("csrf_token", path="/api/v1/auth", secure=True)
        return response

    @auth.get("/me")
    @_require_principal(access_tokens, tenant_request_context)
    def me() -> Response:
        principal = _principal_from_request()
        return jsonify(
            {
                "user_id": str(principal.user_id),
                "organization_id": str(principal.organization_id),
                "session_id": str(principal.session_id),
                "permissions": list(authorization.permissions(principal))
                if authorization is not None
                else [],
            }
        )

    return auth


def _refresh_response(
    result: RefreshResult, access_tokens: AccessTokenService
) -> Response:
    response = jsonify(
        {
            "access_token": result.access_token,
            "token_type": "Bearer",
            "expires_in": access_tokens.expires_in,
        }
    )
    response.set_cookie(
        "refresh_token",
        result.refresh_token,
        secure=True,
        httponly=True,
        samesite="Strict",
        path="/api/v1/auth",
    )
    response.set_cookie(
        "csrf_token",
        result.csrf_token,
        secure=True,
        httponly=False,
        samesite="Strict",
        path="/api/v1/auth",
    )
    return response


def _csrf_token_from_request() -> str:
    header = request.headers.get("X-CSRF-Token", "")
    cookie = request.cookies.get("csrf_token", "")
    if not header or not cookie or not hmac.compare_digest(header, cookie):
        raise CsrfValidationError("CSRF double-submit validation failed")
    return header


def _csrf_failure_response() -> Response:
    response = jsonify(
        {
            "type": "about:blank",
            "title": "Forbidden",
            "status": 403,
            "detail": "CSRF validation failed",
            "instance": request.path,
            "request_id": request_id(),
        }
    )
    response.status_code = 403
    response.mimetype = "application/problem+json"
    return response


def _string_value(payload: dict[object, object], key: str) -> str:
    """Keep malformed request values inside the uniform authentication path."""
    value = payload.get(key, "")
    return value if isinstance(value, str) else ""


def _require_principal(
    access_tokens: AccessTokenService,
    tenant_request_context: TenantRequestContext | None = None,
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
            if tenant_request_context is not None:
                with tenant_request_context.request(g.principal.organization_id):
                    return view()
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
