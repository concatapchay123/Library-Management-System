"""Static SQL contracts for the BE-012 bibliographic catalog migration."""

from __future__ import annotations

from pathlib import Path


def test_books_migration_declares_tenant_controls_and_title_indexes() -> None:
    migration = (
        Path(__file__).resolve().parents[3]
        / "migrations"
        / "versions"
        / "0008_books.py"
    ).read_text(encoding="utf-8")

    assert "CREATE TABLE core.books" in migration
    assert "title_sort_key nvarchar(834)" in migration
    assert "FOREIGN KEY (organization_id) REFERENCES core.organizations" in migration
    assert "UNIQUE (organization_id, book_id)" in migration
    assert "IX_core_books_tenant_title" in migration
    assert "IX_core_books_tenant_isbn" in migration
    assert '_add_tenant_predicates("core.books")' in migration
