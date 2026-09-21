"""Create tenant-protected user credentials and pre-login security evidence.

Revision ID: 0004_users_profiles
Revises: 0003_audit_outbox
Create Date: 2026-09-21
"""

from alembic import context, op


revision = "0004_users_profiles"
down_revision = "0003_audit_outbox"
branch_labels = None
depends_on = None


def _add_tenant_predicates(table_name: str) -> None:
    """Protect one tenant-owned table through the shared fail-closed policy."""
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
    """Remove all predicates before dropping a tenant-owned table."""
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
    """Add credentials, profiles, and audit evidence for unknown-tenant failures."""
    runtime_login = context.config.attributes["runtime_login"]
    op.execute(
        "CREATE TABLE core.users ("
        "user_id uniqueidentifier NOT NULL "
        "CONSTRAINT PK_core_users PRIMARY KEY, "
        "organization_id uniqueidentifier NOT NULL, "
        "email nvarchar(320) NOT NULL, "
        "password_hash varchar(512) NOT NULL, "
        "status varchar(32) NOT NULL "
        "CONSTRAINT CK_core_users_status CHECK (status IN ('active', 'disabled')), "
        "last_login_at datetime2(3) NULL, "
        "created_at datetime2(3) NOT NULL "
        "CONSTRAINT DF_core_users_created_at DEFAULT SYSUTCDATETIME(), "
        "updated_at datetime2(3) NOT NULL "
        "CONSTRAINT DF_core_users_updated_at DEFAULT SYSUTCDATETIME(), "
        "CONSTRAINT FK_core_users_organization FOREIGN KEY (organization_id) "
        "REFERENCES core.organizations(organization_id), "
        "CONSTRAINT UQ_core_users_organization_user UNIQUE (organization_id, user_id), "
        "CONSTRAINT UQ_core_users_organization_email UNIQUE (organization_id, email)"
        ")"
    )
    op.execute(
        "CREATE INDEX IX_core_users_organization_status "
        "ON core.users (organization_id, status)"
    )
    op.execute(
        "CREATE TABLE core.user_profiles ("
        "profile_id uniqueidentifier NOT NULL "
        "CONSTRAINT PK_core_user_profiles PRIMARY KEY, "
        "organization_id uniqueidentifier NOT NULL, "
        "user_id uniqueidentifier NOT NULL, "
        "display_name nvarchar(255) NOT NULL, "
        "phone varchar(32) NULL, "
        "avatar_url nvarchar(2048) NULL, "
        "created_at datetime2(3) NOT NULL "
        "CONSTRAINT DF_core_user_profiles_created_at DEFAULT SYSUTCDATETIME(), "
        "updated_at datetime2(3) NOT NULL "
        "CONSTRAINT DF_core_user_profiles_updated_at DEFAULT SYSUTCDATETIME(), "
        "CONSTRAINT UQ_core_user_profiles_organization_profile "
        "UNIQUE (organization_id, profile_id), "
        "CONSTRAINT UQ_core_user_profiles_organization_user "
        "UNIQUE (organization_id, user_id), "
        "CONSTRAINT FK_core_user_profiles_user FOREIGN KEY "
        "(organization_id, user_id) REFERENCES core.users (organization_id, user_id)"
        ")"
    )
    _add_tenant_predicates("core.users")
    _add_tenant_predicates("core.user_profiles")
    op.execute(
        "CREATE TABLE ops.prelogin_security_events ("
        "event_id uniqueidentifier NOT NULL "
        "CONSTRAINT PK_ops_prelogin_security_events PRIMARY KEY, "
        "action varchar(128) NOT NULL "
        "CONSTRAINT CK_ops_prelogin_security_events_action "
        "CHECK (action = 'authentication.login_failed'), "
        "correlation_id uniqueidentifier NOT NULL, "
        "occurred_at datetime2(3) NOT NULL "
        "CONSTRAINT DF_ops_prelogin_security_events_occurred_at "
        "DEFAULT SYSUTCDATETIME()"
        ")"
    )
    op.execute(
        "CREATE INDEX IX_ops_prelogin_security_events_occurred "
        "ON ops.prelogin_security_events (occurred_at)"
    )
    op.execute(
        "CREATE PROCEDURE ops.record_prelogin_security_event "
        "@event_id uniqueidentifier, @correlation_id uniqueidentifier "
        "WITH EXECUTE AS OWNER AS BEGIN SET NOCOUNT ON; "
        "INSERT INTO ops.prelogin_security_events "
        "(event_id, action, correlation_id) VALUES "
        "(@event_id, 'authentication.login_failed', @correlation_id); END"
    )
    op.execute(
        f"DENY SELECT, INSERT, UPDATE, DELETE ON OBJECT::ops.prelogin_security_events "
        f"TO [{runtime_login}]"
    )
    op.execute(f"REVOKE EXECUTE ON SCHEMA::ops FROM [{runtime_login}]")
    op.execute(
        "GRANT EXECUTE ON OBJECT::ops.record_prelogin_security_event "
        f"TO [{runtime_login}]"
    )


def downgrade() -> None:
    """Remove BE-007 persistence in reverse dependency order."""
    runtime_login = context.config.attributes["runtime_login"]
    op.execute("DROP PROCEDURE ops.record_prelogin_security_event")
    op.execute("DROP TABLE ops.prelogin_security_events")
    _drop_tenant_predicates("core.user_profiles")
    _drop_tenant_predicates("core.users")
    op.execute("DROP TABLE core.user_profiles")
    op.execute("DROP TABLE core.users")
    op.execute(f"GRANT EXECUTE ON SCHEMA::ops TO [{runtime_login}]")
