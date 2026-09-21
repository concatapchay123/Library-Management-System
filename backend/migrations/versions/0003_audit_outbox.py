"""Create tenant-protected immutable audit and transactional outbox tables.

Revision ID: 0003_audit_outbox
Revises: 0002_organizations_rls
Create Date: 2026-09-21
"""

from alembic import context, op


revision = "0003_audit_outbox"
down_revision = "0002_organizations_rls"
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
    op.execute(
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        f"DROP BLOCK PREDICATE ON {table_name}"
    )


def upgrade() -> None:
    """Create durable tenant-owned records used by protected mutations."""
    runtime_login = context.config.attributes["runtime_login"]
    op.execute(
        "CREATE TABLE ops.audit_events ("
        "audit_id uniqueidentifier NOT NULL "
        "CONSTRAINT PK_ops_audit_events PRIMARY KEY, "
        "organization_id uniqueidentifier NOT NULL, "
        "actor_user_id uniqueidentifier NULL, "
        "actor_type varchar(32) NOT NULL, "
        "action varchar(128) NOT NULL, "
        "entity_type varchar(128) NOT NULL, "
        "entity_id uniqueidentifier NOT NULL, "
        "payload_version smallint NOT NULL "
        "CONSTRAINT CK_ops_audit_events_payload_version CHECK (payload_version > 0), "
        "payload_json nvarchar(max) NOT NULL "
        "CONSTRAINT CK_ops_audit_events_payload_json CHECK (ISJSON(payload_json) = 1), "
        "correlation_id uniqueidentifier NOT NULL, "
        "occurred_at datetime2(3) NOT NULL "
        "CONSTRAINT DF_ops_audit_events_occurred_at DEFAULT SYSUTCDATETIME(), "
        "CONSTRAINT FK_ops_audit_events_organization FOREIGN KEY (organization_id) "
        "REFERENCES core.organizations(organization_id)"
        ")"
    )
    op.execute(
        "CREATE INDEX IX_ops_audit_events_organization_entity_occurred "
        "ON ops.audit_events (organization_id, entity_type, entity_id, occurred_at)"
    )
    op.execute(
        "CREATE INDEX IX_ops_audit_events_organization_actor_occurred "
        "ON ops.audit_events (organization_id, actor_user_id, occurred_at)"
    )
    op.execute(
        "CREATE TABLE ops.outbox_events ("
        "event_id uniqueidentifier NOT NULL "
        "CONSTRAINT PK_ops_outbox_events PRIMARY KEY, "
        "organization_id uniqueidentifier NOT NULL, "
        "event_type varchar(128) NOT NULL, "
        "aggregate_type varchar(128) NOT NULL, "
        "aggregate_id uniqueidentifier NOT NULL, "
        "payload_version smallint NOT NULL "
        "CONSTRAINT CK_ops_outbox_events_payload_version CHECK (payload_version > 0), "
        "payload_json nvarchar(max) NOT NULL "
        "CONSTRAINT CK_ops_outbox_events_payload_json CHECK (ISJSON(payload_json) = 1), "
        "correlation_id uniqueidentifier NOT NULL, "
        "idempotency_key varchar(128) NOT NULL, "
        "created_at datetime2(3) NOT NULL "
        "CONSTRAINT DF_ops_outbox_events_created_at DEFAULT SYSUTCDATETIME(), "
        "CONSTRAINT FK_ops_outbox_events_organization FOREIGN KEY (organization_id) "
        "REFERENCES core.organizations(organization_id), "
        "CONSTRAINT UQ_ops_outbox_events_tenant_event_idempotency "
        "UNIQUE (organization_id, event_type, idempotency_key)"
        ")"
    )
    op.execute(
        "CREATE INDEX IX_ops_outbox_events_organization_aggregate_created "
        "ON ops.outbox_events (organization_id, aggregate_type, aggregate_id, created_at)"
    )
    _add_tenant_predicates("ops.audit_events")
    _add_tenant_predicates("ops.outbox_events")
    op.execute(f"DENY UPDATE, DELETE ON OBJECT::ops.audit_events TO [{runtime_login}]")


def downgrade() -> None:
    """Remove BE-005 tables without disturbing the shared tenant boundary."""
    _drop_tenant_predicates("ops.outbox_events")
    _drop_tenant_predicates("ops.audit_events")
    op.execute("DROP TABLE ops.outbox_events")
    op.execute("DROP TABLE ops.audit_events")
