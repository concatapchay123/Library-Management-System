"""Static SQL contracts and unit tests for the BE-016 loans migration."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest


def test_loans_migration_declares_tenant_controls_and_composite_fks() -> None:
    migration = (
        Path(__file__).resolve().parents[3]
        / "migrations"
        / "versions"
        / "0012_loans.py"
    ).read_text(encoding="utf-8")

    assert "CREATE TABLE core.loans" in migration
    assert "CONSTRAINT PK_core_loans PRIMARY KEY" in migration
    assert (
        "CONSTRAINT UQ_core_loans_organization_loan UNIQUE (organization_id, loan_id)"
        in migration
    )
    assert (
        "CONSTRAINT FK_core_loans_organization FOREIGN KEY (organization_id)"
        " REFERENCES core.organizations (organization_id)" in migration
    )
    assert (
        "CONSTRAINT FK_core_loans_copy FOREIGN KEY (organization_id, copy_id)"
        " REFERENCES core.book_copies (organization_id, copy_id)" in migration
    )
    assert (
        "CONSTRAINT FK_core_loans_borrower FOREIGN KEY (organization_id, borrower_user_id)"
        " REFERENCES core.users (organization_id, user_id)" in migration
    )
    assert "CREATE UNIQUE INDEX UQ_core_loans_active_copy ON core.loans" in migration
    assert "(organization_id, copy_id) WHERE status = 'checked_out'" in migration
    assert "IX_core_loans_tenant_copy_status" in migration
    assert "IX_core_loans_tenant_borrower_status" in migration
    assert "IX_core_loans_tenant_due_status" in migration
    assert '_add_tenant_predicates("core.loans")' in migration


def test_loans_downgrade_removes_predicates_and_drops_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = import_module("migrations.versions.0012_loans")
    statements: list[str] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration.downgrade()

    assert statements == [
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "DROP FILTER PREDICATE ON core.loans",
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "DROP BLOCK PREDICATE ON core.loans AFTER INSERT",
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "DROP BLOCK PREDICATE ON core.loans AFTER UPDATE",
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "DROP BLOCK PREDICATE ON core.loans BEFORE DELETE",
        "DROP TABLE core.loans",
    ]
