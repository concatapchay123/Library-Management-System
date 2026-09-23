"""Protected HTTP adapters for the circulation loan lifecycle."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from flask import Blueprint, Response, jsonify, request

from openlibrary.app.correlation import request_id
from openlibrary.modules.core.api.auth import (
    _principal_from_request,
    _require_principal,
)
from openlibrary.modules.core.application.access_tokens import AccessTokenService
from openlibrary.modules.core.application.loans import Loan, LoanService
from openlibrary.modules.core.domain.copy_status import InvalidCopyStatusTransitionError
from openlibrary.modules.core.domain.loans import (
    ActiveLoanLimitExceededError,
    BorrowerNotEligibleError,
    CopyNotAvailableForLoanError,
    InvalidLoanStatusTransitionError,
    LoanNotFoundError,
)
from openlibrary.modules.core.infrastructure.tenancy import TenantRequestContext
from openlibrary.modules.ops.application.idempotency import (
    IdempotencyConflictError,
    IdempotencyService,
)


def create_loans_blueprint(
    service: LoanService,
    access_tokens: AccessTokenService,
    tenant_request_context: TenantRequestContext | None = None,
    idempotency: IdempotencyService | None = None,
) -> Blueprint:
    """Expose circulation loan endpoints without accepting client-selected tenants."""
    loans = Blueprint("loans", __name__, url_prefix="/api/v1/loans")

    def _execute_idempotent(
        payload: object,
        execute_fn: Callable[[], tuple[int, Loan]],
    ) -> Response:
        idempotency_key = request.headers.get("Idempotency-Key")
        actor = _principal_from_request()
        corr_id = None
        if request_id():
            try:
                corr_id = UUID(request_id())
            except ValueError:
                pass

        if idempotency_key is not None:
            clean_key = idempotency_key.strip()
            if not clean_key or len(clean_key) > 128:
                return _bad_request(
                    "Idempotency-Key header must be between 1 and 128 characters."
                )

            if idempotency is not None:

                def _do_execute() -> tuple[int, dict[str, Any], str | None]:
                    status_code, loan = execute_fn()
                    return status_code, _loan_response(loan), str(loan.loan_id)

                try:
                    res = idempotency.process_or_replay(
                        organization_id=actor.organization_id,
                        key=clean_key,
                        method=request.method,
                        endpoint=request.path,
                        request_payload=payload,
                        execute=_do_execute,
                        correlation_id=corr_id,
                        actor_user_id=actor.user_id,
                    )
                except IdempotencyConflictError as err:
                    return _problem_response(
                        err.status_code, err.title, str(err), type_uri=err.problem_type
                    )

                response = jsonify(res.body)
                response.status_code = res.status_code
                if res.replayed:
                    response.headers["Idempotency-Replayed"] = "true"
                return response

        status_code, loan = execute_fn()
        response = jsonify(_loan_response(loan))
        response.status_code = status_code
        return response

    @loans.post("")
    @_require_principal(access_tokens, tenant_request_context)
    def request_loan() -> Response:
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return _bad_request("Invalid JSON payload.")

        copy_id_raw = payload.get("copy_id")
        if not copy_id_raw:
            return _bad_request("copy_id is required.")
        try:
            copy_uuid = UUID(str(copy_id_raw))
        except ValueError:
            return _bad_request("Invalid copy_id UUID format.")

        borrower_user_id: UUID | None = None
        borrower_raw = payload.get("borrower_user_id")
        if borrower_raw:
            try:
                borrower_user_id = UUID(str(borrower_raw))
            except ValueError:
                return _bad_request("Invalid borrower_user_id UUID format.")

        duration_days: int | None = None
        duration_raw = payload.get("duration_days")
        if duration_raw is not None:
            try:
                duration_days = int(duration_raw)
            except (ValueError, TypeError):
                return _bad_request("duration_days must be an integer.")

        corr_id = None
        if request_id():
            try:
                corr_id = UUID(request_id())
            except ValueError:
                pass

        try:
            return _execute_idempotent(
                payload,
                lambda: (
                    201,
                    service.request_loan(
                        actor=_principal_from_request(),
                        copy_id=copy_uuid,
                        borrower_user_id=borrower_user_id,
                        duration_days=duration_days,
                        correlation_id=corr_id,
                    ),
                ),
            )
        except InvalidLoanStatusTransitionError as err:
            return _problem_response(
                err.status_code, err.title, str(err), type_uri=err.problem_type
            )
        except CopyNotAvailableForLoanError as err:
            return _problem_response(
                err.status_code, err.title, str(err), type_uri=err.problem_type
            )
        except ActiveLoanLimitExceededError as err:
            return _problem_response(
                err.status_code, err.title, str(err), type_uri=err.problem_type
            )
        except BorrowerNotEligibleError as err:
            return _problem_response(
                err.status_code, err.title, str(err), type_uri=err.problem_type
            )
        except (KeyError, LoanNotFoundError):
            return _not_found("Copy or borrower not found.")
        except ValueError as err:
            return _bad_request(str(err))

    @loans.post("/desk-checkout")
    @_require_principal(access_tokens, tenant_request_context)
    def desk_checkout() -> Response:
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return _bad_request("Invalid JSON payload.")

        copy_id_raw = payload.get("copy_id")
        borrower_raw = payload.get("borrower_user_id")
        if not copy_id_raw or not borrower_raw:
            return _bad_request("copy_id and borrower_user_id are required.")

        try:
            copy_uuid = UUID(str(copy_id_raw))
            borrower_uuid = UUID(str(borrower_raw))
        except ValueError:
            return _bad_request("Invalid UUID format for copy_id or borrower_user_id.")

        duration_days: int | None = None
        duration_raw = payload.get("duration_days")
        if duration_raw is not None:
            try:
                duration_days = int(duration_raw)
            except (ValueError, TypeError):
                return _bad_request("duration_days must be an integer.")

        corr_id = None
        if request_id():
            try:
                corr_id = UUID(request_id())
            except ValueError:
                pass

        try:
            return _execute_idempotent(
                payload,
                lambda: (
                    201,
                    service.desk_checkout(
                        actor=_principal_from_request(),
                        copy_id=copy_uuid,
                        borrower_user_id=borrower_uuid,
                        duration_days=duration_days,
                        correlation_id=corr_id,
                    ),
                ),
            )
        except InvalidLoanStatusTransitionError as err:
            return _problem_response(
                err.status_code, err.title, str(err), type_uri=err.problem_type
            )
        except CopyNotAvailableForLoanError as err:
            return _problem_response(
                err.status_code, err.title, str(err), type_uri=err.problem_type
            )
        except InvalidCopyStatusTransitionError as err:
            return _problem_response(
                err.status_code, err.title, str(err), type_uri=err.problem_type
            )
        except ActiveLoanLimitExceededError as err:
            return _problem_response(
                err.status_code, err.title, str(err), type_uri=err.problem_type
            )
        except BorrowerNotEligibleError as err:
            return _problem_response(
                err.status_code, err.title, str(err), type_uri=err.problem_type
            )
        except (KeyError, LoanNotFoundError):
            return _not_found("Copy or borrower not found.")
        except ValueError as err:
            return _bad_request(str(err))

    @loans.get("")
    @_require_principal(access_tokens, tenant_request_context)
    def list_loans() -> Response:
        borrower_raw = request.args.get("borrower_user_id")
        copy_raw = request.args.get("copy_id")
        status = request.args.get("status")

        borrower_uuid: UUID | None = None
        if borrower_raw:
            try:
                borrower_uuid = UUID(borrower_raw)
            except ValueError:
                return _bad_request("Invalid borrower_user_id UUID format.")

        copy_uuid: UUID | None = None
        if copy_raw:
            try:
                copy_uuid = UUID(copy_raw)
            except ValueError:
                return _bad_request("Invalid copy_id UUID format.")

        items = service.list_loans(
            actor=_principal_from_request(),
            borrower_user_id=borrower_uuid,
            copy_id=copy_uuid,
            status=status,
        )
        return jsonify({"items": [_loan_response(loan) for loan in items]})

    @loans.get("/<loan_id>")
    @_require_principal(access_tokens, tenant_request_context)
    def get_loan(loan_id: str) -> Response:
        try:
            loan_uuid = UUID(loan_id)
        except ValueError:
            return _bad_request("Invalid loan_id UUID format.")

        try:
            loan = service.get_loan(
                actor=_principal_from_request(),
                loan_id=loan_uuid,
            )
        except (KeyError, LoanNotFoundError):
            return _not_found("Loan not found.")

        return jsonify(_loan_response(loan))

    @loans.post("/<loan_id>/approve")
    @_require_principal(access_tokens, tenant_request_context)
    def approve_loan(loan_id: str) -> Response:
        try:
            loan_uuid = UUID(loan_id)
        except ValueError:
            return _bad_request("Invalid loan_id UUID format.")

        corr_id = None
        if request_id():
            try:
                corr_id = UUID(request_id())
            except ValueError:
                pass

        try:
            loan = service.approve_loan(
                actor=_principal_from_request(),
                loan_id=loan_uuid,
                correlation_id=corr_id,
            )
        except InvalidLoanStatusTransitionError as err:
            return _problem_response(
                err.status_code, err.title, str(err), type_uri=err.problem_type
            )
        except (KeyError, LoanNotFoundError):
            return _not_found("Loan not found.")
        except ValueError as err:
            return _bad_request(str(err))

        return jsonify(_loan_response(loan))

    @loans.post("/<loan_id>/reject")
    @_require_principal(access_tokens, tenant_request_context)
    def reject_loan(loan_id: str) -> Response:
        try:
            loan_uuid = UUID(loan_id)
        except ValueError:
            return _bad_request("Invalid loan_id UUID format.")

        payload = request.get_json(silent=True) or {}
        reason = payload.get("reason", "") if isinstance(payload, dict) else ""

        corr_id = None
        if request_id():
            try:
                corr_id = UUID(request_id())
            except ValueError:
                pass

        try:
            loan = service.reject_loan(
                actor=_principal_from_request(),
                loan_id=loan_uuid,
                reason=str(reason),
                correlation_id=corr_id,
            )
        except InvalidLoanStatusTransitionError as err:
            return _problem_response(
                err.status_code, err.title, str(err), type_uri=err.problem_type
            )
        except (KeyError, LoanNotFoundError):
            return _not_found("Loan not found.")
        except ValueError as err:
            return _bad_request(str(err))

        return jsonify(_loan_response(loan))

    @loans.post("/<loan_id>/checkout")
    @_require_principal(access_tokens, tenant_request_context)
    def checkout_loan(loan_id: str) -> Response:
        try:
            loan_uuid = UUID(loan_id)
        except ValueError:
            return _bad_request("Invalid loan_id UUID format.")

        payload = request.get_json(silent=True) or {}
        duration_days: int | None = None
        if isinstance(payload, dict) and payload.get("duration_days") is not None:
            try:
                duration_days = int(payload["duration_days"])
            except (ValueError, TypeError):
                return _bad_request("duration_days must be an integer.")

        corr_id = None
        if request_id():
            try:
                corr_id = UUID(request_id())
            except ValueError:
                pass

        try:
            return _execute_idempotent(
                payload,
                lambda: (
                    200,
                    service.checkout_loan(
                        actor=_principal_from_request(),
                        loan_id=loan_uuid,
                        duration_days=duration_days,
                        correlation_id=corr_id,
                    ),
                ),
            )
        except InvalidLoanStatusTransitionError as err:
            return _problem_response(
                err.status_code, err.title, str(err), type_uri=err.problem_type
            )
        except CopyNotAvailableForLoanError as err:
            return _problem_response(
                err.status_code, err.title, str(err), type_uri=err.problem_type
            )
        except InvalidCopyStatusTransitionError as err:
            return _problem_response(
                err.status_code, err.title, str(err), type_uri=err.problem_type
            )
        except (KeyError, LoanNotFoundError):
            return _not_found("Loan or copy not found.")
        except ValueError as err:
            return _bad_request(str(err))

    @loans.post("/<loan_id>/return")
    @_require_principal(access_tokens, tenant_request_context)
    def return_loan(loan_id: str) -> Response:
        try:
            loan_uuid = UUID(loan_id)
        except ValueError:
            return _bad_request("Invalid loan_id UUID format.")

        corr_id = None
        if request_id():
            try:
                corr_id = UUID(request_id())
            except ValueError:
                pass

        try:
            return _execute_idempotent(
                {},
                lambda: (
                    200,
                    service.return_loan(
                        actor=_principal_from_request(),
                        loan_id=loan_uuid,
                        correlation_id=corr_id,
                    ),
                ),
            )
        except InvalidLoanStatusTransitionError as err:
            return _problem_response(
                err.status_code, err.title, str(err), type_uri=err.problem_type
            )
        except InvalidCopyStatusTransitionError as err:
            return _problem_response(
                err.status_code, err.title, str(err), type_uri=err.problem_type
            )
        except (KeyError, LoanNotFoundError):
            return _not_found("Loan or copy not found.")
        except ValueError as err:
            return _bad_request(str(err))

    return loans


def _loan_response(loan: Loan) -> dict[str, Any]:
    return {
        "loan_id": str(loan.loan_id),
        "organization_id": str(loan.organization_id),
        "copy_id": str(loan.copy_id),
        "borrower_user_id": str(loan.borrower_user_id),
        "status": loan.status,
        "loan_status": loan.loan_status,
        "request_status": loan.request_status,
        "requested_at": loan.requested_at.isoformat(),
        "approved_at": loan.approved_at.isoformat() if loan.approved_at else None,
        "checked_out_at": loan.checked_out_at.isoformat()
        if loan.checked_out_at
        else None,
        "due_at": loan.due_at.isoformat() if loan.due_at else None,
        "returned_at": loan.returned_at.isoformat() if loan.returned_at else None,
        "policy_snapshot": dict(loan.policy_snapshot),
        "created_at": loan.created_at.isoformat(),
        "updated_at": loan.updated_at.isoformat(),
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


def _conflict(detail: str = "Resource conflict.") -> Response:
    return _problem_response(409, "Conflict", detail)
