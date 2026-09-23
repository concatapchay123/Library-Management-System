"""Create tenant-scoped locations and book copies.

Revision ID: 0009_locations_and_book_copies
Revises: 0008_books
Create Date: 2026-09-23
"""

from alembic import op


revision = "0009_locations_and_book_copies"
down_revision = "0008_books"
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
    """Add locations and physical copies with tenant composite constraints and RLS."""
    op.execute(
        "CREATE TABLE core.locations (location_id uniqueidentifier NOT NULL "
        "CONSTRAINT PK_core_locations PRIMARY KEY, organization_id uniqueidentifier NOT NULL, "
        "name nvarchar(255) NOT NULL, "
        "code varchar(64) NOT NULL, "
        "parent_location_id uniqueidentifier NULL, "
        "status varchar(32) NOT NULL CONSTRAINT DF_core_locations_status DEFAULT 'active', "
        "created_at datetime2 NOT NULL CONSTRAINT DF_core_locations_created_at "
        "DEFAULT SYSUTCDATETIME(), updated_at datetime2 NOT NULL "
        "CONSTRAINT DF_core_locations_updated_at DEFAULT SYSUTCDATETIME(), "
        "CONSTRAINT UQ_core_locations_organization_location UNIQUE (organization_id, location_id), "
        "CONSTRAINT UQ_core_locations_organization_code UNIQUE (organization_id, code), "
        "CONSTRAINT FK_core_locations_organization FOREIGN KEY (organization_id) REFERENCES core.organizations (organization_id), "
        "CONSTRAINT FK_core_locations_parent FOREIGN KEY (organization_id, parent_location_id) REFERENCES core.locations (organization_id, location_id))"
    )
    op.execute(
        "CREATE INDEX IX_core_locations_tenant_parent ON core.locations "
        "(organization_id, parent_location_id)"
    )
    _add_tenant_predicates("core.locations")

    op.execute(
        "CREATE TABLE core.book_copies (copy_id uniqueidentifier NOT NULL "
        "CONSTRAINT PK_core_book_copies PRIMARY KEY, organization_id uniqueidentifier NOT NULL, "
        "book_id uniqueidentifier NOT NULL, "
        "barcode varchar(64) NOT NULL, "
        "location_id uniqueidentifier NOT NULL, "
        "status varchar(32) NOT NULL CONSTRAINT DF_core_book_copies_status DEFAULT 'available', "
        "condition_code varchar(32) NOT NULL CONSTRAINT DF_core_book_copies_condition_code DEFAULT 'good', "
        "acquired_at datetime2 NOT NULL CONSTRAINT DF_core_book_copies_acquired_at "
        "DEFAULT SYSUTCDATETIME(), "
        "created_at datetime2 NOT NULL CONSTRAINT DF_core_book_copies_created_at "
        "DEFAULT SYSUTCDATETIME(), updated_at datetime2 NOT NULL "
        "CONSTRAINT DF_core_book_copies_updated_at DEFAULT SYSUTCDATETIME(), "
        "CONSTRAINT UQ_core_book_copies_organization_copy UNIQUE (organization_id, copy_id), "
        "CONSTRAINT UQ_core_book_copies_organization_barcode UNIQUE (organization_id, barcode), "
        "CONSTRAINT FK_core_book_copies_organization FOREIGN KEY (organization_id) REFERENCES core.organizations (organization_id), "
        "CONSTRAINT FK_core_book_copies_book FOREIGN KEY (organization_id, book_id) REFERENCES core.books (organization_id, book_id), "
        "CONSTRAINT FK_core_book_copies_location FOREIGN KEY (organization_id, location_id) REFERENCES core.locations (organization_id, location_id))"
    )
    op.execute(
        "CREATE INDEX IX_core_book_copies_tenant_book_status ON core.book_copies "
        "(organization_id, book_id, status)"
    )
    op.execute(
        "CREATE INDEX IX_core_book_copies_tenant_location ON core.book_copies "
        "(organization_id, location_id)"
    )
    _add_tenant_predicates("core.book_copies")


def downgrade() -> None:
    """Remove copy and location tables only after removing attached RLS predicates."""
    _drop_tenant_predicates("core.book_copies")
    _drop_tenant_predicates("core.locations")
    op.execute("DROP TABLE core.book_copies")
    op.execute("DROP TABLE core.locations")
