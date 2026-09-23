"""Static SQL contracts and unit tests for the BE-017 idempotency keys migration."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest


def test_idempotency_keys_migration_declares_tenant_controls_and_constraints() -> None:
    migration = (
        Path(__file__).resolve().parents[3]
        / "migrations"
        / "versions"
        / "0013_idempotency_keys.py"
    ).read_text(encoding="utf-8")

    assert "CREATE TABLE ops.idempotency_keys" in migration
    assert "CONSTRAINT PK_ops_idempotency_keys PRIMARY KEY" in migration
    assert (
        "CONSTRAINT FK_ops_idempotency_keys_organization FOREIGN KEY (organization_id)"
        " REFERENCES core.organizations (organization_id)" in migration
    )
    assert "CONSTRAINT UQ_ops_idempotency_keys_tenant_key" in migration
    assert "(organization_id, idempotency_key, method, endpoint)" in migration
    assert "IX_ops_idempotency_keys_tenant_expires" in migration
    assert '_add_tenant_predicates("ops.idempotency_keys")' in migration


def test_idempotency_keys_downgrade_removes_predicates_and_drops_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = import_module("migrations.versions.0013_idempotency_keys")
    statements: list[str] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration.downgrade()

    assert statements == [
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "DROP FILTER PREDICATE ON ops.idempotency_keys",
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "DROP BLOCK PREDICATE ON ops.idempotency_keys AFTER INSERT",
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "DROP BLOCK PREDICATE ON ops.idempotency_keys AFTER UPDATE",
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "DROP BLOCK PREDICATE ON ops.idempotency_keys BEFORE DELETE",
        "DROP TABLE ops.idempotency_keys",
    ]
