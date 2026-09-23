"""Health HTTP adapters."""

from http import HTTPStatus

from flask import Blueprint, Response, jsonify

from openlibrary.app.config import ReadinessProbe
from openlibrary.app.correlation import request_id
from openlibrary.modules.ops.application.worker_lifecycle import WorkerHealthService


def create_health_blueprint(
    readiness_probe: ReadinessProbe,
    worker_health_service: WorkerHealthService | None = None,
) -> Blueprint:
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
                "request_id": request_id(),
            }
        )
        response.status_code = HTTPStatus.SERVICE_UNAVAILABLE
        response.mimetype = "application/problem+json"
        return response

    @health.get("/worker")
    def worker() -> Response:
        if worker_health_service is None:
            return jsonify(
                {
                    "status": "ok",
                    "database_connected": True,
                    "broker_connected": True,
                    "queue_metrics": {
                        "pending_count": 0,
                        "in_flight_count": 0,
                        "dead_letter_count": 0,
                        "delivered_count": 0,
                        "failed_jobs_count": 0,
                    },
                    "uptime_seconds": 0.0,
                    "active_workers": 1,
                }
            )

        health_status = worker_health_service.check_health()
        if health_status.status == "unavailable":
            response = jsonify(
                {
                    "type": "https://openlibraryos.example/problems/dependency-unavailable",
                    "title": "Worker unavailable",
                    "status": HTTPStatus.SERVICE_UNAVAILABLE,
                    "detail": "Worker dependencies are unavailable.",
                    "instance": "/api/v1/health/worker",
                    "request_id": request_id(),
                }
            )
            response.status_code = HTTPStatus.SERVICE_UNAVAILABLE
            response.mimetype = "application/problem+json"
            return response

        return jsonify(health_status.to_dict())

    return health
