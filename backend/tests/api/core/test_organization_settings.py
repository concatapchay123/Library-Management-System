"""Authorization and tenant ownership contracts for organization settings."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest

from openlibrary.app.config import AppConfig
from openlibrary.app.factory import create_app
from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.authorization import AuthorizationDenied
from openlibrary.modules.core.application.organization_settings import (
    OrganizationSettings,
    OrganizationSettingsService,
)


ORGANIZATION_ID = uuid4()
ACTOR = Principal(uuid4(), ORGANIZATION_ID, uuid4())


@dataclass
class _SettingsStore:
    values: dict[UUID, OrganizationSettings] = field(
        default_factory=lambda: {
            ORGANIZATION_ID: OrganizationSettings(
                timezone="UTC", settings={"theme": "light"}
            )
        }
    )

    def get(self, organization_id: UUID) -> OrganizationSettings:
        return self.values[organization_id]

    def update(
        self,
        organization_id: UUID,
        *,
        timezone: str,
        settings: dict[str, object],
        actor: Principal,
    ) -> OrganizationSettings:
        assert organization_id == actor.organization_id
        updated = OrganizationSettings(timezone=timezone, settings=settings)
        self.values[organization_id] = updated
        return updated


class _Authorizer:
    def __init__(self, allowed: set[str]) -> None:
        self.allowed = allowed

    def require(self, principal: Principal, permission: str) -> None:
        assert principal == ACTOR
        if permission not in self.allowed:
            raise AuthorizationDenied("denied")


class _AccessTokens:
    def verify(self, token: str) -> Principal:
        assert token == "verified-token"
        return ACTOR


def test_organization_settings_are_read_and_changed_only_in_the_principal_tenant() -> (
    None
):
    store = _SettingsStore()
    service = OrganizationSettingsService(
        store, _Authorizer({"organization.read", "organization.manage"})
    )

    assert service.get(actor=ACTOR).settings == {"theme": "light"}
    updated = service.update(
        actor=ACTOR, timezone="Asia/Bangkok", settings={"theme": "dark"}
    )

    assert updated == OrganizationSettings(
        timezone="Asia/Bangkok", settings={"theme": "dark"}
    )
    assert store.values[ORGANIZATION_ID] == updated


def test_organization_settings_require_the_named_manage_permission() -> None:
    service = OrganizationSettingsService(
        _SettingsStore(), _Authorizer({"organization.read"})
    )

    with pytest.raises(AuthorizationDenied):
        service.update(actor=ACTOR, timezone="UTC", settings={})


def test_settings_http_route_derives_its_tenant_from_the_verified_token() -> None:
    store = _SettingsStore()
    service = OrganizationSettingsService(
        store, _Authorizer({"organization.read", "organization.manage"})
    )
    app = create_app(
        AppConfig(
            readiness_probe=lambda: True,
            access_tokens=_AccessTokens(),  # type: ignore[arg-type]
            organization_settings=service,
        )
    )
    client = app.test_client()

    read = client.get(
        "/api/v1/organizations/settings",
        headers={"Authorization": "Bearer verified-token"},
    )
    changed = client.patch(
        "/api/v1/organizations/settings",
        headers={"Authorization": "Bearer verified-token"},
        json={"timezone": "Asia/Bangkok", "settings": {"theme": "dark"}},
    )

    assert read.get_json() == {"timezone": "UTC", "settings": {"theme": "light"}}
    assert changed.get_json() == {
        "timezone": "Asia/Bangkok",
        "settings": {"theme": "dark"},
    }
    assert store.values[ORGANIZATION_ID].timezone == "Asia/Bangkok"
