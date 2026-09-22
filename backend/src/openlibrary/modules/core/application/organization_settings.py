"""Tenant-owned organization settings use case."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.authorization import AuthorizationPort


@dataclass(frozen=True, slots=True)
class OrganizationSettings:
    """The small mutable organization configuration exposed to tenant operators."""

    timezone: str
    settings: dict[str, object]


class OrganizationSettingsStore(Protocol):
    """Persistence port whose tenant key must come from the verified actor."""

    def get(self, organization_id: UUID) -> OrganizationSettings: ...

    def update(
        self,
        organization_id: UUID,
        *,
        timezone: str,
        settings: dict[str, object],
        actor: Principal,
    ) -> OrganizationSettings: ...


class OrganizationSettingsService:
    """Authorize settings access without accepting a client-selected tenant."""

    def __init__(
        self, store: OrganizationSettingsStore, authorizer: AuthorizationPort
    ) -> None:
        self._store = store
        self._authorizer = authorizer

    def get(self, *, actor: Principal) -> OrganizationSettings:
        self._authorizer.require(actor, "organization.read")
        return self._store.get(actor.organization_id)

    def update(
        self, *, actor: Principal, timezone: str, settings: dict[str, object]
    ) -> OrganizationSettings:
        self._authorizer.require(actor, "organization.manage")
        cleaned_timezone = timezone.strip()
        if not cleaned_timezone or len(cleaned_timezone) > 64:
            raise ValueError("Invalid organization timezone")
        return self._store.update(
            actor.organization_id,
            timezone=cleaned_timezone,
            settings=dict(settings),
            actor=actor,
        )
