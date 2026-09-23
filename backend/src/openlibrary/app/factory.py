"""Flask application factory."""

from flask import Flask

from openlibrary.app.config import AppConfig
from openlibrary.app.correlation import install_request_correlation
from openlibrary.app.errors import install_problem_details_handlers
from openlibrary.app.health import create_health_blueprint
from openlibrary.modules.core.api.auth import create_auth_blueprint
from openlibrary.modules.core.api.books import create_books_blueprint
from openlibrary.modules.core.api.inventory import (
    create_book_copies_blueprint,
    create_copies_blueprint,
    create_locations_blueprint,
)
from openlibrary.modules.core.api.loans import create_loans_blueprint
from openlibrary.modules.core.api.organizations import create_organizations_blueprint
from openlibrary.modules.core.api.reservations import create_reservations_blueprint


def create_app(config: AppConfig) -> Flask:
    """Create a configured OpenLibraryOS application without external I/O."""
    app = Flask(__name__)
    install_request_correlation(app)
    install_problem_details_handlers(app)
    app.register_blueprint(create_health_blueprint(config.readiness_probe))
    if config.login_service is not None:
        if config.access_tokens is None or config.refresh_sessions is None:
            raise ValueError(
                "Login routes require access token and refresh token issuance"
            )
        app.register_blueprint(
            create_auth_blueprint(
                config.login_service,
                config.access_tokens,
                config.refresh_sessions,
                config.authorization,
                config.tenant_request_context,
            )
        )
    if config.organization_settings is not None:
        if config.access_tokens is None:
            raise ValueError(
                "Organization settings routes require access token verification"
            )
        app.register_blueprint(
            create_organizations_blueprint(
                config.organization_settings,
                config.access_tokens,
                config.tenant_request_context,
            )
        )
    if config.book_catalog is not None:
        if config.access_tokens is None:
            raise ValueError("Book catalog routes require access token verification")
        app.register_blueprint(
            create_books_blueprint(
                config.book_catalog,
                config.access_tokens,
                config.tenant_request_context,
            )
        )
    if config.inventory is not None:
        if config.access_tokens is None:
            raise ValueError("Inventory routes require access token verification")
        app.register_blueprint(
            create_locations_blueprint(
                config.inventory,
                config.access_tokens,
                config.tenant_request_context,
            )
        )
        app.register_blueprint(
            create_book_copies_blueprint(
                config.inventory,
                config.access_tokens,
                config.tenant_request_context,
                copy_status=config.copy_status,
            )
        )
        app.register_blueprint(
            create_copies_blueprint(
                config.inventory,
                config.access_tokens,
                config.tenant_request_context,
                copy_status=config.copy_status,
            )
        )
    if config.loan_service is not None:
        if config.access_tokens is None:
            raise ValueError(
                "Circulation loan routes require access token verification"
            )
        app.register_blueprint(
            create_loans_blueprint(
                config.loan_service,
                config.access_tokens,
                config.tenant_request_context,
                idempotency=config.idempotency_service,
            )
        )
    if config.reservation_service is not None:
        if config.access_tokens is None:
            raise ValueError("Reservation routes require access token verification")
        app.register_blueprint(
            create_reservations_blueprint(
                config.reservation_service,
                config.access_tokens,
                config.tenant_request_context,
            )
        )
    return app
