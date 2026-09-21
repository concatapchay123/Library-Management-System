"""Create tenant-scoped data-driven RBAC relations.

Revision ID: 0006_rbac
Revises: 0005_refresh_sessions
Create Date: 2026-09-21
"""

from alembic import op


revision = "0006_rbac"
down_revision = "0005_refresh_sessions"
branch_labels = None
depends_on = None


def _add_tenant_predicates(table_name: str) -> None:
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
    op.execute(
        "CREATE TABLE core.roles (role_id uniqueidentifier NOT NULL "
        "CONSTRAINT PK_core_roles PRIMARY KEY, organization_id uniqueidentifier NOT NULL, "
        "name varchar(128) NOT NULL, CONSTRAINT UQ_core_roles_organization_role "
        "UNIQUE (organization_id, role_id), CONSTRAINT UQ_core_roles_organization_name "
        "UNIQUE (organization_id, name), CONSTRAINT FK_core_roles_organization "
        "FOREIGN KEY (organization_id) REFERENCES core.organizations (organization_id))"
    )
    op.execute(
        "CREATE TABLE core.permissions (permission_id uniqueidentifier NOT NULL "
        "CONSTRAINT PK_core_permissions PRIMARY KEY, organization_id uniqueidentifier NOT NULL, "
        "code varchar(128) NOT NULL, CONSTRAINT UQ_core_permissions_organization_permission "
        "UNIQUE (organization_id, permission_id), CONSTRAINT UQ_core_permissions_organization_code "
        "UNIQUE (organization_id, code), CONSTRAINT FK_core_permissions_organization "
        "FOREIGN KEY (organization_id) REFERENCES core.organizations (organization_id))"
    )
    op.execute(
        "CREATE TABLE core.user_roles (organization_id uniqueidentifier NOT NULL, "
        "user_id uniqueidentifier NOT NULL, role_id uniqueidentifier NOT NULL, "
        "CONSTRAINT PK_core_user_roles PRIMARY KEY (organization_id, user_id, role_id), "
        "CONSTRAINT FK_core_user_roles_user FOREIGN KEY (organization_id, user_id) "
        "REFERENCES core.users (organization_id, user_id), "
        "CONSTRAINT FK_core_user_roles_role FOREIGN KEY (organization_id, role_id) "
        "REFERENCES core.roles (organization_id, role_id))"
    )
    op.execute(
        "CREATE TABLE core.role_permissions (organization_id uniqueidentifier NOT NULL, "
        "role_id uniqueidentifier NOT NULL, permission_id uniqueidentifier NOT NULL, "
        "CONSTRAINT PK_core_role_permissions PRIMARY KEY (organization_id, role_id, permission_id), "
        "CONSTRAINT FK_core_role_permissions_role FOREIGN KEY (organization_id, role_id) "
        "REFERENCES core.roles (organization_id, role_id), "
        "CONSTRAINT FK_core_role_permissions_permission FOREIGN KEY (organization_id, permission_id) "
        "REFERENCES core.permissions (organization_id, permission_id))"
    )
    op.execute(
        "CREATE INDEX IX_core_user_roles_tenant_role ON core.user_roles (organization_id, role_id, user_id)"
    )
    op.execute(
        "CREATE INDEX IX_core_role_permissions_tenant_role ON core.role_permissions (organization_id, role_id, permission_id)"
    )
    _add_tenant_predicates("core.roles")
    _add_tenant_predicates("core.permissions")
    _add_tenant_predicates("core.user_roles")
    _add_tenant_predicates("core.role_permissions")


def downgrade() -> None:
    _drop_tenant_predicates("core.role_permissions")
    _drop_tenant_predicates("core.user_roles")
    _drop_tenant_predicates("core.permissions")
    _drop_tenant_predicates("core.roles")
    op.execute("DROP TABLE core.role_permissions")
    op.execute("DROP TABLE core.user_roles")
    op.execute("DROP TABLE core.permissions")
    op.execute("DROP TABLE core.roles")
