"""Health HTTP adapters."""

from http import HTTPStatus

from flask import Blueprint, Response, jsonify

from openlibrary.app.config import ReadinessProbe


def create_health_blueprint(readiness_probe: ReadinessProbe) -> Blueprint:
    """Create health routes that defer dependency checks to injected code."""
    health = Blueprint("health", __name__, url_prefix="/api/v1/health")

    @health.get("/live")
    def live() -> Response:
        return jsonify({"status": "ok"})

    @health.get("/ready")
    def ready() -> Response:
        if readiness_probe():
            return jsonify({"status": "ok"})

        response = jsonify(
            {
                "type": "https://openlibraryos.example/problems/dependency-unavailable",
                "title": "Service unavailable",
                "status": HTTPStatus.SERVICE_UNAVAILABLE,
                "detail": "A required dependency is unavailable.",
                "instance": "/api/v1/health/ready",
            }
        )
        response.status_code = HTTPStatus.SERVICE_UNAVAILABLE
        response.mimetype = "application/problem+json"
        return response

    return health
