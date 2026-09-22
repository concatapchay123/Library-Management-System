"""Complete tenant RLS operations and create the privileged bootstrap boundary.

Revision ID: 0007_tenant_context_catalog
Revises: 0006_rbac
Create Date: 2026-09-22
"""

from alembic import context, op


revision = "0007_tenant_context_catalog"
down_revision = "0006_rbac"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Close the root-table RLS gap and expose bootstrap only to migrations."""
    migration_login = context.config.attributes["migration_login"]
    op.execute(
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "ADD BLOCK PREDICATE core.tenant_access_predicate(organization_id) "
        "ON core.organizations AFTER UPDATE"
    )
    op.execute(
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "ADD BLOCK PREDICATE core.tenant_access_predicate(organization_id) "
        "ON core.organizations BEFORE DELETE"
    )
    op.execute(
        "CREATE PROCEDURE core.bootstrap_organization "
        "@organization_id uniqueidentifier, @name nvarchar(255), @slug varchar(100), "
        "@organization_type varchar(32), @timezone varchar(64), @settings_json nvarchar(max), "
        "@correlation_id uniqueidentifier "
        "WITH EXECUTE AS OWNER AS BEGIN SET NOCOUNT ON; SET XACT_ABORT ON; BEGIN TRANSACTION; "
        "INSERT INTO core.organizations (organization_id, name, slug, organization_type, status, timezone, settings_json) "
        "VALUES (@organization_id, @name, @slug, @organization_type, 'active', @timezone, @settings_json); "
        "INSERT INTO ops.audit_events (audit_id, organization_id, actor_user_id, actor_type, action, entity_type, entity_id, payload_version, payload_json, correlation_id) "
        "VALUES (NEWID(), @organization_id, NULL, 'system', 'organization.bootstrapped', 'organization', @organization_id, 1, N'{}', @correlation_id); "
        "COMMIT; END"
    )
    op.execute(
        f"GRANT EXECUTE ON OBJECT::core.bootstrap_organization TO [{migration_login}]"
    )


def downgrade() -> None:
    """Remove the privileged path and restore the exact prior policy shape."""
    migration_login = context.config.attributes["migration_login"]
    op.execute(
        f"REVOKE EXECUTE ON OBJECT::core.bootstrap_organization TO [{migration_login}]"
    )
    op.execute("DROP PROCEDURE core.bootstrap_organization")
    op.execute(
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "DROP BLOCK PREDICATE ON core.organizations BEFORE DELETE"
    )
    op.execute(
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "DROP BLOCK PREDICATE ON core.organizations AFTER UPDATE"
    )
