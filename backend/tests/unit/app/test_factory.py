from openlibrary.app.config import AppConfig
from openlibrary.app.factory import create_app


def test_factory_exposes_live_health_without_using_readiness_probe() -> None:
    def unavailable() -> bool:
        raise AssertionError("liveness must not call the readiness probe")

    app = create_app(AppConfig(readiness_probe=unavailable))

    response = app.test_client().get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_readiness_returns_problem_details_when_dependency_is_unavailable() -> None:
    app = create_app(AppConfig(readiness_probe=lambda: False))

    response = app.test_client().get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.content_type == "application/problem+json"
    assert response.get_json() == {
        "type": "https://openlibraryos.example/problems/dependency-unavailable",
        "title": "Service unavailable",
        "status": 503,
        "detail": "A required dependency is unavailable.",
        "instance": "/api/v1/health/ready",
    }


def test_readiness_returns_ok_when_dependencies_are_available() -> None:
    app = create_app(AppConfig(readiness_probe=lambda: True))

    response = app.test_client().get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
