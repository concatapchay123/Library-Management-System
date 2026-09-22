"""Configuration values supplied when the application is created."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openlibrary.modules.core.application.access_tokens import AccessTokenService
    from openlibrary.modules.core.application.authorization import AuthorizationService
    from openlibrary.modules.core.application.books import BookCatalogService
    from openlibrary.modules.core.application.login import LoginService
    from openlibrary.modules.core.application.organization_settings import (
        OrganizationSettingsService,
    )
    from openlibrary.modules.core.application.refresh_sessions import (
        RefreshSessionService,
    )
    from openlibrary.modules.core.infrastructure.tenancy import TenantRequestContext

ReadinessProbe = Callable[[], bool]


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Dependencies needed to create an application instance."""

    readiness_probe: ReadinessProbe
    login_service: "LoginService | None" = None
    access_tokens: "AccessTokenService | None" = None
    refresh_sessions: "RefreshSessionService | None" = None
    authorization: "AuthorizationService | None" = None
    organization_settings: "OrganizationSettingsService | None" = None
    book_catalog: "BookCatalogService | None" = None
    tenant_request_context: "TenantRequestContext | None" = None
