"""HTTP API adapter for public library edition endpoints."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
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
from openlibrary.modules.core.infrastructure.tenancy import TenantRequestContext
from openlibrary.modules.public_library.application import PublicLibraryService
from openlibrary.modules.public_library.domain import (
    ActiveSubscriptionExistsError,
    DuplicateIdentifierError,
    EditionUnavailableError,
    InvalidPlanError,
    InvalidSubscriptionDatesError,
    Member,
    MemberNotFoundError,
    MembershipPlan,
    MembershipPlanNotFoundError,
    ProfileAlreadyExistsError,
    Subscription,
    SubscriptionInactiveError,
    SubscriptionNotFoundError,
)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def _member_dict(m: Member) -> dict[str, Any]:
    return {
        "member_id": str(m.member_id),
        "organization_id": str(m.organization_id),
        "user_id": str(m.user_id),
        "member_number": m.member_number,
        "status": m.status,
        "created_at": _iso(m.created_at),
        "updated_at": _iso(m.updated_at),
    }


def _plan_dict(p: MembershipPlan) -> dict[str, Any]:
    return {
        "plan_id": str(p.plan_id),
        "organization_id": str(p.organization_id),
        "code": p.code,
        "name": p.name,
        "description": p.description,
        "max_active_loans": p.max_active_loans,
        "duration_days": p.duration_days,
        "price": str(p.price),
        "currency": p.currency,
        "status": p.status,
        "created_at": _iso(p.created_at),
        "updated_at": _iso(p.updated_at),
    }


def _subscription_dict(s: Subscription) -> dict[str, Any]:
    return {
        "subscription_id": str(s.subscription_id),
        "organization_id": str(s.organization_id),
        "member_id": str(s.member_id),
        "plan_id": str(s.plan_id),
        "starts_at": _iso(s.starts_at),
        "ends_at": _iso(s.ends_at),
        "status": s.status,
        "created_at": _iso(s.created_at),
        "updated_at": _iso(s.updated_at),
    }


def _problem(status: int, title: str, detail: str, type_suffix: str) -> Response:
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


def _handle_public_library_error(err: Exception) -> Response:
    if isinstance(err, EditionUnavailableError):
        return _problem(
            403,
            "Edition unavailable",
            "The public library edition is not enabled for this organization.",
            "edition-unavailable",
        )
    if isinstance(err, DuplicateIdentifierError):
        return _problem(409, "Duplicate identifier", str(err), "duplicate-identifier")
    if isinstance(err, ProfileAlreadyExistsError):
        return _problem(
            409, "Profile already exists", str(err), "profile-already-exists"
        )
    if isinstance(err, ActiveSubscriptionExistsError):
        return _problem(
            409,
            "Active subscription exists",
            str(err),
            "active-subscription-exists",
        )
    if isinstance(
        err,
        (MemberNotFoundError, MembershipPlanNotFoundError, SubscriptionNotFoundError),
    ):
        return _problem(404, "Not Found", str(err), "not-found")
    if isinstance(err, InvalidSubscriptionDatesError):
        return _problem(
            422,
            "Invalid subscription dates",
            str(err),
            "invalid-subscription-dates",
        )
    if isinstance(err, SubscriptionInactiveError):
        return _problem(
            422,
            "Subscription inactive",
            str(err),
            "subscription-inactive",
        )
    if isinstance(err, InvalidPlanError):
        return _problem(422, "Invalid plan", str(err), "invalid-plan")
    if isinstance(err, AuthorizationDenied):
        return _problem(403, "Forbidden", "Authorization denied.", "forbidden")
    if isinstance(err, ValueError):
        return _problem(400, "Bad Request", str(err), "bad-request")
    raise err


def create_public_library_blueprint(
    service: PublicLibraryService,
    access_tokens: AccessTokenService,
    tenant_request_context: TenantRequestContext | None = None,
    url_prefix: str = "/api/v1/public-library",
) -> Blueprint:
    """Create blueprint for public library endpoints."""
    bp_name = f"public_library_{url_prefix.replace('/', '_').strip('_')}"
    bp = Blueprint(bp_name, __name__, url_prefix=url_prefix)

    # --- Members ---

    @bp.post("/members")
    @_require_principal(access_tokens, tenant_request_context)
    def create_member() -> Response:
        try:
            body = request.get_json(force=True) or {}
            raw_user_id = body.get("user_id")
            if not raw_user_id:
                raise ValueError("user_id is required")
            member_number = body.get("member_number", "")
            status = body.get("status", "active")
            created = service.create_member(
                actor=_principal_from_request(),
                user_id=UUID(str(raw_user_id)),
                member_number=str(member_number),
                status=str(status),
            )
            response = jsonify(_member_dict(created))
            response.status_code = 201
            return response
        except Exception as err:
            return _handle_public_library_error(err)

    @bp.get("/members")
    @_require_principal(access_tokens, tenant_request_context)
    def list_members() -> Response:
        try:
            members = service.list_members(actor=_principal_from_request())
            return jsonify({"items": [_member_dict(m) for m in members]})
        except Exception as err:
            return _handle_public_library_error(err)

    @bp.get("/members/<uuid:member_id>")
    @_require_principal(access_tokens, tenant_request_context)
    def get_member(member_id: UUID) -> Response:
        try:
            member = service.get_member(
                actor=_principal_from_request(), member_id=member_id
            )
            return jsonify(_member_dict(member))
        except Exception as err:
            return _handle_public_library_error(err)

    @bp.get("/members/by-user/<uuid:user_id>")
    @_require_principal(access_tokens, tenant_request_context)
    def get_member_by_user(user_id: UUID) -> Response:
        try:
            member = service.get_member_by_user_id(
                actor=_principal_from_request(), user_id=user_id
            )
            return jsonify(_member_dict(member))
        except Exception as err:
            return _handle_public_library_error(err)

    @bp.patch("/members/<uuid:member_id>/status")
    @_require_principal(access_tokens, tenant_request_context)
    def update_member_status(member_id: UUID) -> Response:
        try:
            body = request.get_json(force=True) or {}
            status = body.get("status")
            if not status:
                raise ValueError("status is required")
            updated = service.update_member_status(
                actor=_principal_from_request(),
                member_id=member_id,
                status=str(status),
            )
            return jsonify(_member_dict(updated))
        except Exception as err:
            return _handle_public_library_error(err)

    # --- Membership Plans (with /membership-plans and /plans endpoints) ---

    def _list_plans_handler() -> Response:
        try:
            status = request.args.get("status")
            plans = service.list_plans(actor=_principal_from_request(), status=status)
            return jsonify({"items": [_plan_dict(p) for p in plans]})
        except Exception as err:
            return _handle_public_library_error(err)

    def _create_plan_handler() -> Response:
        try:
            body = request.get_json(force=True) or {}
            code = body.get("code")
            name = body.get("name")
            if not code or not name:
                raise ValueError("code and name are required")
            max_active_loans = int(body.get("max_active_loans", 5))
            duration_days = int(body.get("duration_days", 30))
            description = body.get("description")
            raw_price = body.get("price", "0.0000")
            price = Decimal(str(raw_price))
            currency = body.get("currency", "USD")
            status = body.get("status", "active")

            plan = service.create_plan(
                actor=_principal_from_request(),
                code=str(code),
                name=str(name),
                max_active_loans=max_active_loans,
                duration_days=duration_days,
                description=str(description) if description else None,
                price=price,
                currency=str(currency),
                status=str(status),
            )
            response = jsonify(_plan_dict(plan))
            response.status_code = 201
            return response
        except Exception as err:
            return _handle_public_library_error(err)

    def _get_plan_handler(plan_id: UUID) -> Response:
        try:
            plan = service.get_plan(actor=_principal_from_request(), plan_id=plan_id)
            return jsonify(_plan_dict(plan))
        except Exception as err:
            return _handle_public_library_error(err)

    def _update_plan_handler(plan_id: UUID) -> Response:
        try:
            body = request.get_json(force=True) or {}
            name = body.get("name")
            description = body.get("description")
            max_active_loans = (
                int(body["max_active_loans"]) if "max_active_loans" in body else None
            )
            duration_days = (
                int(body["duration_days"]) if "duration_days" in body else None
            )
            price = Decimal(str(body["price"])) if "price" in body else None
            currency = body.get("currency")
            status = body.get("status")

            updated = service.update_plan(
                actor=_principal_from_request(),
                plan_id=plan_id,
                name=str(name) if name is not None else None,
                description=str(description) if description is not None else None,
                max_active_loans=max_active_loans,
                duration_days=duration_days,
                price=price,
                currency=str(currency) if currency is not None else None,
                status=str(status) if status is not None else None,
            )
            return jsonify(_plan_dict(updated))
        except Exception as err:
            return _handle_public_library_error(err)

    def _seed_plans_handler() -> Response:
        try:
            seeded = service.seed_default_plans(actor=_principal_from_request())
            return jsonify({"items": [_plan_dict(p) for p in seeded]})
        except Exception as err:
            return _handle_public_library_error(err)

    # Register handlers for both /membership-plans and /plans
    for route_base in ("/membership-plans", "/plans"):
        bp.add_url_rule(
            route_base,
            f"list_plans{route_base.replace('-', '_')}",
            _require_principal(access_tokens, tenant_request_context)(
                _list_plans_handler
            ),
            methods=["GET"],
        )
        bp.add_url_rule(
            route_base,
            f"create_plan{route_base.replace('-', '_')}",
            _require_principal(access_tokens, tenant_request_context)(
                _create_plan_handler
            ),
            methods=["POST"],
        )
        bp.add_url_rule(
            f"{route_base}/<uuid:plan_id>",
            f"get_plan{route_base.replace('-', '_')}",
            _require_principal(access_tokens, tenant_request_context)(
                _get_plan_handler
            ),
            methods=["GET"],
        )
        bp.add_url_rule(
            f"{route_base}/<uuid:plan_id>",
            f"update_plan{route_base.replace('-', '_')}",
            _require_principal(access_tokens, tenant_request_context)(
                _update_plan_handler
            ),
            methods=["PUT"],
        )
        bp.add_url_rule(
            f"{route_base}/seed",
            f"seed_plans{route_base.replace('-', '_')}",
            _require_principal(access_tokens, tenant_request_context)(
                _seed_plans_handler
            ),
            methods=["POST"],
        )

    # --- Subscriptions ---

    @bp.post("/subscriptions")
    @_require_principal(access_tokens, tenant_request_context)
    def create_subscription() -> Response:
        try:
            body = request.get_json(force=True) or {}
            raw_member_id = body.get("member_id")
            raw_plan_id = body.get("plan_id")
            raw_starts_at = body.get("starts_at")
            raw_ends_at = body.get("ends_at")
            if (
                not raw_member_id
                or not raw_plan_id
                or not raw_starts_at
                or not raw_ends_at
            ):
                raise ValueError(
                    "member_id, plan_id, starts_at, and ends_at are required"
                )

            starts_at = datetime.fromisoformat(str(raw_starts_at))
            ends_at = datetime.fromisoformat(str(raw_ends_at))
            status = body.get("status", "active")

            sub = service.create_subscription(
                actor=_principal_from_request(),
                member_id=UUID(str(raw_member_id)),
                plan_id=UUID(str(raw_plan_id)),
                starts_at=starts_at,
                ends_at=ends_at,
                status=str(status),
            )
            response = jsonify(_subscription_dict(sub))
            response.status_code = 201
            return response
        except Exception as err:
            return _handle_public_library_error(err)

    @bp.get("/subscriptions")
    @_require_principal(access_tokens, tenant_request_context)
    def list_subscriptions() -> Response:
        try:
            raw_member_id = request.args.get("member_id")
            member_id = UUID(raw_member_id) if raw_member_id else None
            status = request.args.get("status")
            subs = service.list_subscriptions(
                actor=_principal_from_request(),
                member_id=member_id,
                status=status,
            )
            return jsonify({"items": [_subscription_dict(s) for s in subs]})
        except Exception as err:
            return _handle_public_library_error(err)

    @bp.get("/subscriptions/<uuid:subscription_id>")
    @_require_principal(access_tokens, tenant_request_context)
    def get_subscription(subscription_id: UUID) -> Response:
        try:
            sub = service.get_subscription(
                actor=_principal_from_request(), subscription_id=subscription_id
            )
            return jsonify(_subscription_dict(sub))
        except Exception as err:
            return _handle_public_library_error(err)

    @bp.post("/subscriptions/<uuid:subscription_id>/cancel")
    @_require_principal(access_tokens, tenant_request_context)
    def cancel_subscription(subscription_id: UUID) -> Response:
        try:
            sub = service.cancel_subscription(
                actor=_principal_from_request(), subscription_id=subscription_id
            )
            return jsonify(_subscription_dict(sub))
        except Exception as err:
            return _handle_public_library_error(err)

    return bp
