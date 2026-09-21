"""Request-correlation and RFC Problem Details behavior."""

from uuid import UUID

from openlibrary.app.config import AppConfig
from openlibrary.app.errors import _detail_for
from openlibrary.app.factory import create_app
from werkzeug.exceptions import BadRequest


def test_valid_client_request_id_is_reused_for_problem_details() -> None:
    """Removing correlation propagation must break client-visible error tracing."""
    app = create_app(AppConfig(readiness_probe=lambda: False))

    response = app.test_client().get(
        "/api/v1/health/ready", headers={"X-Request-ID": "gateway-42"}
    )

    assert response.status_code == 503
    assert response.headers["X-Request-ID"] == "gateway-42"
    assert response.get_json()["request_id"] == "gateway-42"


def test_invalid_client_request_id_is_replaced_before_a_problem_response() -> None:
    """Invalid header values must not cross the request-correlation boundary."""
    app = create_app(AppConfig(readiness_probe=lambda: False))

    response = app.test_client().get(
        "/api/v1/health/ready", headers={"X-Request-ID": "invalid value"}
    )

    request_id = response.headers["X-Request-ID"]
    assert UUID(request_id)
    assert response.get_json()["request_id"] == request_id


def test_missing_route_returns_problem_details_with_a_request_id() -> None:
    """Removing the HTTP error handler must not restore Flask's HTML error page."""
    app = create_app(AppConfig(readiness_probe=lambda: True))

    response = app.test_client().get("/api/v1/missing")

    assert response.status_code == 404
    assert response.mimetype == "application/problem+json"
    assert response.get_json() == {
        "type": "https://openlibraryos.example/problems/not-found",
        "title": "Not Found",
        "status": 404,
        "detail": "The requested resource was not found.",
        "instance": "/api/v1/missing",
        "request_id": response.headers["X-Request-ID"],
    }


def test_http_exception_without_a_description_has_a_safe_problem_detail() -> None:
    """A nullable framework description must not escape the Problem Details boundary."""
    error = BadRequest()
    error.description = None

    assert _detail_for(error) == "An HTTP request error occurred."
