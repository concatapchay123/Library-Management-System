"""HTTP API adapter for public library edition endpoints."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from flask import Blueprint, Response, jsonify, request

from openlibrary.app.correlation import request_id
from openlibrary.modules.core.api.auth import (
    _principal_from_request,
    _require_principal,
)
from openlibrary.modules.core.application.access_tokens import AccessTokenService
from openlibrary.modules.core.application.authorization import AuthorizationDenied
from openlibrary.modules.core.infrastructure.tenancy import TenantRequestContext
from openlibrary.modules.public_library.application import (
    PublicLibraryFinanceService,
    PublicLibraryService,
)
from openlibrary.modules.public_library.domain import (
    ActiveSubscriptionExistsError,
    AllocationNotFoundError,
    AllocationType,
    CurrencyMismatchError,
    DuplicateIdentifierError,
    DuplicateProviderEventError,
    DuplicateProviderReferenceError,
    EditionUnavailableError,
    Fine,
    FineAlreadyClosedError,
    FineNotFoundError,
    InvalidAllocationAmountError,
    InvalidMoneyError,
    InvalidPaymentStateTransitionError,
    InvalidPlanError,
    InvalidSubscriptionDatesError,
    InvalidWebhookSignatureError,
    Invoice,
    InvoiceImmutableError,
    InvoiceLine,
    InvoiceNotFoundError,
    Member,
    MemberNotFoundError,
    MembershipPlan,
    MembershipPlanNotFoundError,
    MissingWebhookSignatureError,
    OverAllocationError,
    OverRefundError,
    Payment,
    PaymentAllocation,
    PaymentNotFoundError,
    ProfileAlreadyExistsError,
    StaleWebhookTimestampError,
    Subscription,
    SubscriptionInactiveError,
    SubscriptionNotFoundError,
)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def _fine_dict(f: Fine) -> dict[str, Any]:
    return {
        "fine_id": str(f.fine_id),
        "organization_id": str(f.organization_id),
        "member_id": str(f.member_id),
        "loan_id": str(f.loan_id) if f.loan_id else None,
        "amount": str(f.amount),
        "currency": f.currency,
        "status": f.status,
        "reason": f.reason,
        "assessed_at": _iso(f.assessed_at),
        "created_at": _iso(f.created_at),
        "updated_at": _iso(f.updated_at),
    }


def _invoice_line_dict(line: InvoiceLine) -> dict[str, Any]:
    return {
        "invoice_line_id": str(line.invoice_line_id),
        "organization_id": str(line.organization_id),
        "invoice_id": str(line.invoice_id),
        "line_number": line.line_number,
        "description": line.description,
        "quantity": line.quantity,
        "unit_price": str(line.unit_price),
        "amount": str(line.amount),
        "fine_id": str(line.fine_id) if line.fine_id else None,
        "created_at": _iso(line.created_at),
    }


def _invoice_dict(inv: Invoice) -> dict[str, Any]:
    return {
        "invoice_id": str(inv.invoice_id),
        "organization_id": str(inv.organization_id),
        "member_id": str(inv.member_id),
        "invoice_number": inv.invoice_number,
        "subtotal": str(inv.subtotal),
        "tax": str(inv.tax),
        "total": str(inv.total),
        "currency": inv.currency,
        "status": inv.status,
        "issued_at": _iso(inv.issued_at),
        "due_at": _iso(inv.due_at),
        "created_at": _iso(inv.created_at),
        "updated_at": _iso(inv.updated_at),
        "lines": [_invoice_line_dict(line) for line in inv.lines],
    }


def _payment_dict(p: Payment) -> dict[str, Any]:
    return {
        "payment_id": str(p.payment_id),
        "organization_id": str(p.organization_id),
        "member_id": str(p.member_id),
        "amount": str(p.amount),
        "currency": p.currency,
        "provider": p.provider,
        "status": p.status,
        "provider_reference": p.provider_reference,
        "provider_event_id": p.provider_event_id,
        "paid_at": _iso(p.paid_at),
        "created_at": _iso(p.created_at),
        "updated_at": _iso(p.updated_at),
    }


def _allocation_dict(a: PaymentAllocation) -> dict[str, Any]:
    return {
        "allocation_id": str(a.allocation_id),
        "organization_id": str(a.organization_id),
        "payment_id": str(a.payment_id),
        "fine_id": str(a.fine_id),
        "amount": str(a.amount),
        "allocation_type": a.allocation_type,
        "invoice_id": str(a.invoice_id) if a.invoice_id else None,
        "created_at": _iso(a.created_at),
    }


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
        (
            MemberNotFoundError,
            MembershipPlanNotFoundError,
            SubscriptionNotFoundError,
            FineNotFoundError,
            InvoiceNotFoundError,
            PaymentNotFoundError,
            AllocationNotFoundError,
        ),
    ):
        return _problem(404, "Not Found", str(err), "not-found")
    if isinstance(
        err,
        (
            InvoiceImmutableError,
            OverAllocationError,
            FineAlreadyClosedError,
            DuplicateProviderReferenceError,
            DuplicateProviderEventError,
            InvalidPaymentStateTransitionError,
            OverRefundError,
        ),
    ):
        return _problem(409, "Financial Conflict", str(err), "financial-conflict")
    if isinstance(err, InvalidWebhookSignatureError):
        return _problem(
            401,
            "Invalid Webhook Signature",
            str(err),
            "invalid-webhook-signature",
        )
    if isinstance(err, (MissingWebhookSignatureError, StaleWebhookTimestampError)):
        return _problem(
            400,
            "Bad Webhook Request",
            str(err),
            "bad-webhook-request",
        )
    if isinstance(
        err,
        (
            InvalidSubscriptionDatesError,
            SubscriptionInactiveError,
            InvalidPlanError,
            CurrencyMismatchError,
            InvalidMoneyError,
            InvalidAllocationAmountError,
        ),
    ):
        return _problem(
            422,
            "Unprocessable Content",
            str(err),
            "unprocessable-content",
        )
    if isinstance(err, AuthorizationDenied):
        return _problem(403, "Forbidden", "Authorization denied.", "forbidden")
    if isinstance(err, (TypeError, ValueError)):
        return _problem(400, "Bad Request", str(err), "bad-request")
    raise err


def _parse_decimal(val: Any, field_name: str) -> Decimal:
    if val is None:
        raise ValueError(f"{field_name} is required")
    if isinstance(val, float):
        raise TypeError(
            f"Floating-point money amounts are rejected for {field_name}; use a string or Decimal instead."
        )
    try:
        return Decimal(str(val))
    except Exception as exc:
        raise ValueError(f"Invalid decimal value for {field_name}: {val}") from exc


def create_public_library_blueprint(
    service: PublicLibraryService,
    access_tokens: AccessTokenService,
    tenant_request_context: TenantRequestContext | None = None,
    url_prefix: str = "/api/v1/public-library",
    finance_service: PublicLibraryFinanceService | None = None,
) -> Blueprint:
    """Create blueprint for public library endpoints."""
    bp_name = f"public_library_{url_prefix.replace('/', '_').strip('_')}"
    bp = Blueprint(bp_name, __name__, url_prefix=url_prefix)

    fin_service = finance_service or PublicLibraryFinanceService(
        store=service._store,
        authorizer=service._authorizer,
        clock=service._clock,
    )

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

    # --- Fines ---

    @bp.post("/fines")
    @_require_principal(access_tokens, tenant_request_context)
    def assess_fine() -> Response:
        try:
            body = request.get_json(force=True) or {}
            raw_member_id = body.get("member_id")
            if not raw_member_id:
                raise ValueError("member_id is required")
            raw_amount = body.get("amount")
            amount = _parse_decimal(raw_amount, "amount")
            currency = body.get("currency")
            if not currency:
                raise ValueError("currency is required")
            reason = body.get("reason")
            if not reason:
                raise ValueError("reason is required")
            raw_loan_id = body.get("loan_id")
            loan_id = UUID(str(raw_loan_id)) if raw_loan_id else None

            fine = fin_service.assess_fine(
                actor=_principal_from_request(),
                member_id=UUID(str(raw_member_id)),
                amount=amount,
                currency=str(currency),
                reason=str(reason),
                loan_id=loan_id,
            )
            response = jsonify(_fine_dict(fine))
            response.status_code = 201
            return response
        except Exception as err:
            return _handle_public_library_error(err)

    @bp.get("/fines")
    @_require_principal(access_tokens, tenant_request_context)
    def list_fines() -> Response:
        try:
            raw_member_id = request.args.get("member_id")
            member_id = UUID(raw_member_id) if raw_member_id else None
            raw_loan_id = request.args.get("loan_id")
            loan_id = UUID(raw_loan_id) if raw_loan_id else None
            status = request.args.get("status")
            fines = fin_service.list_fines(
                actor=_principal_from_request(),
                member_id=member_id,
                loan_id=loan_id,
                status=status,
            )
            return jsonify({"items": [_fine_dict(f) for f in fines]})
        except Exception as err:
            return _handle_public_library_error(err)

    @bp.get("/fines/<uuid:fine_id>")
    @_require_principal(access_tokens, tenant_request_context)
    def get_fine(fine_id: UUID) -> Response:
        try:
            fine = fin_service.get_fine(
                actor=_principal_from_request(), fine_id=fine_id
            )
            return jsonify(_fine_dict(fine))
        except Exception as err:
            return _handle_public_library_error(err)

    @bp.post("/fines/calculate")
    @_require_principal(access_tokens, tenant_request_context)
    def calculate_fine() -> Response:
        try:
            body = request.get_json(force=True) or {}
            raw_due_at = body.get("due_at")
            raw_return_at = body.get("effective_return_at")
            if not raw_due_at or not raw_return_at:
                raise ValueError("due_at and effective_return_at are required")
            due_at = datetime.fromisoformat(str(raw_due_at))
            effective_return_at = datetime.fromisoformat(str(raw_return_at))
            daily_rate = _parse_decimal(body.get("daily_rate"), "daily_rate")
            currency = body.get("currency")
            if not currency:
                raise ValueError("currency is required")
            max_fine = (
                _parse_decimal(body["max_fine"], "max_fine")
                if "max_fine" in body and body["max_fine"] is not None
                else None
            )

            money = fin_service.calculate_overdue_fine(
                due_at=due_at,
                effective_return_at=effective_return_at,
                daily_rate=daily_rate,
                currency=str(currency),
                max_fine=max_fine,
            )
            return jsonify({"amount": str(money.amount), "currency": money.currency})
        except Exception as err:
            return _handle_public_library_error(err)

    @bp.post("/fines/<uuid:fine_id>/waive")
    @_require_principal(access_tokens, tenant_request_context)
    def waive_fine(fine_id: UUID) -> Response:
        try:
            body = request.get_json(force=True) or {}
            reason = body.get("reason")
            if not reason:
                raise ValueError("reason is required")
            waived = fin_service.waive_fine(
                actor=_principal_from_request(),
                fine_id=fine_id,
                reason=str(reason),
            )
            return jsonify(_fine_dict(waived))
        except Exception as err:
            return _handle_public_library_error(err)

    @bp.get("/fines/<uuid:fine_id>/allocations")
    @_require_principal(access_tokens, tenant_request_context)
    def list_fine_allocations(fine_id: UUID) -> Response:
        try:
            allocs = fin_service.list_allocations_for_fine(
                actor=_principal_from_request(),
                fine_id=fine_id,
            )
            return jsonify({"items": [_allocation_dict(a) for a in allocs]})
        except Exception as err:
            return _handle_public_library_error(err)

    # --- Invoices ---

    @bp.post("/invoices")
    @_require_principal(access_tokens, tenant_request_context)
    def issue_invoice() -> Response:
        try:
            body = request.get_json(force=True) or {}
            raw_member_id = body.get("member_id")
            if not raw_member_id:
                raise ValueError("member_id is required")
            currency = body.get("currency")
            if not currency:
                raise ValueError("currency is required")

            raw_tax = body.get("tax")
            tax = _parse_decimal(raw_tax, "tax") if raw_tax is not None else None

            raw_due_at = body.get("due_at")
            due_at = datetime.fromisoformat(str(raw_due_at)) if raw_due_at else None

            raw_lines = body.get("lines")
            if not raw_lines or not isinstance(raw_lines, list):
                raise ValueError("lines must be a non-empty list")

            lines: list[InvoiceLine] = []
            for idx, raw_line in enumerate(raw_lines, start=1):
                if not isinstance(raw_line, dict):
                    raise ValueError(f"Line {idx} must be an object")
                desc = raw_line.get("description")
                if not desc:
                    raise ValueError(f"Line {idx} description is required")
                qty = int(raw_line.get("quantity", 1))
                unit_price = _parse_decimal(
                    raw_line.get("unit_price"), f"Line {idx} unit_price"
                )
                amount = _parse_decimal(raw_line.get("amount"), f"Line {idx} amount")
                raw_fine_id = raw_line.get("fine_id")
                fine_id = UUID(str(raw_fine_id)) if raw_fine_id else None

                lines.append(
                    InvoiceLine(
                        invoice_line_id=uuid4(),
                        organization_id=_principal_from_request().organization_id,
                        invoice_id=uuid4(),
                        line_number=idx,
                        description=str(desc),
                        quantity=qty,
                        unit_price=unit_price,
                        amount=amount,
                        created_at=datetime.now(),
                        fine_id=fine_id,
                    )
                )

            inv = fin_service.issue_invoice(
                actor=_principal_from_request(),
                member_id=UUID(str(raw_member_id)),
                lines=lines,
                currency=str(currency),
                tax=tax,
                due_at=due_at,
            )
            response = jsonify(_invoice_dict(inv))
            response.status_code = 201
            return response
        except Exception as err:
            return _handle_public_library_error(err)

    @bp.get("/invoices")
    @_require_principal(access_tokens, tenant_request_context)
    def list_invoices() -> Response:
        try:
            raw_member_id = request.args.get("member_id")
            member_id = UUID(raw_member_id) if raw_member_id else None
            status = request.args.get("status")
            invoices = fin_service.list_invoices(
                actor=_principal_from_request(),
                member_id=member_id,
                status=status,
            )
            return jsonify({"items": [_invoice_dict(inv) for inv in invoices]})
        except Exception as err:
            return _handle_public_library_error(err)

    @bp.get("/invoices/<uuid:invoice_id>")
    @_require_principal(access_tokens, tenant_request_context)
    def get_invoice(invoice_id: UUID) -> Response:
        try:
            invoice = fin_service.get_invoice(
                actor=_principal_from_request(),
                invoice_id=invoice_id,
            )
            return jsonify(_invoice_dict(invoice))
        except Exception as err:
            return _handle_public_library_error(err)

    @bp.put("/invoices/<uuid:invoice_id>")
    @bp.put("/invoices/<uuid:invoice_id>/lines")
    @bp.patch("/invoices/<uuid:invoice_id>")
    @_require_principal(access_tokens, tenant_request_context)
    def update_invoice(invoice_id: UUID) -> Response:
        try:
            body = request.get_json(silent=True) or {}
            raw_lines = body.get("lines", [])
            new_lines: list[InvoiceLine] = []
            actor = _principal_from_request()
            for idx, raw_line in enumerate(raw_lines, start=1):
                desc = raw_line.get("description", "")
                qty = int(raw_line.get("quantity", 1))
                unit_price = _parse_decimal(
                    raw_line.get("unit_price", 0), f"Line {idx} unit_price"
                )
                amount = _parse_decimal(
                    raw_line.get("amount", unit_price * qty), f"Line {idx} amount"
                )
                raw_fine_id = raw_line.get("fine_id")
                fine_id = UUID(str(raw_fine_id)) if raw_fine_id else None
                new_lines.append(
                    InvoiceLine(
                        invoice_line_id=uuid4(),
                        organization_id=actor.organization_id,
                        invoice_id=invoice_id,
                        line_number=idx,
                        description=str(desc),
                        quantity=qty,
                        unit_price=unit_price,
                        amount=amount,
                        created_at=datetime.now(),
                        fine_id=fine_id,
                    )
                )
            fin_service.modify_invoice_lines(
                actor=actor,
                invoice_id=invoice_id,
                new_lines=new_lines,
            )
            return jsonify({"status": "ok"})
        except Exception as err:
            return _handle_public_library_error(err)

    @bp.post("/invoices/<uuid:invoice_id>/void")
    @_require_principal(access_tokens, tenant_request_context)
    def void_invoice(invoice_id: UUID) -> Response:
        try:
            body = request.get_json(force=True) or {}
            reason = body.get("reason")
            if not reason:
                raise ValueError("reason is required")
            voided = fin_service.void_invoice(
                actor=_principal_from_request(),
                invoice_id=invoice_id,
                reason=str(reason),
            )
            return jsonify(_invoice_dict(voided))
        except Exception as err:
            return _handle_public_library_error(err)

    # --- Payments ---

    @bp.post("/payments")
    @_require_principal(access_tokens, tenant_request_context)
    def record_payment() -> Response:
        try:
            body = request.get_json(force=True) or {}
            raw_member_id = body.get("member_id")
            if not raw_member_id:
                raise ValueError("member_id is required")
            amount = _parse_decimal(body.get("amount"), "amount")
            currency = body.get("currency")
            if not currency:
                raise ValueError("currency is required")
            provider = body.get("provider", "manual")
            provider_reference = body.get("provider_reference")
            provider_event_id = body.get("provider_event_id")

            payment = fin_service.record_payment(
                actor=_principal_from_request(),
                member_id=UUID(str(raw_member_id)),
                amount=amount,
                currency=str(currency),
                provider=str(provider),
                provider_reference=str(provider_reference)
                if provider_reference
                else None,
                provider_event_id=str(provider_event_id) if provider_event_id else None,
            )
            response = jsonify(_payment_dict(payment))
            response.status_code = 201
            return response
        except Exception as err:
            return _handle_public_library_error(err)

    @bp.get("/payments")
    @_require_principal(access_tokens, tenant_request_context)
    def list_payments() -> Response:
        try:
            raw_member_id = request.args.get("member_id")
            member_id = UUID(raw_member_id) if raw_member_id else None
            status = request.args.get("status")
            payments = fin_service.list_payments(
                actor=_principal_from_request(),
                member_id=member_id,
                status=status,
            )
            return jsonify({"items": [_payment_dict(p) for p in payments]})
        except Exception as err:
            return _handle_public_library_error(err)

    @bp.get("/payments/<uuid:payment_id>")
    @_require_principal(access_tokens, tenant_request_context)
    def get_payment(payment_id: UUID) -> Response:
        try:
            payment = fin_service.get_payment(
                actor=_principal_from_request(),
                payment_id=payment_id,
            )
            return jsonify(_payment_dict(payment))
        except Exception as err:
            return _handle_public_library_error(err)

    @bp.get("/payments/<uuid:payment_id>/allocations")
    @_require_principal(access_tokens, tenant_request_context)
    def list_payment_allocations(payment_id: UUID) -> Response:
        try:
            allocs = fin_service.list_allocations_for_payment(
                actor=_principal_from_request(),
                payment_id=payment_id,
            )
            return jsonify({"items": [_allocation_dict(a) for a in allocs]})
        except Exception as err:
            return _handle_public_library_error(err)

    @bp.post("/payments/<uuid:payment_id>/refund")
    @_require_principal(access_tokens, tenant_request_context)
    def refund_payment(payment_id: UUID) -> Response:
        try:
            body = request.get_json(force=True) or {}
            amount = _parse_decimal(body.get("amount"), "amount")
            raw_fine_id = body.get("fine_id")
            fine_id = UUID(str(raw_fine_id)) if raw_fine_id else None
            reason = str(body.get("reason", ""))

            allocation = fin_service.refund_payment(
                actor=_principal_from_request(),
                payment_id=payment_id,
                amount=amount,
                fine_id=fine_id,
                reason=reason,
            )
            response = jsonify(_allocation_dict(allocation))
            response.status_code = 201
            return response
        except Exception as err:
            return _handle_public_library_error(err)

    @bp.post("/payments/<uuid:payment_id>/reconcile")
    @_require_principal(access_tokens, tenant_request_context)
    def reconcile_payment(payment_id: UUID) -> Response:
        try:
            principal = _principal_from_request()
            payment = fin_service.reconcile_pending_payment(
                organization_id=principal.organization_id,
                payment_id=payment_id,
            )
            return jsonify(_payment_dict(payment))
        except Exception as err:
            return _handle_public_library_error(err)

    @bp.post("/payments/webhooks/<provider>")
    def handle_payment_webhook(provider: str) -> Response:
        try:
            raw_org_id = request.args.get("organization_id") or request.headers.get(
                "X-Organization-Id"
            )
            if not raw_org_id:
                raise ValueError(
                    "organization_id query parameter or X-Organization-Id header is required"
                )
            try:
                org_id = UUID(str(raw_org_id))
            except Exception as e:
                raise ValueError(f"Invalid organization_id UUID: {raw_org_id}") from e

            raw_body = request.get_data()
            headers = dict(request.headers)

            def _process() -> Response:
                payment = fin_service.handle_payment_webhook(
                    organization_id=org_id,
                    provider=provider,
                    raw_body=raw_body,
                    headers=headers,
                )
                return jsonify(_payment_dict(payment))

            if tenant_request_context is not None:
                with tenant_request_context.request(org_id):
                    return _process()
            return _process()
        except Exception as err:
            return _handle_public_library_error(err)

    # --- Allocations ---

    @bp.post("/allocations")
    @_require_principal(access_tokens, tenant_request_context)
    def allocate_payment() -> Response:
        try:
            body = request.get_json(force=True) or {}
            raw_payment_id = body.get("payment_id")
            raw_fine_id = body.get("fine_id")
            if not raw_payment_id or not raw_fine_id:
                raise ValueError("payment_id and fine_id are required")
            amount = _parse_decimal(body.get("amount"), "amount")
            raw_invoice_id = body.get("invoice_id")
            invoice_id = UUID(str(raw_invoice_id)) if raw_invoice_id else None
            allocation_type = body.get("allocation_type", AllocationType.PAYMENT)

            allocation = fin_service.allocate_payment(
                actor=_principal_from_request(),
                payment_id=UUID(str(raw_payment_id)),
                fine_id=UUID(str(raw_fine_id)),
                amount=amount,
                invoice_id=invoice_id,
                allocation_type=str(allocation_type),
            )
            response = jsonify(_allocation_dict(allocation))
            response.status_code = 201
            return response
        except Exception as err:
            return _handle_public_library_error(err)

    @bp.get("/allocations/<uuid:allocation_id>")
    @_require_principal(access_tokens, tenant_request_context)
    def get_allocation(allocation_id: UUID) -> Response:
        try:
            allocation = fin_service.get_allocation(
                actor=_principal_from_request(),
                allocation_id=allocation_id,
            )
            return jsonify(_allocation_dict(allocation))
        except Exception as err:
            return _handle_public_library_error(err)

    @bp.get("/allocations")
    @_require_principal(access_tokens, tenant_request_context)
    def list_allocations() -> Response:
        try:
            raw_fine_id = request.args.get("fine_id")
            raw_payment_id = request.args.get("payment_id")
            if raw_fine_id:
                allocs = fin_service.list_allocations_for_fine(
                    actor=_principal_from_request(),
                    fine_id=UUID(raw_fine_id),
                )
            elif raw_payment_id:
                allocs = fin_service.list_allocations_for_payment(
                    actor=_principal_from_request(),
                    payment_id=UUID(raw_payment_id),
                )
            else:
                raise ValueError(
                    "Either fine_id or payment_id is required to list allocations"
                )
            return jsonify({"items": [_allocation_dict(a) for a in allocs]})
        except Exception as err:
            return _handle_public_library_error(err)

    return bp
