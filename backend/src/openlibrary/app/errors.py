"""RFC Problem Details responses for API failures."""

from http import HTTPStatus

from flask import Flask, Response, jsonify, request
from werkzeug.exceptions import HTTPException

from openlibrary.app.correlation import request_id
from openlibrary.modules.core.application.authorization import AuthorizationDenied


def install_problem_details_handlers(app: Flask) -> None:
    """Prevent framework HTML errors and implementation detail from escaping the API."""

    @app.errorhandler(AuthorizationDenied)
    def handle_authorization_denied(error: AuthorizationDenied) -> Response:
        del error
        return authorization_failure_response()

    @app.errorhandler(HTTPException)
    def handle_http_exception(error: HTTPException) -> Response:
        return _problem_response(
            status=error.code or HTTPStatus.INTERNAL_SERVER_ERROR,
            title=error.name,
            detail=_detail_for(error),
        )

    @app.errorhandler(Exception)
    def handle_unexpected_exception(error: Exception) -> Response:
        app.logger.exception("Unhandled request failure; request_id=%s", request_id())
        return _problem_response(
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
            title="Internal Server Error",
            detail="An unexpected error occurred.",
        )


def _detail_for(error: HTTPException) -> str:
    if error.code == HTTPStatus.NOT_FOUND:
        return "The requested resource was not found."
    return error.description or "An HTTP request error occurred."


def _problem_response(*, status: int | HTTPStatus, title: str, detail: str) -> Response:
    """Build one safe error representation for a failed API request."""
    response = jsonify(
        {
            "type": f"https://openlibraryos.example/problems/{_problem_type(status)}",
            "title": title,
            "status": int(status),
            "detail": detail,
            "instance": request.path,
            "request_id": request_id(),
        }
    )
    response.status_code = status
    response.mimetype = "application/problem+json"
    return response


def authentication_failure_response() -> Response:
    """Return the one non-enumerating public response for credential failures."""
    return _problem_response(
        status=HTTPStatus.UNAUTHORIZED,
        title="Authentication failed",
        detail="Authentication failed.",
    )


def authorization_failure_response() -> Response:
    """Return one stable response for an application-service permission denial."""
    return _problem_response(
        status=HTTPStatus.FORBIDDEN,
        title="Forbidden",
        detail="Authorization denied.",
    )


def _problem_type(status: int | HTTPStatus) -> str:
    """Derive a stable URL-safe type suffix from an HTTP status."""
    return HTTPStatus(status).phrase.lower().replace(" ", "-")
