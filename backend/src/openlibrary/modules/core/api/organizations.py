"""Protected HTTP adapter for the caller's organization settings."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request

from openlibrary.app.correlation import request_id
from openlibrary.modules.core.api.auth import (
    _principal_from_request,
    _require_principal,
)
from openlibrary.modules.core.application.access_tokens import AccessTokenService
from openlibrary.modules.core.application.organization_settings import (
    OrganizationSettings,
    OrganizationSettingsService,
)
from openlibrary.modules.core.infrastructure.tenancy import TenantRequestContext


def create_organizations_blueprint(
    service: OrganizationSettingsService,
    access_tokens: AccessTokenService,
    tenant_request_context: TenantRequestContext | None,
) -> Blueprint:
    """Expose no tenant selector: every operation derives it from the JWT principal."""
    organizations = Blueprint(
        "organizations", __name__, url_prefix="/api/v1/organizations"
    )

    @organizations.get("/settings")
    @_require_principal(access_tokens, tenant_request_context)
    def get_settings() -> Response:
        return jsonify(_response(service.get(actor=_principal_from_request())))

    @organizations.patch("/settings")
    @_require_principal(access_tokens, tenant_request_context)
    def update_settings() -> Response:
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return _invalid_settings_response()
        timezone = payload.get("timezone")
        settings = payload.get("settings")
        if not isinstance(timezone, str) or not isinstance(settings, dict):
            return _invalid_settings_response()
        try:
            updated = service.update(
                actor=_principal_from_request(), timezone=timezone, settings=settings
            )
        except ValueError:
            return _invalid_settings_response()
        return jsonify(_response(updated))

    return organizations


def _response(settings: OrganizationSettings) -> dict[str, object]:
    return {"timezone": settings.timezone, "settings": settings.settings}


def _invalid_settings_response() -> Response:
    response = jsonify(
        {
            "type": "https://openlibraryos.example/problems/bad-request",
            "title": "Bad Request",
            "status": 400,
            "detail": "Invalid organization settings.",
            "instance": request.path,
            "request_id": request_id(),
        }
    )
    response.status_code = 400
    response.mimetype = "application/problem+json"
    return response
