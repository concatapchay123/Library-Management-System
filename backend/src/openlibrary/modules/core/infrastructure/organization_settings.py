"""SQL Server persistence for organization settings."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection

from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.organization_settings import (
    OrganizationSettings,
)
from openlibrary.modules.core.infrastructure.tenancy import SqlServerTenantContext
from openlibrary.modules.ops.application.persistence import AuditEvent
from openlibrary.modules.ops.infrastructure.sqlserver import SqlServerAuditedTransaction


class SqlServerOrganizationSettingsStore:
    """Use the tenant lifecycle for every settings query and mutation."""

    def __init__(self, tenant_context: SqlServerTenantContext) -> None:
        self._tenant_context = tenant_context
        self._writer = SqlServerAuditedTransaction()

    def get(self, organization_id: UUID) -> OrganizationSettings:
        with self._tenant_context.connection(organization_id) as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT timezone, settings_json FROM core.organizations "
                        "WHERE organization_id = :organization_id"
                    ),
                    {"organization_id": str(organization_id)},
                )
                .mappings()
                .one()
            )
        return OrganizationSettings(
            timezone=str(row["timezone"]),
            settings=_settings_object(row["settings_json"]),
        )

    def update(
        self,
        organization_id: UUID,
        *,
        timezone: str,
        settings: dict[str, object],
        actor: Principal,
    ) -> OrganizationSettings:
        serialized_settings = json.dumps(
            settings, separators=(",", ":"), sort_keys=True
        )
        with self._tenant_context.connection(organization_id) as connection:

            def mutation(active_connection: Connection) -> None:
                result = active_connection.execute(
                    text(
                        "UPDATE core.organizations SET timezone = :timezone, "
                        "settings_json = :settings_json, updated_at = SYSUTCDATETIME() "
                        "WHERE organization_id = :organization_id"
                    ),
                    {
                        "organization_id": str(organization_id),
                        "timezone": timezone,
                        "settings_json": serialized_settings,
                    },
                )
                if result.rowcount != 1:
                    raise LookupError("Organization settings not found")

            self._writer.run(
                connection,
                mutation,
                AuditEvent(
                    action="organization.settings_updated",
                    entity_type="organization",
                    entity_id=organization_id,
                    actor_user_id=actor.user_id,
                    actor_type="user",
                    payload={"timezone": timezone},
                    correlation_id=uuid4(),
                ),
                (),
            )
        return OrganizationSettings(timezone=timezone, settings=dict(settings))


def _settings_object(value: object) -> dict[str, object]:
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError as error:
        raise ValueError("Organization settings JSON is invalid") from error
    if not isinstance(parsed, dict):
        raise ValueError("Organization settings must be a JSON object")
    return {str(key): item for key, item in parsed.items()}
