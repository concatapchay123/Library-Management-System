"""Static SQL contracts and unit tests for the BE-014 copy status history migration."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest


def test_copy_status_history_migration_declares_tenant_controls_and_composite_fks() -> (
    None
):
    migration = (
        Path(__file__).resolve().parents[3]
        / "migrations"
        / "versions"
        / "0010_copy_status_history.py"
    ).read_text(encoding="utf-8")

    assert "CREATE TABLE core.copy_status_history" in migration
    assert "CONSTRAINT PK_core_copy_status_history PRIMARY KEY" in migration
    assert (
        "CONSTRAINT UQ_core_copy_status_history_organization_history"
        " UNIQUE (organization_id, history_id)" in migration
    )
    assert (
        "CONSTRAINT FK_core_copy_status_history_organization FOREIGN KEY (organization_id)"
        " REFERENCES core.organizations (organization_id)" in migration
    )
    assert (
        "CONSTRAINT FK_core_copy_status_history_copy FOREIGN KEY (organization_id, copy_id)"
        " REFERENCES core.book_copies (organization_id, copy_id)" in migration
    )
    assert (
        "CONSTRAINT FK_core_copy_status_history_actor FOREIGN KEY (organization_id, actor_id)"
        " REFERENCES core.users (organization_id, user_id)" in migration
    )
    assert "IX_core_copy_status_history_tenant_copy" in migration
    assert "IX_core_copy_status_history_tenant_actor" in migration
    assert '_add_tenant_predicates("core.copy_status_history")' in migration
    assert "DENY UPDATE, DELETE ON OBJECT::core.copy_status_history" in migration


def test_copy_status_history_downgrade_removes_predicates_and_drops_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = import_module("migrations.versions.0010_copy_status_history")
    statements: list[str] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration.downgrade()

    assert statements == [
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "DROP FILTER PREDICATE ON core.copy_status_history",
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "DROP BLOCK PREDICATE ON core.copy_status_history AFTER INSERT",
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "DROP BLOCK PREDICATE ON core.copy_status_history AFTER UPDATE",
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "DROP BLOCK PREDICATE ON core.copy_status_history BEFORE DELETE",
        "DROP TABLE core.copy_status_history",
    ]
