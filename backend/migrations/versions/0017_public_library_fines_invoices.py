"""Create public library fines, payments, invoices, invoice lines, and payment allocations.

Revision ID: 0017_public_library_fines_invoices
Revises: 0016_public_library_memberships
Create Date: 2026-09-23
"""

from alembic import op


revision = "0017_public_library_fines_invoices"
down_revision = "0016_public_library_memberships"
branch_labels = None
depends_on = None

_TABLES = [
    "public_library.fines",
    "public_library.payments",
    "public_library.invoices",
    "public_library.invoice_lines",
    "public_library.payment_allocations",
]


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
    """Create public library financial tables with explicit currency, decimal(19,4), and RLS."""
    # 1. fines
    op.execute(
        "CREATE TABLE public_library.fines ("
        "fine_id uniqueidentifier NOT NULL "
        "CONSTRAINT PK_public_library_fines PRIMARY KEY, "
        "organization_id uniqueidentifier NOT NULL, "
        "member_id uniqueidentifier NOT NULL, "
        "loan_id uniqueidentifier NULL, "
        "amount decimal(19,4) NOT NULL CONSTRAINT DF_public_library_fines_amount DEFAULT 0.0000, "
        "currency varchar(3) NOT NULL CONSTRAINT DF_public_library_fines_currency DEFAULT 'USD', "
        "status varchar(32) NOT NULL CONSTRAINT DF_public_library_fines_status DEFAULT 'assessed', "
        "reason nvarchar(255) NOT NULL, "
        "assessed_at datetime2 NOT NULL CONSTRAINT DF_public_library_fines_assessed_at DEFAULT SYSUTCDATETIME(), "
        "created_at datetime2 NOT NULL CONSTRAINT DF_public_library_fines_created_at DEFAULT SYSUTCDATETIME(), "
        "updated_at datetime2 NOT NULL CONSTRAINT DF_public_library_fines_updated_at DEFAULT SYSUTCDATETIME(), "
        "CONSTRAINT CK_public_library_fines_amount CHECK (amount >= 0), "
        "CONSTRAINT UQ_public_library_fines_org_fine UNIQUE (organization_id, fine_id), "
        "CONSTRAINT FK_public_library_fines_organization FOREIGN KEY (organization_id) REFERENCES core.organizations (organization_id), "
        "CONSTRAINT FK_public_library_fines_member FOREIGN KEY (organization_id, member_id) REFERENCES public_library.members (organization_id, member_id), "
        "CONSTRAINT FK_public_library_fines_loan FOREIGN KEY (organization_id, loan_id) REFERENCES core.loans (organization_id, loan_id))"
    )
    _add_tenant_predicates("public_library.fines")

    # 2. payments
    op.execute(
        "CREATE TABLE public_library.payments ("
        "payment_id uniqueidentifier NOT NULL "
        "CONSTRAINT PK_public_library_payments PRIMARY KEY, "
        "organization_id uniqueidentifier NOT NULL, "
        "member_id uniqueidentifier NOT NULL, "
        "amount decimal(19,4) NOT NULL, "
        "currency varchar(3) NOT NULL CONSTRAINT DF_public_library_payments_currency DEFAULT 'USD', "
        "provider varchar(64) NOT NULL, "
        "provider_reference varchar(255) NULL, "
        "provider_event_id varchar(255) NULL, "
        "status varchar(32) NOT NULL CONSTRAINT DF_public_library_payments_status DEFAULT 'succeeded', "
        "paid_at datetime2 NULL, "
        "created_at datetime2 NOT NULL CONSTRAINT DF_public_library_payments_created_at DEFAULT SYSUTCDATETIME(), "
        "updated_at datetime2 NOT NULL CONSTRAINT DF_public_library_payments_updated_at DEFAULT SYSUTCDATETIME(), "
        "CONSTRAINT CK_public_library_payments_amount CHECK (amount >= 0), "
        "CONSTRAINT UQ_public_library_payments_org_payment UNIQUE (organization_id, payment_id), "
        "CONSTRAINT FK_public_library_payments_organization FOREIGN KEY (organization_id) REFERENCES core.organizations (organization_id), "
        "CONSTRAINT FK_public_library_payments_member FOREIGN KEY (organization_id, member_id) REFERENCES public_library.members (organization_id, member_id))"
    )
    _add_tenant_predicates("public_library.payments")

    # 3. invoices
    op.execute(
        "CREATE TABLE public_library.invoices ("
        "invoice_id uniqueidentifier NOT NULL "
        "CONSTRAINT PK_public_library_invoices PRIMARY KEY, "
        "organization_id uniqueidentifier NOT NULL, "
        "member_id uniqueidentifier NOT NULL, "
        "invoice_number nvarchar(64) NOT NULL, "
        "subtotal decimal(19,4) NOT NULL, "
        "tax decimal(19,4) NOT NULL CONSTRAINT DF_public_library_invoices_tax DEFAULT 0.0000, "
        "total decimal(19,4) NOT NULL, "
        "currency varchar(3) NOT NULL CONSTRAINT DF_public_library_invoices_currency DEFAULT 'USD', "
        "status varchar(32) NOT NULL CONSTRAINT DF_public_library_invoices_status DEFAULT 'issued', "
        "issued_at datetime2 NOT NULL CONSTRAINT DF_public_library_invoices_issued_at DEFAULT SYSUTCDATETIME(), "
        "due_at datetime2 NULL, "
        "created_at datetime2 NOT NULL CONSTRAINT DF_public_library_invoices_created_at DEFAULT SYSUTCDATETIME(), "
        "updated_at datetime2 NOT NULL CONSTRAINT DF_public_library_invoices_updated_at DEFAULT SYSUTCDATETIME(), "
        "CONSTRAINT CK_public_library_invoices_subtotal CHECK (subtotal >= 0), "
        "CONSTRAINT CK_public_library_invoices_tax CHECK (tax >= 0), "
        "CONSTRAINT CK_public_library_invoices_total CHECK (total >= 0), "
        "CONSTRAINT UQ_public_library_invoices_org_invoice UNIQUE (organization_id, invoice_id), "
        "CONSTRAINT UQ_public_library_invoices_org_number UNIQUE (organization_id, invoice_number), "
        "CONSTRAINT FK_public_library_invoices_organization FOREIGN KEY (organization_id) REFERENCES core.organizations (organization_id), "
        "CONSTRAINT FK_public_library_invoices_member FOREIGN KEY (organization_id, member_id) REFERENCES public_library.members (organization_id, member_id))"
    )
    _add_tenant_predicates("public_library.invoices")

    # 4. invoice_lines
    op.execute(
        "CREATE TABLE public_library.invoice_lines ("
        "invoice_line_id uniqueidentifier NOT NULL "
        "CONSTRAINT PK_public_library_invoice_lines PRIMARY KEY, "
        "organization_id uniqueidentifier NOT NULL, "
        "invoice_id uniqueidentifier NOT NULL, "
        "line_number int NOT NULL, "
        "description nvarchar(255) NOT NULL, "
        "quantity int NOT NULL, "
        "unit_price decimal(19,4) NOT NULL, "
        "amount decimal(19,4) NOT NULL, "
        "fine_id uniqueidentifier NULL, "
        "created_at datetime2 NOT NULL CONSTRAINT DF_public_library_inv_lines_created_at DEFAULT SYSUTCDATETIME(), "
        "CONSTRAINT CK_public_library_inv_lines_quantity CHECK (quantity > 0), "
        "CONSTRAINT CK_public_library_inv_lines_amount CHECK (amount >= 0), "
        "CONSTRAINT UQ_public_library_inv_lines_org_line UNIQUE (organization_id, invoice_line_id), "
        "CONSTRAINT UQ_public_library_inv_lines_org_inv_line UNIQUE (organization_id, invoice_id, line_number), "
        "CONSTRAINT FK_public_library_inv_lines_organization FOREIGN KEY (organization_id) REFERENCES core.organizations (organization_id), "
        "CONSTRAINT FK_public_library_inv_lines_invoice FOREIGN KEY (organization_id, invoice_id) REFERENCES public_library.invoices (organization_id, invoice_id), "
        "CONSTRAINT FK_public_library_inv_lines_fine FOREIGN KEY (organization_id, fine_id) REFERENCES public_library.fines (organization_id, fine_id))"
    )
    _add_tenant_predicates("public_library.invoice_lines")

    # 5. payment_allocations
    op.execute(
        "CREATE TABLE public_library.payment_allocations ("
        "allocation_id uniqueidentifier NOT NULL "
        "CONSTRAINT PK_public_library_payment_allocations PRIMARY KEY, "
        "organization_id uniqueidentifier NOT NULL, "
        "payment_id uniqueidentifier NOT NULL, "
        "fine_id uniqueidentifier NOT NULL, "
        "invoice_id uniqueidentifier NULL, "
        "amount decimal(19,4) NOT NULL, "
        "allocation_type varchar(32) NOT NULL CONSTRAINT DF_public_library_alloc_type DEFAULT 'payment', "
        "created_at datetime2 NOT NULL CONSTRAINT DF_public_library_alloc_created_at DEFAULT SYSUTCDATETIME(), "
        "CONSTRAINT CK_public_library_alloc_amount CHECK (amount > 0), "
        "CONSTRAINT UQ_public_library_alloc_org_alloc UNIQUE (organization_id, allocation_id), "
        "CONSTRAINT FK_public_library_alloc_organization FOREIGN KEY (organization_id) REFERENCES core.organizations (organization_id), "
        "CONSTRAINT FK_public_library_alloc_payment FOREIGN KEY (organization_id, payment_id) REFERENCES public_library.payments (organization_id, payment_id), "
        "CONSTRAINT FK_public_library_alloc_fine FOREIGN KEY (organization_id, fine_id) REFERENCES public_library.fines (organization_id, fine_id), "
        "CONSTRAINT FK_public_library_alloc_invoice FOREIGN KEY (organization_id, invoice_id) REFERENCES public_library.invoices (organization_id, invoice_id))"
    )
    _add_tenant_predicates("public_library.payment_allocations")

    # Indexes
    op.execute(
        "CREATE INDEX IX_public_library_fines_member_status "
        "ON public_library.fines (organization_id, member_id, status)"
    )
    op.execute(
        "CREATE INDEX IX_public_library_fines_loan "
        "ON public_library.fines (organization_id, loan_id)"
    )
    op.execute(
        "CREATE INDEX IX_public_library_payments_member_status "
        "ON public_library.payments (organization_id, member_id, status)"
    )
    op.execute(
        "CREATE INDEX IX_public_library_invoices_member_status "
        "ON public_library.invoices (organization_id, member_id, status)"
    )
    op.execute(
        "CREATE INDEX IX_public_library_inv_lines_invoice "
        "ON public_library.invoice_lines (organization_id, invoice_id)"
    )
    op.execute(
        "CREATE INDEX IX_public_library_alloc_fine "
        "ON public_library.payment_allocations (organization_id, fine_id)"
    )
    op.execute(
        "CREATE INDEX IX_public_library_alloc_payment "
        "ON public_library.payment_allocations (organization_id, payment_id)"
    )


def downgrade() -> None:
    """Detach RLS predicates and drop tables in reverse dependency order."""
    op.execute(
        "DROP INDEX IX_public_library_alloc_payment ON public_library.payment_allocations"
    )
    op.execute(
        "DROP INDEX IX_public_library_alloc_fine ON public_library.payment_allocations"
    )
    op.execute(
        "DROP INDEX IX_public_library_inv_lines_invoice ON public_library.invoice_lines"
    )
    op.execute(
        "DROP INDEX IX_public_library_invoices_member_status ON public_library.invoices"
    )
    op.execute(
        "DROP INDEX IX_public_library_payments_member_status ON public_library.payments"
    )
    op.execute("DROP INDEX IX_public_library_fines_loan ON public_library.fines")
    op.execute(
        "DROP INDEX IX_public_library_fines_member_status ON public_library.fines"
    )

    for table_name in reversed(_TABLES):
        _drop_tenant_predicates(table_name)
        op.execute(f"DROP TABLE {table_name}")
