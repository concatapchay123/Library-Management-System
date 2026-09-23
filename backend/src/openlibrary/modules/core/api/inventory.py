"""Protected HTTP adapters for locations and physical book copies."""

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
from openlibrary.modules.core.application.inventory import (
    BookCopy,
    DuplicateBarcodeError,
    DuplicateLocationCodeError,
    InventoryService,
    Location,
)
from openlibrary.modules.core.infrastructure.tenancy import TenantRequestContext


def create_locations_blueprint(
    service: InventoryService,
    access_tokens: AccessTokenService,
    tenant_request_context: TenantRequestContext | None,
) -> Blueprint:
    """Expose location operations without accepting any tenant selector."""
    locations = Blueprint("locations", __name__, url_prefix="/api/v1/locations")

    @locations.get("")
    @_require_principal(access_tokens, tenant_request_context)
    def list_locations() -> Response:
        items = service.list_locations(actor=_principal_from_request())
        return jsonify({"items": [_location_response(loc) for loc in items]})

    @locations.post("")
    @_require_principal(access_tokens, tenant_request_context)
    def create_location() -> Response:
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return _bad_request("Invalid JSON payload.")
        name = payload.get("name")
        code = payload.get("code")
        parent_location_id_raw = payload.get("parent_location_id")
        if not isinstance(name, str) or not isinstance(code, str):
            return _bad_request("Name and code must be non-empty strings.")
        parent_uuid: UUID | None = None
        if parent_location_id_raw is not None:
            try:
                parent_uuid = UUID(str(parent_location_id_raw))
            except ValueError:
                return _bad_request("Invalid parent_location_id UUID format.")
        try:
            loc = service.create_location(
                actor=_principal_from_request(),
                name=name,
                code=code,
                parent_location_id=parent_uuid,
            )
        except DuplicateLocationCodeError:
            return _conflict("Location code already exists in organization.")
        except KeyError:
            return _not_found("Parent location not found.")
        except ValueError as err:
            return _bad_request(str(err))
        response = jsonify(_location_response(loc))
        response.status_code = 201
        return response

    @locations.get("/<location_id>")
    @_require_principal(access_tokens, tenant_request_context)
    def get_location(location_id: str) -> Response:
        try:
            loc_uuid = UUID(location_id)
        except ValueError:
            return _bad_request("Invalid location_id UUID format.")
        try:
            loc = service.get_location(
                actor=_principal_from_request(), location_id=loc_uuid
            )
        except KeyError:
            return _not_found("Location not found.")
        return jsonify(_location_response(loc))

    @locations.patch("/<location_id>")
    @_require_principal(access_tokens, tenant_request_context)
    def update_location(location_id: str) -> Response:
        try:
            loc_uuid = UUID(location_id)
        except ValueError:
            return _bad_request("Invalid location_id UUID format.")
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return _bad_request("Invalid JSON payload.")
        name = payload.get("name")
        code = payload.get("code")
        status = payload.get("status", "active")
        parent_raw = payload.get("parent_location_id")
        if (
            not isinstance(name, str)
            or not isinstance(code, str)
            or not isinstance(status, str)
        ):
            return _bad_request("name, code and status must be strings.")
        parent_uuid: UUID | None = None
        if parent_raw is not None:
            try:
                parent_uuid = UUID(str(parent_raw))
            except ValueError:
                return _bad_request("Invalid parent_location_id UUID format.")
        try:
            loc = service.update_location(
                actor=_principal_from_request(),
                location_id=loc_uuid,
                name=name,
                code=code,
                parent_location_id=parent_uuid,
                status=status,
            )
        except DuplicateLocationCodeError:
            return _conflict("Location code already exists in organization.")
        except KeyError:
            return _not_found("Location or parent not found.")
        except ValueError as err:
            return _bad_request(str(err))
        return jsonify(_location_response(loc))

    return locations


def create_book_copies_blueprint(
    service: InventoryService,
    access_tokens: AccessTokenService,
    tenant_request_context: TenantRequestContext | None,
) -> Blueprint:
    """Expose copy operations nested under book resources."""
    book_copies = Blueprint(
        "book_copies", __name__, url_prefix="/api/v1/books/<book_id>/copies"
    )

    @book_copies.get("")
    @_require_principal(access_tokens, tenant_request_context)
    def list_copies(book_id: str) -> Response:
        try:
            book_uuid = UUID(book_id)
        except ValueError:
            return _bad_request("Invalid book_id UUID format.")
        try:
            copies = service.list_book_copies(
                actor=_principal_from_request(), book_id=book_uuid
            )
        except KeyError:
            return _not_found("Book not found.")
        return jsonify({"items": [_copy_response(copy) for copy in copies]})

    @book_copies.post("")
    @_require_principal(access_tokens, tenant_request_context)
    def create_copy(book_id: str) -> Response:
        try:
            book_uuid = UUID(book_id)
        except ValueError:
            return _bad_request("Invalid book_id UUID format.")
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return _bad_request("Invalid JSON payload.")
        location_id_raw = payload.get("location_id")
        barcode = payload.get("barcode")
        condition_code = payload.get("condition_code", "good")
        if location_id_raw is None or not isinstance(barcode, str):
            return _bad_request("location_id and barcode are required.")
        if not isinstance(condition_code, str):
            return _bad_request("condition_code must be a string.")
        try:
            loc_uuid = UUID(str(location_id_raw))
        except ValueError:
            return _bad_request("Invalid location_id UUID format.")
        try:
            copy = service.create_copy(
                actor=_principal_from_request(),
                book_id=book_uuid,
                location_id=loc_uuid,
                barcode=barcode,
                condition_code=condition_code,
            )
        except DuplicateBarcodeError:
            return _conflict("Barcode already exists in organization.")
        except KeyError:
            return _not_found("Book or location not found.")
        except ValueError as err:
            return _bad_request(str(err))
        response = jsonify(_copy_response(copy))
        response.status_code = 201
        return response

    @book_copies.get("/<copy_id>")
    @_require_principal(access_tokens, tenant_request_context)
    def get_copy(book_id: str, copy_id: str) -> Response:
        try:
            UUID(book_id)
            copy_uuid = UUID(copy_id)
        except ValueError:
            return _bad_request("Invalid UUID format.")
        try:
            copy = service.get_copy(actor=_principal_from_request(), copy_id=copy_uuid)
        except KeyError:
            return _not_found("Copy not found.")
        return jsonify(_copy_response(copy))

    @book_copies.patch("/<copy_id>")
    @_require_principal(access_tokens, tenant_request_context)
    def update_copy(book_id: str, copy_id: str) -> Response:
        try:
            UUID(book_id)
            copy_uuid = UUID(copy_id)
        except ValueError:
            return _bad_request("Invalid UUID format.")
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return _bad_request("Invalid JSON payload.")
        loc_uuid: UUID | None = None
        if "location_id" in payload and payload["location_id"] is not None:
            try:
                loc_uuid = UUID(str(payload["location_id"]))
            except ValueError:
                return _bad_request("Invalid location_id UUID format.")
        condition = payload.get("condition_code")
        if condition is not None and not isinstance(condition, str):
            return _bad_request("condition_code must be a string.")
        try:
            copy = service.update_copy(
                actor=_principal_from_request(),
                copy_id=copy_uuid,
                location_id=loc_uuid,
                condition_code=condition,
            )
        except KeyError:
            return _not_found("Copy or location not found.")
        except ValueError as err:
            return _bad_request(str(err))
        return jsonify(_copy_response(copy))

    return book_copies


def create_copies_blueprint(
    service: InventoryService,
    access_tokens: AccessTokenService,
    tenant_request_context: TenantRequestContext | None,
) -> Blueprint:
    """Expose direct copy operations by copy_id."""
    copies = Blueprint("copies", __name__, url_prefix="/api/v1/copies")

    @copies.get("/<copy_id>")
    @_require_principal(access_tokens, tenant_request_context)
    def get_copy(copy_id: str) -> Response:
        try:
            copy_uuid = UUID(copy_id)
        except ValueError:
            return _bad_request("Invalid copy_id UUID format.")
        try:
            copy = service.get_copy(actor=_principal_from_request(), copy_id=copy_uuid)
        except KeyError:
            return _not_found("Copy not found.")
        return jsonify(_copy_response(copy))

    @copies.patch("/<copy_id>")
    @_require_principal(access_tokens, tenant_request_context)
    def update_copy(copy_id: str) -> Response:
        try:
            copy_uuid = UUID(copy_id)
        except ValueError:
            return _bad_request("Invalid copy_id UUID format.")
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return _bad_request("Invalid JSON payload.")
        loc_uuid: UUID | None = None
        if "location_id" in payload and payload["location_id"] is not None:
            try:
                loc_uuid = UUID(str(payload["location_id"]))
            except ValueError:
                return _bad_request("Invalid location_id UUID format.")
        condition = payload.get("condition_code")
        if condition is not None and not isinstance(condition, str):
            return _bad_request("condition_code must be a string.")
        try:
            copy = service.update_copy(
                actor=_principal_from_request(),
                copy_id=copy_uuid,
                location_id=loc_uuid,
                condition_code=condition,
            )
        except KeyError:
            return _not_found("Copy or location not found.")
        except ValueError as err:
            return _bad_request(str(err))
        return jsonify(_copy_response(copy))

    return copies


def _location_response(loc: Location) -> dict[str, Any]:
    return {
        "location_id": str(loc.location_id),
        "name": loc.name,
        "code": loc.code,
        "parent_location_id": str(loc.parent_location_id)
        if loc.parent_location_id
        else None,
        "status": loc.status,
    }


def _copy_response(copy: BookCopy) -> dict[str, Any]:
    return {
        "copy_id": str(copy.copy_id),
        "book_id": str(copy.book_id),
        "barcode": copy.barcode,
        "location_id": str(copy.location_id),
        "status": copy.status,
        "condition_code": copy.condition_code,
        "acquired_at": copy.acquired_at.isoformat(),
    }


def _problem_response(status: int, title: str, detail: str) -> Response:
    type_suffix = "bad-request"
    if status == 404:
        type_suffix = "not-found"
    elif status == 409:
        type_suffix = "conflict"
    elif status == 403:
        type_suffix = "forbidden"
    response = jsonify(
        {
            "type": f"https://openlibraryos.example/problems/{type_suffix}",
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


def _not_found(detail: str = "Resource not found.") -> Response:
    return _problem_response(404, "Not Found", detail)


def _conflict(detail: str = "Resource conflict.") -> Response:
    return _problem_response(409, "Conflict", detail)
