"""Create append-only copy status history with actor attribution and tenant isolation.

Revision ID: 0010_copy_status_history
Revises: 0009_locations_and_book_copies
Create Date: 2026-09-23
"""

from alembic import context, op

revision = "0010_copy_status_history"
down_revision = "0009_locations_and_book_copies"
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
    """Create core.copy_status_history table with composite FKs, RLS, and runtime immutability."""
    runtime_login = context.config.attributes["runtime_login"]
    op.execute(
        "CREATE TABLE core.copy_status_history ("
        "history_id uniqueidentifier NOT NULL "
        "CONSTRAINT PK_core_copy_status_history PRIMARY KEY, "
        "organization_id uniqueidentifier NOT NULL, "
        "copy_id uniqueidentifier NOT NULL, "
        "from_status varchar(32) NOT NULL, "
        "to_status varchar(32) NOT NULL, "
        "reason nvarchar(500) NOT NULL, "
        "actor_id uniqueidentifier NOT NULL, "
        "created_at datetime2 NOT NULL "
        "CONSTRAINT DF_core_copy_status_history_created_at DEFAULT SYSUTCDATETIME(), "
        "CONSTRAINT UQ_core_copy_status_history_organization_history UNIQUE (organization_id, history_id), "
        "CONSTRAINT FK_core_copy_status_history_organization FOREIGN KEY (organization_id) REFERENCES core.organizations (organization_id), "
        "CONSTRAINT FK_core_copy_status_history_copy FOREIGN KEY (organization_id, copy_id) REFERENCES core.book_copies (organization_id, copy_id), "
        "CONSTRAINT FK_core_copy_status_history_actor FOREIGN KEY (organization_id, actor_id) REFERENCES core.users (organization_id, user_id))"
    )
    op.execute(
        "CREATE INDEX IX_core_copy_status_history_tenant_copy ON core.copy_status_history "
        "(organization_id, copy_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IX_core_copy_status_history_tenant_actor ON core.copy_status_history "
        "(organization_id, actor_id)"
    )
    _add_tenant_predicates("core.copy_status_history")
    op.execute(
        f"DENY UPDATE, DELETE ON OBJECT::core.copy_status_history TO [{runtime_login}]"
    )


def downgrade() -> None:
    """Remove copy status history table only after dropping tenant security predicates."""
    _drop_tenant_predicates("core.copy_status_history")
    op.execute("DROP TABLE core.copy_status_history")
