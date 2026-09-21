"""Create opaque refresh sessions and their narrowly scoped pre-auth resolver.

Revision ID: 0005_refresh_sessions
Revises: 0004_users_profiles
Create Date: 2026-09-21
"""

from alembic import context, op


revision = "0005_refresh_sessions"
down_revision = "0004_users_profiles"
branch_labels = None
depends_on = None


def _add_tenant_predicates(table_name: str) -> None:
    """Apply the shared filter plus all SQL Server block-predicate operations."""
    op.execute(
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "ADD FILTER PREDICATE core.tenant_access_predicate(organization_id) "
        f"ON {table_name}"
    )
    for operation in ("AFTER INSERT", "AFTER UPDATE", "BEFORE DELETE"):
        op.execute(
            "ALTER SECURITY POLICY core.organization_tenant_policy "
            "ADD BLOCK PREDICATE core.tenant_access_predicate(organization_id) "
            f"ON {table_name} {operation}"
        )


def _drop_tenant_predicates(table_name: str) -> None:
    """Remove every predicate before removing its tenant-owned table."""
    op.execute(
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        f"DROP FILTER PREDICATE ON {table_name}"
    )
    for operation in ("AFTER INSERT", "AFTER UPDATE", "BEFORE DELETE"):
        op.execute(
            "ALTER SECURITY POLICY core.organization_tenant_policy "
            f"DROP BLOCK PREDICATE ON {table_name} {operation}"
        )


def upgrade() -> None:
    """Persist only token/CSRF hashes and expose an owner-executing resolver."""
    runtime_login = context.config.attributes["runtime_login"]
    op.execute(
        "CREATE TABLE core.refresh_sessions ("
        "session_id uniqueidentifier NOT NULL "
        "CONSTRAINT PK_core_refresh_sessions PRIMARY KEY, "
        "organization_id uniqueidentifier NOT NULL, "
        "user_id uniqueidentifier NOT NULL, "
        "root_session_id uniqueidentifier NOT NULL, "
        "parent_session_id uniqueidentifier NULL, "
        "token_hash char(64) NOT NULL, "
        "csrf_hash char(64) NOT NULL, "
        "expires_at datetime2(3) NOT NULL, "
        "rotated_at datetime2(3) NULL, "
        "revoked_at datetime2(3) NULL, "
        "created_at datetime2(3) NOT NULL "
        "CONSTRAINT DF_core_refresh_sessions_created_at DEFAULT SYSUTCDATETIME(), "
        "CONSTRAINT UQ_core_refresh_sessions_organization_session "
        "UNIQUE (organization_id, session_id), "
        "CONSTRAINT FK_core_refresh_sessions_user FOREIGN KEY "
        "(organization_id, user_id) REFERENCES core.users (organization_id, user_id), "
        "CONSTRAINT FK_core_refresh_sessions_root FOREIGN KEY "
        "(organization_id, root_session_id) REFERENCES core.refresh_sessions "
        "(organization_id, session_id), "
        "CONSTRAINT FK_core_refresh_sessions_parent FOREIGN KEY "
        "(organization_id, parent_session_id) REFERENCES core.refresh_sessions "
        "(organization_id, session_id)"
        ")"
    )
    op.execute(
        "CREATE UNIQUE INDEX IX_core_refresh_sessions_token_hash "
        "ON core.refresh_sessions (token_hash)"
    )
    op.execute(
        "CREATE INDEX IX_core_refresh_sessions_organization_root "
        "ON core.refresh_sessions (organization_id, root_session_id)"
    )
    _add_tenant_predicates("core.refresh_sessions")
    op.execute(
        "CREATE PROCEDURE core.resolve_refresh_session @token_hash char(64) "
        "WITH EXECUTE AS OWNER "
        "AS BEGIN SET NOCOUNT ON; "
        "SELECT session_id, organization_id, user_id, root_session_id, "
        "parent_session_id, csrf_hash, expires_at, rotated_at, revoked_at "
        "FROM core.refresh_sessions "
        "WHERE token_hash = @token_hash AND revoked_at IS NULL "
        "AND expires_at > SYSUTCDATETIME(); END"
    )
    op.execute(
        "ADD SIGNATURE TO OBJECT::core.resolve_refresh_session "
        "BY CERTIFICATE core_login_resolver_certificate"
    )
    op.execute(
        f"GRANT EXECUTE ON OBJECT::core.resolve_refresh_session TO [{runtime_login}]"
    )


def downgrade() -> None:
    """Remove resolver, policy predicates, and session table in dependency order."""
    op.execute(
        "DROP SIGNATURE FROM OBJECT::core.resolve_refresh_session "
        "BY CERTIFICATE core_login_resolver_certificate"
    )
    op.execute("DROP PROCEDURE core.resolve_refresh_session")
    _drop_tenant_predicates("core.refresh_sessions")
    op.execute("DROP TABLE core.refresh_sessions")
