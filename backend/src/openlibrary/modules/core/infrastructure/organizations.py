"""Narrow SQL Server boundary for organization tenant resolution."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection


@dataclass(frozen=True, slots=True)
class LoginTenant:
    """Minimal organization data required before credential verification."""

    organization_id: UUID
    slug: str
    status: str


def resolve_login_tenant(connection: Connection, slug: str) -> LoginTenant | None:
    """Resolve a login slug only through the owner-executing SQL procedure."""
    row = (
        connection.execute(
            text("EXEC core.resolve_login_tenant @slug = :slug"), {"slug": slug}
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return None
    return LoginTenant(
        organization_id=UUID(str(row["organization_id"])),
        slug=str(row["slug"]),
        status=str(row["status"]),
    )


def set_tenant_context(connection: Connection, organization_id: UUID) -> None:
    """Set one server-derived tenant ID for the current SQL connection."""
    connection.execute(
        text(
            "EXEC sys.sp_set_session_context "
            "@key=N'organization_id', @value=:organization_id, @read_only=0"
        ),
        {"organization_id": str(organization_id)},
    )


def clear_tenant_context(connection: Connection) -> None:
    """Clear tenant state before the connection can return to a pool."""
    connection.execute(
        text("EXEC sys.sp_set_session_context @key=N'organization_id', @value=NULL")
    )
