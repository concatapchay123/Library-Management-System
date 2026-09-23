"""Create tenant-protected idempotency keys table with 24-hour expiration and RLS.

Revision ID: 0013_idempotency_keys
Revises: 0012_loans
Create Date: 2026-09-23
"""

from alembic import op


revision = "0013_idempotency_keys"
down_revision = "0012_loans"
branch_labels = None
depends_on = None


def _add_tenant_predicates(table_name: str) -> None:
    """Attach every data operation to the shared fail-closed tenant policy."""
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
    """Detach all predicates before dropping a tenant-owned table."""
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
    """Create ops.idempotency_keys table for safe request replay with RLS."""
    op.execute(
        "CREATE TABLE ops.idempotency_keys ("
        "key_id uniqueidentifier NOT NULL "
        "CONSTRAINT PK_ops_idempotency_keys PRIMARY KEY, "
        "organization_id uniqueidentifier NOT NULL, "
        "idempotency_key varchar(128) NOT NULL, "
        "method varchar(16) NOT NULL, "
        "endpoint varchar(256) NOT NULL, "
        "request_hash varchar(64) NOT NULL, "
        "resource_reference varchar(256) NULL, "
        "status_code smallint NOT NULL "
        "CONSTRAINT DF_ops_idempotency_keys_status_code DEFAULT 200, "
        "safe_response_json nvarchar(max) NOT NULL "
        "CONSTRAINT CK_ops_idempotency_keys_safe_response CHECK (ISJSON(safe_response_json) = 1), "
        "created_at datetime2(3) NOT NULL "
        "CONSTRAINT DF_ops_idempotency_keys_created_at DEFAULT SYSUTCDATETIME(), "
        "expires_at datetime2(3) NOT NULL, "
        "CONSTRAINT FK_ops_idempotency_keys_organization FOREIGN KEY (organization_id) REFERENCES core.organizations (organization_id), "
        "CONSTRAINT UQ_ops_idempotency_keys_tenant_key "
        "UNIQUE (organization_id, idempotency_key, method, endpoint)"
        ")"
    )
    op.execute(
        "CREATE INDEX IX_ops_idempotency_keys_tenant_expires "
        "ON ops.idempotency_keys (organization_id, expires_at)"
    )
    _add_tenant_predicates("ops.idempotency_keys")


def downgrade() -> None:
    """Remove ops.idempotency_keys table only after dropping attached RLS predicates."""
    _drop_tenant_predicates("ops.idempotency_keys")
    op.execute("DROP TABLE ops.idempotency_keys")
