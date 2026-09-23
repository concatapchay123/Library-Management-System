"""Protected HTTP adapters for the reservation lifecycle."""

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
from openlibrary.modules.core.application.reservations import (
    Reservation,
    ReservationService,
)
from openlibrary.modules.core.domain.reservations import (
    ActiveReservationLimitExceededError,
    CopyNotAvailableForReservationError,
    InvalidReservationStatusTransitionError,
    ReservationNotEligibleForClaimError,
    ReservationNotFoundError,
)
from openlibrary.modules.core.infrastructure.tenancy import TenantRequestContext


def create_reservations_blueprint(
    service: ReservationService,
    access_tokens: AccessTokenService,
    tenant_request_context: TenantRequestContext | None = None,
) -> Blueprint:
    """Expose reservation endpoints under tenant context."""
    reservations = Blueprint(
        "reservations", __name__, url_prefix="/api/v1/reservations"
    )

    @reservations.post("")
    @_require_principal(access_tokens, tenant_request_context)
    def create_reservation() -> Response:
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return _bad_request("Invalid JSON payload.")

        raw_book_id = payload.get("book_id")
        if not raw_book_id:
            return _bad_request("Field 'book_id' is required.")

        try:
            book_id = UUID(str(raw_book_id))
        except ValueError:
            return _bad_request("Invalid 'book_id' UUID format.")

        copy_id = None
        raw_copy_id = payload.get("copy_id")
        if raw_copy_id:
            try:
                copy_id = UUID(str(raw_copy_id))
            except ValueError:
                return _bad_request("Invalid 'copy_id' UUID format.")

        requester_user_id = None
        raw_requester = payload.get("requester_user_id")
        if raw_requester:
            try:
                requester_user_id = UUID(str(raw_requester))
            except ValueError:
                return _bad_request("Invalid 'requester_user_id' UUID format.")

        corr_id = None
        if request_id():
            try:
                corr_id = UUID(request_id())
            except ValueError:
                pass

        try:
            reservation = service.create_reservation(
                actor=_principal_from_request(),
                book_id=book_id,
                copy_id=copy_id,
                requester_user_id=requester_user_id,
                correlation_id=corr_id,
            )
            response = jsonify(_reservation_response(reservation))
            response.status_code = 201
            return response
        except ActiveReservationLimitExceededError as err:
            return _problem_response(
                err.status_code, err.title, str(err), type_uri=err.problem_type
            )
        except CopyNotAvailableForReservationError as err:
            return _problem_response(
                err.status_code, err.title, str(err), type_uri=err.problem_type
            )
        except AuthorizationDenied as err:
            return _problem_response(403, "Forbidden", str(err))

    @reservations.get("")
    @_require_principal(access_tokens, tenant_request_context)
    def list_reservations() -> Response:
        book_id = None
        raw_book_id = request.args.get("book_id")
        if raw_book_id:
            try:
                book_id = UUID(raw_book_id)
            except ValueError:
                return _bad_request("Invalid 'book_id' UUID format.")

        requester_user_id = None
        raw_requester = request.args.get("requester_user_id")
        if raw_requester:
            try:
                requester_user_id = UUID(raw_requester)
            except ValueError:
                return _bad_request("Invalid 'requester_user_id' UUID format.")

        status = request.args.get("status")

        try:
            items = service.list_reservations(
                actor=_principal_from_request(),
                book_id=book_id,
                requester_user_id=requester_user_id,
                status=status,
            )
            return jsonify(
                {
                    "items": [_reservation_response(r) for r in items],
                    "total": len(items),
                }
            )
        except AuthorizationDenied as err:
            return _problem_response(403, "Forbidden", str(err))

    @reservations.get("/<reservation_id>")
    @_require_principal(access_tokens, tenant_request_context)
    def get_reservation(reservation_id: str) -> Response:
        try:
            res_uuid = UUID(reservation_id)
        except ValueError:
            return _bad_request("Invalid reservation_id UUID format.")

        try:
            res = service.get_reservation(
                actor=_principal_from_request(), reservation_id=res_uuid
            )
            return jsonify(_reservation_response(res))
        except (KeyError, ReservationNotFoundError):
            return _not_found(f"Reservation {reservation_id} not found.")
        except AuthorizationDenied as err:
            return _problem_response(403, "Forbidden", str(err))

    @reservations.post("/<reservation_id>/cancel")
    @_require_principal(access_tokens, tenant_request_context)
    def cancel_reservation(reservation_id: str) -> Response:
        try:
            res_uuid = UUID(reservation_id)
        except ValueError:
            return _bad_request("Invalid reservation_id UUID format.")

        corr_id = None
        if request_id():
            try:
                corr_id = UUID(request_id())
            except ValueError:
                pass

        try:
            res = service.cancel_reservation(
                actor=_principal_from_request(),
                reservation_id=res_uuid,
                correlation_id=corr_id,
            )
            return jsonify(_reservation_response(res))
        except (KeyError, ReservationNotFoundError):
            return _not_found(f"Reservation {reservation_id} not found.")
        except InvalidReservationStatusTransitionError as err:
            return _problem_response(
                err.status_code, err.title, str(err), type_uri=err.problem_type
            )
        except AuthorizationDenied as err:
            return _problem_response(403, "Forbidden", str(err))

    @reservations.post("/<reservation_id>/claim")
    @_require_principal(access_tokens, tenant_request_context)
    def claim_reservation(reservation_id: str) -> Response:
        try:
            res_uuid = UUID(reservation_id)
        except ValueError:
            return _bad_request("Invalid reservation_id UUID format.")

        corr_id = None
        if request_id():
            try:
                corr_id = UUID(request_id())
            except ValueError:
                pass

        try:
            res = service.claim_reservation(
                actor=_principal_from_request(),
                reservation_id=res_uuid,
                correlation_id=corr_id,
            )
            return jsonify(_reservation_response(res))
        except (KeyError, ReservationNotFoundError):
            return _not_found(f"Reservation {reservation_id} not found.")
        except ReservationNotEligibleForClaimError as err:
            return _problem_response(
                err.status_code, err.title, str(err), type_uri=err.problem_type
            )
        except InvalidReservationStatusTransitionError as err:
            return _problem_response(
                err.status_code, err.title, str(err), type_uri=err.problem_type
            )
        except AuthorizationDenied as err:
            return _problem_response(403, "Forbidden", str(err))

    return reservations


def _reservation_response(reservation: Reservation) -> dict[str, Any]:
    return {
        "reservation_id": str(reservation.reservation_id),
        "organization_id": str(reservation.organization_id),
        "book_id": str(reservation.book_id),
        "requester_user_id": str(reservation.requester_user_id),
        "copy_id": str(reservation.copy_id) if reservation.copy_id else None,
        "queue_position": reservation.queue_position,
        "status": reservation.status,
        "hold_expires_at": (
            reservation.hold_expires_at.isoformat()
            if reservation.hold_expires_at
            else None
        ),
        "created_at": reservation.created_at.isoformat(),
        "updated_at": reservation.updated_at.isoformat(),
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


def _not_found(detail: str = "Resource not found.") -> Response:
    return _problem_response(404, "Not Found", detail)
