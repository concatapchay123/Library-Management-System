"""Create the RLS-protected organization registry and login resolver.

Revision ID: 0002_organizations_rls
Revises: 0001_database_identities
Create Date: 2026-09-21
"""

from alembic import context, op


revision = "0002_organizations_rls"
down_revision = "0001_database_identities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the tenant root, fail-closed policy, and narrow pre-login procedure."""
    runtime_login = context.config.attributes["runtime_login"]
    op.execute("CREATE ROLE core_login_resolver_role")
    op.execute(
        "CREATE TABLE core.organizations ("
        "organization_id uniqueidentifier NOT NULL "
        "CONSTRAINT PK_core_organizations PRIMARY KEY, "
        "name nvarchar(255) NOT NULL, "
        "slug varchar(100) NOT NULL "
        "CONSTRAINT UQ_core_organizations_slug UNIQUE, "
        "organization_type varchar(32) NOT NULL, "
        "status varchar(32) NOT NULL, "
        "timezone varchar(64) NOT NULL, "
        "settings_json nvarchar(max) NOT NULL, "
        "created_at datetime2(3) NOT NULL "
        "CONSTRAINT DF_core_organizations_created_at DEFAULT SYSUTCDATETIME(), "
        "updated_at datetime2(3) NOT NULL "
        "CONSTRAINT DF_core_organizations_updated_at DEFAULT SYSUTCDATETIME()"
        ")"
    )
    op.execute(
        "CREATE FUNCTION core.tenant_access_predicate "
        "(@organization_id uniqueidentifier) "
        "RETURNS TABLE WITH SCHEMABINDING "
        "AS RETURN SELECT CAST(1 AS bit) AS predicate_result "
        "WHERE USER_NAME() = N'dbo' "
        "OR IS_MEMBER(N'core_login_resolver_role') = 1 "
        "OR @organization_id = TRY_CONVERT("
        "uniqueidentifier, SESSION_CONTEXT(N'organization_id'))"
    )
    op.execute(
        "CREATE SECURITY POLICY core.organization_tenant_policy "
        "ADD FILTER PREDICATE core.tenant_access_predicate(organization_id) "
        "ON core.organizations, "
        "ADD BLOCK PREDICATE core.tenant_access_predicate(organization_id) "
        "ON core.organizations AFTER INSERT "
        "WITH (STATE = ON)"
    )
    op.execute(
        "CREATE PROCEDURE core.resolve_login_tenant @slug varchar(100) "
        "WITH EXECUTE AS OWNER "
        "AS BEGIN SET NOCOUNT ON; "
        "SELECT organization_id, slug, status "
        "FROM core.organizations WHERE slug = @slug; END"
    )
    op.execute(
        "CREATE CERTIFICATE core_login_resolver_certificate "
        "WITH SUBJECT = N'OpenLibraryOS pre-login resolver module signing'"
    )
    op.execute(
        "CREATE USER core_login_resolver_certificate_user "
        "FROM CERTIFICATE core_login_resolver_certificate"
    )
    op.execute(
        "ALTER ROLE core_login_resolver_role "
        "ADD MEMBER core_login_resolver_certificate_user"
    )
    op.execute(
        "ADD SIGNATURE TO OBJECT::core.resolve_login_tenant "
        "BY CERTIFICATE core_login_resolver_certificate"
    )
    op.execute(f"REVOKE EXECUTE ON SCHEMA::core FROM [{runtime_login}]")
    op.execute(
        f"GRANT EXECUTE ON OBJECT::core.resolve_login_tenant TO [{runtime_login}]"
    )


def downgrade() -> None:
    """Remove BE-004 objects and restore the BE-003 permission baseline."""
    runtime_login = context.config.attributes["runtime_login"]
    op.execute(
        "DROP SIGNATURE FROM OBJECT::core.resolve_login_tenant "
        "BY CERTIFICATE core_login_resolver_certificate"
    )
    op.execute("DROP PROCEDURE core.resolve_login_tenant")
    op.execute(
        "ALTER ROLE core_login_resolver_role "
        "DROP MEMBER core_login_resolver_certificate_user"
    )
    op.execute("DROP USER core_login_resolver_certificate_user")
    op.execute("DROP CERTIFICATE core_login_resolver_certificate")
    op.execute("DROP ROLE core_login_resolver_role")
    op.execute("DROP SECURITY POLICY core.organization_tenant_policy")
    op.execute("DROP FUNCTION core.tenant_access_predicate")
    op.execute("DROP TABLE core.organizations")
    op.execute(f"GRANT EXECUTE ON SCHEMA::core TO [{runtime_login}]")
