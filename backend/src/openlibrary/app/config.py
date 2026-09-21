"""Configuration values supplied when the application is created."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openlibrary.modules.core.application.access_tokens import AccessTokenService
    from openlibrary.modules.core.application.login import LoginService
    from openlibrary.modules.core.application.refresh_sessions import (
        RefreshSessionService,
    )

ReadinessProbe = Callable[[], bool]


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Dependencies needed to create an application instance."""

    readiness_probe: ReadinessProbe
    login_service: "LoginService | None" = None
    access_tokens: "AccessTokenService | None" = None
    refresh_sessions: "RefreshSessionService | None" = None
