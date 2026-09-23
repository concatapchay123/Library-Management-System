"""Create tenant-scoped circulation loans with active loan invariants and RLS.

Revision ID: 0012_loans
Revises: 0011_outbox_claim_jobs
Create Date: 2026-09-23
"""

from alembic import op


revision = "0012_loans"
down_revision = "0011_outbox_claim_jobs"
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
    """Add core.loans table with composite tenant constraints, active loan invariant, and RLS."""
    op.execute(
        "CREATE TABLE core.loans ("
        "loan_id uniqueidentifier NOT NULL "
        "CONSTRAINT PK_core_loans PRIMARY KEY, "
        "organization_id uniqueidentifier NOT NULL, "
        "copy_id uniqueidentifier NOT NULL, "
        "borrower_user_id uniqueidentifier NOT NULL, "
        "status varchar(32) NOT NULL CONSTRAINT DF_core_loans_status DEFAULT 'requested', "
        "loan_status varchar(32) NOT NULL CONSTRAINT DF_core_loans_loan_status DEFAULT 'requested', "
        "request_status varchar(32) NOT NULL CONSTRAINT DF_core_loans_request_status DEFAULT 'pending', "
        "requested_at datetime2 NOT NULL CONSTRAINT DF_core_loans_requested_at DEFAULT SYSUTCDATETIME(), "
        "approved_at datetime2 NULL, "
        "checked_out_at datetime2 NULL, "
        "due_at datetime2 NULL, "
        "returned_at datetime2 NULL, "
        "policy_snapshot_json nvarchar(max) NOT NULL CONSTRAINT DF_core_loans_policy_snapshot DEFAULT '{}', "
        "created_at datetime2 NOT NULL CONSTRAINT DF_core_loans_created_at DEFAULT SYSUTCDATETIME(), "
        "updated_at datetime2 NOT NULL CONSTRAINT DF_core_loans_updated_at DEFAULT SYSUTCDATETIME(), "
        "CONSTRAINT UQ_core_loans_organization_loan UNIQUE (organization_id, loan_id), "
        "CONSTRAINT FK_core_loans_organization FOREIGN KEY (organization_id) REFERENCES core.organizations (organization_id), "
        "CONSTRAINT FK_core_loans_copy FOREIGN KEY (organization_id, copy_id) REFERENCES core.book_copies (organization_id, copy_id), "
        "CONSTRAINT FK_core_loans_borrower FOREIGN KEY (organization_id, borrower_user_id) REFERENCES core.users (organization_id, user_id))"
    )
    op.execute(
        "CREATE UNIQUE INDEX UQ_core_loans_active_copy ON core.loans "
        "(organization_id, copy_id) WHERE status = 'checked_out'"
    )
    op.execute(
        "CREATE INDEX IX_core_loans_tenant_copy_status ON core.loans "
        "(organization_id, copy_id, status)"
    )
    op.execute(
        "CREATE INDEX IX_core_loans_tenant_borrower_status ON core.loans "
        "(organization_id, borrower_user_id, status)"
    )
    op.execute(
        "CREATE INDEX IX_core_loans_tenant_due_status ON core.loans "
        "(organization_id, due_at, status)"
    )
    _add_tenant_predicates("core.loans")


def downgrade() -> None:
    """Remove core.loans table only after dropping attached RLS predicates."""
    _drop_tenant_predicates("core.loans")
    op.execute("DROP TABLE core.loans")
