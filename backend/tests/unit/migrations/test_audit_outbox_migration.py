"""Unit coverage for reversible BE-005 security-policy migration SQL."""

from importlib import import_module

import pytest


def test_drop_tenant_predicates_removes_every_block_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Downgrade must remove every predicate added for one tenant table."""
    migration = import_module("migrations.versions.0003_audit_outbox")
    statements: list[str] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration._drop_tenant_predicates("ops.audit_events")

    assert statements == [
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "DROP FILTER PREDICATE ON ops.audit_events",
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "DROP BLOCK PREDICATE ON ops.audit_events AFTER INSERT",
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "DROP BLOCK PREDICATE ON ops.audit_events AFTER UPDATE",
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "DROP BLOCK PREDICATE ON ops.audit_events BEFORE DELETE",
    ]
