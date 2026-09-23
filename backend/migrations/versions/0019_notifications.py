"""Create tenant-scoped core.notifications table, inbox indexes, and RLS predicates.

Revision ID: 0019_notifications
Revises: 0018_public_library_payment_webhooks
Create Date: 2026-09-23
"""

from alembic import op


revision = "0019_notifications"
down_revision = "0018_public_library_payment_webhooks"
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
    """Add core.notifications table with composite tenant constraints, inbox index, and RLS."""
    op.execute(
        "CREATE TABLE core.notifications ("
        "notification_id uniqueidentifier NOT NULL "
        "CONSTRAINT PK_core_notifications PRIMARY KEY, "
        "organization_id uniqueidentifier NOT NULL, "
        "user_id uniqueidentifier NOT NULL, "
        "channel varchar(32) NOT NULL CONSTRAINT DF_core_notifications_channel DEFAULT 'in_app', "
        "type varchar(64) NOT NULL, "
        "payload_json nvarchar(max) NOT NULL, "
        "status varchar(32) NOT NULL CONSTRAINT DF_core_notifications_status DEFAULT 'unread', "
        "read_at datetime2(3) NULL, "
        "outbox_event_id uniqueidentifier NULL, "
        "created_at datetime2(3) NOT NULL CONSTRAINT DF_core_notifications_created_at DEFAULT SYSUTCDATETIME(), "
        "CONSTRAINT UQ_core_notifications_organization_notification UNIQUE (organization_id, notification_id), "
        "CONSTRAINT FK_core_notifications_organization FOREIGN KEY (organization_id) REFERENCES core.organizations (organization_id), "
        "CONSTRAINT FK_core_notifications_user FOREIGN KEY (organization_id, user_id) REFERENCES core.users (organization_id, user_id), "
        "CONSTRAINT FK_core_notifications_outbox_events FOREIGN KEY (organization_id, outbox_event_id) REFERENCES ops.outbox_events (organization_id, event_id), "
        "CONSTRAINT CK_core_notifications_status CHECK (status IN ('unread', 'read')), "
        "CONSTRAINT CK_core_notifications_channel CHECK (channel IN ('in_app', 'email'))"
        ")"
    )
    op.execute(
        "CREATE INDEX IX_core_notifications_inbox "
        "ON core.notifications (organization_id, user_id, status, created_at DESC)"
    )
    op.execute(
        "CREATE UNIQUE INDEX UQ_core_notifications_event_user "
        "ON core.notifications (organization_id, outbox_event_id, user_id) "
        "WHERE outbox_event_id IS NOT NULL"
    )
    _add_tenant_predicates("core.notifications")


def downgrade() -> None:
    """Remove core.notifications table only after dropping attached RLS predicates and indexes."""
    op.execute("DROP INDEX UQ_core_notifications_event_user ON core.notifications")
    op.execute("DROP INDEX IX_core_notifications_inbox ON core.notifications")
    _drop_tenant_predicates("core.notifications")
    op.execute("DROP TABLE core.notifications")
