"""Deployment-only organization bootstrap adapter."""

from __future__ import annotations

from collections.abc import Callable
import json
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection


class PrivilegedOrganizationBootstrapper:
    """Create organizations only through the migration-granted stored procedure."""

    def __init__(self, connection_factory: Callable[[], Connection]) -> None:
        self._connection_factory = connection_factory

    def create(
        self,
        *,
        name: str,
        slug: str,
        organization_type: str,
        timezone: str,
        settings: dict[str, object],
    ) -> UUID:
        organization_id = uuid4()
        with self._connection_factory() as connection:
            connection.execute(
                text(
                    "EXEC core.bootstrap_organization "
                    "@organization_id=:organization_id, @name=:name, @slug=:slug, "
                    "@organization_type=:organization_type, @timezone=:timezone, "
                    "@settings_json=:settings_json, @correlation_id=:correlation_id"
                ),
                {
                    "organization_id": str(organization_id),
                    "name": _required(name, "name", 255),
                    "slug": _required(slug, "slug", 100),
                    "organization_type": _required(
                        organization_type, "organization type", 32
                    ),
                    "timezone": _required(timezone, "timezone", 64),
                    "settings_json": json.dumps(
                        settings, separators=(",", ":"), sort_keys=True
                    ),
                    "correlation_id": str(uuid4()),
                },
            )
            connection.commit()
        return organization_id


def _required(value: str, label: str, limit: int) -> str:
    cleaned = value.strip()
    if not cleaned or len(cleaned) > limit:
        raise ValueError(f"Invalid organization {label}")
    return cleaned
