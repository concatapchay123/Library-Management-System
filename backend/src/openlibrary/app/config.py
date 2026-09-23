"""Configuration values supplied when the application is created."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openlibrary.modules.core.application.access_tokens import AccessTokenService
    from openlibrary.modules.core.application.authorization import AuthorizationService
    from openlibrary.modules.core.application.books import BookCatalogService
    from openlibrary.modules.core.application.copy_status import CopyStatusService
    from openlibrary.modules.core.application.inventory import InventoryService
    from openlibrary.modules.core.application.loans import LoanService
    from openlibrary.modules.core.application.login import LoginService
    from openlibrary.modules.core.application.notifications import NotificationService
    from openlibrary.modules.core.application.organization_settings import (
        OrganizationSettingsService,
    )
    from openlibrary.modules.core.application.refresh_sessions import (
        RefreshSessionService,
    )
    from openlibrary.modules.core.application.reservations import ReservationService
    from openlibrary.modules.core.infrastructure.tenancy import TenantRequestContext
    from openlibrary.modules.education.application import EducationService
    from openlibrary.modules.ops.application.idempotency import IdempotencyService
    from openlibrary.modules.ops.application.worker_lifecycle import WorkerHealthService
    from openlibrary.modules.public_library.application import (
        PublicLibraryFinanceService,
        PublicLibraryService,
    )

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
    inventory: "InventoryService | None" = None
    copy_status: "CopyStatusService | None" = None
    loan_service: "LoanService | None" = None
    reservation_service: "ReservationService | None" = None
    notification_service: "NotificationService | None" = None
    idempotency_service: "IdempotencyService | None" = None
    education_service: "EducationService | None" = None
    public_library_service: "PublicLibraryService | None" = None
    public_library_finance_service: "PublicLibraryFinanceService | None" = None
    tenant_request_context: "TenantRequestContext | None" = None
    worker_health_service: "WorkerHealthService | None" = None
