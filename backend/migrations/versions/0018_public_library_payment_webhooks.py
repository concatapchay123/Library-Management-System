"""Create payment_events table, provider reference uniqueness, and payment status constraints with RLS.

Revision ID: 0018_public_library_payment_webhooks
Revises: 0017_public_library_fines_invoices
Create Date: 2026-09-23
"""

from alembic import op


revision = "0018_public_library_payment_webhooks"
down_revision = "0017_public_library_fines_invoices"
branch_labels = None
depends_on = None

_TABLES = ("public_library.payment_events",)


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
    """Create payment events table, status check constraint, and provider uniqueness."""
    # 1. Payment status check constraint
    op.execute(
        "ALTER TABLE public_library.payments ADD CONSTRAINT CK_public_library_payments_status "
        "CHECK (status IN ('pending', 'authorized', 'succeeded', 'failed', 'refunded', 'partially_refunded', 'disputed'))"
    )

    # 2. Filtered unique index on (organization_id, provider, provider_reference)
    op.execute(
        "CREATE UNIQUE INDEX UQ_public_library_payments_provider_ref "
        "ON public_library.payments (organization_id, provider, provider_reference) "
        "WHERE provider_reference IS NOT NULL"
    )

    # 3. payment_events table
    op.execute(
        "CREATE TABLE public_library.payment_events ("
        "event_id uniqueidentifier NOT NULL "
        "CONSTRAINT PK_public_library_payment_events PRIMARY KEY, "
        "organization_id uniqueidentifier NOT NULL, "
        "provider varchar(64) NOT NULL, "
        "provider_event_id varchar(255) NOT NULL, "
        "event_type varchar(64) NOT NULL, "
        "payload_hash varchar(64) NOT NULL, "
        "payment_id uniqueidentifier NULL, "
        "status varchar(32) NOT NULL CONSTRAINT DF_public_library_pe_status DEFAULT 'processed', "
        "created_at datetime2 NOT NULL CONSTRAINT DF_public_library_pe_created DEFAULT SYSUTCDATETIME(), "
        "CONSTRAINT UQ_public_library_pe_event UNIQUE (organization_id, provider, provider_event_id), "
        "CONSTRAINT FK_public_library_pe_org FOREIGN KEY (organization_id) REFERENCES core.organizations (organization_id), "
        "CONSTRAINT FK_public_library_pe_payment FOREIGN KEY (organization_id, payment_id) REFERENCES public_library.payments (organization_id, payment_id)"
        ")"
    )
    _add_tenant_predicates("public_library.payment_events")

    # 4. Indexes
    op.execute(
        "CREATE INDEX IX_public_library_pe_provider "
        "ON public_library.payment_events (organization_id, provider, created_at)"
    )
    op.execute(
        "CREATE INDEX IX_public_library_pe_payment "
        "ON public_library.payment_events (organization_id, payment_id)"
    )


def downgrade() -> None:
    """Detach predicates and drop tables and constraints."""
    op.execute(
        "DROP INDEX IX_public_library_pe_payment ON public_library.payment_events"
    )
    op.execute(
        "DROP INDEX IX_public_library_pe_provider ON public_library.payment_events"
    )
    _drop_tenant_predicates("public_library.payment_events")
    op.execute("DROP TABLE public_library.payment_events")

    op.execute(
        "DROP INDEX UQ_public_library_payments_provider_ref ON public_library.payments"
    )
    op.execute(
        "ALTER TABLE public_library.payments DROP CONSTRAINT CK_public_library_payments_status"
    )
