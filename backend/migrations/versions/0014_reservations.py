"""Create tenant-scoped reservations with queue ordering, hold expiry and RLS.

Revision ID: 0014_reservations
Revises: 0013_idempotency_keys
Create Date: 2026-09-23
"""

from alembic import op


revision = "0014_reservations"
down_revision = "0013_idempotency_keys"
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
    """Add core.reservations table with composite tenant constraints, queue index, and RLS."""
    op.execute(
        "CREATE TABLE core.reservations ("
        "reservation_id uniqueidentifier NOT NULL "
        "CONSTRAINT PK_core_reservations PRIMARY KEY, "
        "organization_id uniqueidentifier NOT NULL, "
        "book_id uniqueidentifier NOT NULL, "
        "requester_user_id uniqueidentifier NOT NULL, "
        "copy_id uniqueidentifier NULL, "
        "queue_position int NOT NULL, "
        "status varchar(32) NOT NULL CONSTRAINT DF_core_reservations_status DEFAULT 'pending', "
        "hold_expires_at datetime2 NULL, "
        "created_at datetime2 NOT NULL CONSTRAINT DF_core_reservations_created_at DEFAULT SYSUTCDATETIME(), "
        "updated_at datetime2 NOT NULL CONSTRAINT DF_core_reservations_updated_at DEFAULT SYSUTCDATETIME(), "
        "CONSTRAINT UQ_core_reservations_organization_reservation UNIQUE (organization_id, reservation_id), "
        "CONSTRAINT FK_core_reservations_organization FOREIGN KEY (organization_id) REFERENCES core.organizations (organization_id), "
        "CONSTRAINT FK_core_reservations_book FOREIGN KEY (organization_id, book_id) REFERENCES core.books (organization_id, book_id), "
        "CONSTRAINT FK_core_reservations_requester FOREIGN KEY (organization_id, requester_user_id) REFERENCES core.users (organization_id, user_id), "
        "CONSTRAINT FK_core_reservations_copy FOREIGN KEY (organization_id, copy_id) REFERENCES core.book_copies (organization_id, copy_id))"
    )
    op.execute(
        "CREATE UNIQUE INDEX UQ_core_reservations_held_copy ON core.reservations "
        "(organization_id, copy_id) WHERE status = 'held'"
    )
    op.execute(
        "CREATE INDEX IX_core_reservations_tenant_book_status ON core.reservations "
        "(organization_id, book_id, status, queue_position, created_at)"
    )
    op.execute(
        "CREATE INDEX IX_core_reservations_tenant_requester_status ON core.reservations "
        "(organization_id, requester_user_id, status)"
    )
    op.execute(
        "CREATE INDEX IX_core_reservations_tenant_hold_expires ON core.reservations "
        "(organization_id, hold_expires_at, status)"
    )
    _add_tenant_predicates("core.reservations")


def downgrade() -> None:
    """Remove core.reservations table only after dropping attached RLS predicates."""
    _drop_tenant_predicates("core.reservations")
    op.execute("DROP TABLE core.reservations")
