"""Create tenant-scoped bibliographic book titles.

Revision ID: 0008_books
Revises: 0007_tenant_context_catalog
Create Date: 2026-09-22
"""

from alembic import op


revision = "0008_books"
down_revision = "0007_tenant_context_catalog"
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
    """Add titles only; physical copies and availability remain out of this schema."""
    op.execute(
        "CREATE TABLE core.books (book_id uniqueidentifier NOT NULL "
        "CONSTRAINT PK_core_books PRIMARY KEY, organization_id uniqueidentifier NOT NULL, "
        "title nvarchar(512) NOT NULL, "
        "title_sort_key nvarchar(834) COLLATE Latin1_General_100_BIN2 NOT NULL, "
        "isbn varchar(32) NULL, "
        "authors_json nvarchar(max) NOT NULL, published_year smallint NULL, "
        "created_at datetime2 NOT NULL CONSTRAINT DF_core_books_created_at "
        "DEFAULT SYSUTCDATETIME(), updated_at datetime2 NOT NULL "
        "CONSTRAINT DF_core_books_updated_at DEFAULT SYSUTCDATETIME(), "
        "CONSTRAINT UQ_core_books_organization_book UNIQUE (organization_id, book_id), "
        "CONSTRAINT FK_core_books_organization FOREIGN KEY (organization_id) REFERENCES core.organizations (organization_id), "
        "CONSTRAINT CK_core_books_authors_json CHECK (ISJSON(authors_json) = 1), "
        "CONSTRAINT CK_core_books_published_year CHECK "
        "(published_year IS NULL OR published_year BETWEEN 1 AND 9999))"
    )
    op.execute(
        "CREATE INDEX IX_core_books_tenant_title ON core.books "
        "(organization_id, title_sort_key, book_id)"
    )
    op.execute(
        "CREATE INDEX IX_core_books_tenant_isbn ON core.books "
        "(organization_id, isbn, book_id)"
    )
    _add_tenant_predicates("core.books")


def downgrade() -> None:
    """Remove the catalog table only after removing every attached RLS predicate."""
    _drop_tenant_predicates("core.books")
    op.execute("DROP TABLE core.books")
