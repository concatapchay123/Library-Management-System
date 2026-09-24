"""SQL Server adapters for the BE-007 login application service."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from openlibrary.modules.core.application.login import (
    LoginService,
    UserCredentials,
)
from openlibrary.modules.core.domain.passwords import PasswordService
from openlibrary.modules.core.infrastructure.organizations import (
    clear_tenant_context,
    resolve_login_tenant,
    set_tenant_context,
)
from openlibrary.modules.ops.infrastructure.sqlserver import SqlServerAuditedTransaction


class SqlServerUserCredentialsRepository:
    """Parameterized credential operations after server-derived tenant selection."""

    def find_by_email(
        self, connection: Connection, *, organization_id: UUID, email: str
    ) -> UserCredentials | None:
        """Return a user only within the resolved tenant and active RLS context."""
        row = (
            connection.execute(
                text(
                    "SELECT user_id, password_hash, status FROM core.users "
                    "WHERE organization_id = :organization_id AND email = :email"
                ),
                {"organization_id": str(organization_id), "email": email},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        return UserCredentials(
            user_id=UUID(str(row["user_id"])),
            password_hash=str(row["password_hash"]),
            status=str(row["status"]),
        )

    def find_by_id(
        self, connection: Connection, *, organization_id: UUID, user_id: UUID
    ) -> UserCredentials | None:
        """Return a user only within the resolved tenant and active RLS context."""
        row = (
            connection.execute(
                text(
                    "SELECT user_id, password_hash, status FROM core.users "
                    "WHERE organization_id = :organization_id AND user_id = :user_id"
                ),
                {"organization_id": str(organization_id), "user_id": str(user_id)},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        return UserCredentials(
            user_id=UUID(str(row["user_id"])),
            password_hash=str(row["password_hash"]),
            status=str(row["status"]),
        )

    def update_password(
        self,
        connection: Connection,
        *,
        organization_id: UUID,
        user_id: UUID,
        password_hash: str,
    ) -> None:
        """Update password hash for a user within tenant context."""
        connection.execute(
            text(
                "UPDATE core.users SET password_hash = :password_hash, "
                "updated_at = SYSUTCDATETIME() "
                "WHERE organization_id = :organization_id AND user_id = :user_id"
            ),
            {
                "organization_id": str(organization_id),
                "user_id": str(user_id),
                "password_hash": password_hash,
            },
        )

    def update_last_login(self, connection: Connection, *, user_id: UUID) -> None:
        """Update only the successful user's server timestamp inside the audit transaction."""
        connection.execute(
            text(
                "UPDATE core.users SET last_login_at = SYSUTCDATETIME(), "
                "updated_at = SYSUTCDATETIME() WHERE user_id = :user_id"
            ),
            {"user_id": str(user_id)},
        )


class SqlServerPreloginSecurityAudit:
    """Procedure-only writer for a failure that has no tenant identity."""

    def record_unknown_tenant_failure(
        self, connection: Connection, *, correlation_id: UUID
    ) -> None:
        """Call the owner-executing procedure with no credential or identity input."""
        connection.execute(
            text(
                "EXEC ops.record_prelogin_security_event "
                "@event_id = :event_id, @correlation_id = :correlation_id"
            ),
            {"event_id": str(uuid4()), "correlation_id": str(correlation_id)},
        )


def create_sqlserver_login_service(database_url: str) -> LoginService:
    """Wire runtime-only SQL Server dependencies for public credential validation."""
    engine: Engine | None = None

    def connection_factory() -> Connection:
        nonlocal engine
        if engine is None:
            engine = create_engine(database_url)
        return engine.connect()

    password_service = PasswordService()
    return LoginService(
        connection_factory=connection_factory,
        tenant_resolver=resolve_login_tenant,
        set_tenant_context=set_tenant_context,
        clear_tenant_context=clear_tenant_context,
        user_credentials=SqlServerUserCredentialsRepository(),
        password_service=password_service,
        dummy_password_hash=password_service.hash("openlibraryos-login-dummy"),
        audited_transaction=SqlServerAuditedTransaction(),
        prelogin_security_audit=SqlServerPreloginSecurityAudit(),
    )
