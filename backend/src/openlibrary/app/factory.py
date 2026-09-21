"""Flask application factory."""

from flask import Flask

from openlibrary.app.config import AppConfig
from openlibrary.app.correlation import install_request_correlation
from openlibrary.app.errors import install_problem_details_handlers
from openlibrary.app.health import create_health_blueprint


def create_app(config: AppConfig) -> Flask:
    """Create a configured OpenLibraryOS application without external I/O."""
    app = Flask(__name__)
    install_request_correlation(app)
    install_problem_details_handlers(app)
    app.register_blueprint(create_health_blueprint(config.readiness_probe))
    return app
