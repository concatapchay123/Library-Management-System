"""SQL Server persistence adapter for opaque browser refresh sessions."""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from openlibrary.modules.core.application.refresh_sessions import RefreshSession
from openlibrary.modules.core.infrastructure.tenancy import SqlServerTenantContext


class SqlServerRefreshSessionStore:
    """Use a signed resolver before tenant context, then RLS-protected mutations."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._tenant_context: SqlServerTenantContext | None = None

    def create(self, session: RefreshSession) -> None:
        with self._tenant_connection(session.organization_id) as connection:
            connection.execute(
                text(
                    "INSERT INTO core.refresh_sessions "
                    "(session_id, organization_id, user_id, root_session_id, "
                    "parent_session_id, token_hash, csrf_hash, expires_at) VALUES "
                    "(:session_id, :organization_id, :user_id, :root_session_id, "
                    ":parent_session_id, :token_hash, :csrf_hash, :expires_at)"
                ),
                {
                    "session_id": str(session.session_id),
                    "organization_id": str(session.organization_id),
                    "user_id": str(session.user_id),
                    "root_session_id": str(session.root_session_id),
                    "parent_session_id": _uuid(session.parent_session_id),
                    "token_hash": session.token_hash,
                    "csrf_hash": session.csrf_hash,
                    "expires_at": session.expires_at,
                },
            )

    def resolve(self, token_hash: str) -> RefreshSession | None:
        with self._connection() as connection:
            row = (
                connection.execute(
                    text("EXEC core.resolve_refresh_session @token_hash = :token_hash"),
                    {"token_hash": token_hash},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return RefreshSession(
            session_id=UUID(str(row["session_id"])),
            root_session_id=UUID(str(row["root_session_id"])),
            parent_session_id=_uuid_value(row["parent_session_id"]),
            organization_id=UUID(str(row["organization_id"])),
            user_id=UUID(str(row["user_id"])),
            token_hash="",
            csrf_hash=str(row["csrf_hash"]),
            expires_at=_utc_datetime(row["expires_at"]),
            rotated_at=_optional_utc_datetime(row["rotated_at"]),
            revoked_at=_optional_utc_datetime(row["revoked_at"]),
        )

    def rotate(
        self, session: RefreshSession, replacement: RefreshSession, when: datetime
    ) -> bool:
        with self._tenant_connection(session.organization_id) as connection:
            result = connection.execute(
                text(
                    "UPDATE core.refresh_sessions SET rotated_at = :rotated_at "
                    "WHERE session_id = :session_id AND rotated_at IS NULL "
                    "AND revoked_at IS NULL"
                ),
                {"session_id": str(session.session_id), "rotated_at": when},
            )
            if result.rowcount != 1:
                return False
            connection.execute(
                text(
                    "INSERT INTO core.refresh_sessions "
                    "(session_id, organization_id, user_id, root_session_id, "
                    "parent_session_id, token_hash, csrf_hash, expires_at) VALUES "
                    "(:session_id, :organization_id, :user_id, :root_session_id, "
                    ":parent_session_id, :token_hash, :csrf_hash, :expires_at)"
                ),
                {
                    "session_id": str(replacement.session_id),
                    "organization_id": str(replacement.organization_id),
                    "user_id": str(replacement.user_id),
                    "root_session_id": str(replacement.root_session_id),
                    "parent_session_id": _uuid(replacement.parent_session_id),
                    "token_hash": replacement.token_hash,
                    "csrf_hash": replacement.csrf_hash,
                    "expires_at": replacement.expires_at,
                },
            )
            return True

    def revoke_chain(
        self, root_session_id: UUID, organization_id: UUID, when: datetime
    ) -> None:
        with self._tenant_connection(organization_id) as connection:
            connection.execute(
                text(
                    "UPDATE core.refresh_sessions SET revoked_at = :revoked_at "
                    "WHERE root_session_id = :root_session_id AND revoked_at IS NULL"
                ),
                {"root_session_id": str(root_session_id), "revoked_at": when},
            )

    def _tenant_connection(
        self, organization_id: UUID
    ) -> AbstractContextManager[Connection]:
        if self._tenant_context is None:
            self._tenant_context = SqlServerTenantContext(self._database_url)
        return self._tenant_context.connection(organization_id)

    def _connection(self) -> AbstractContextManager[Connection]:
        if self._tenant_context is None:
            self._tenant_context = SqlServerTenantContext(self._database_url)
        return self._tenant_context.raw_connection()


def _uuid(value: UUID | None) -> str | None:
    return None if value is None else str(value)


def _uuid_value(value: object) -> UUID | None:
    return None if value is None else UUID(str(value))


def _utc_datetime(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("SQL Server refresh-session timestamp is invalid")
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _optional_utc_datetime(value: object) -> datetime | None:
    return None if value is None else _utc_datetime(value)
