"""Static SQL contracts for the BE-010 tenant RBAC migration."""

from __future__ import annotations

from pathlib import Path


def test_rbac_migration_declares_composite_tenant_constraints_and_rls() -> None:
    """Every tenant RBAC relation has composite foreign keys and all RLS predicates."""
    migration = (
        Path(__file__).resolve().parents[3] / "migrations" / "versions" / "0006_rbac.py"
    ).read_text(encoding="utf-8")

    for table in ("roles", "permissions", "user_roles", "role_permissions"):
        assert f'_add_tenant_predicates("core.{table}")' in migration
    assert "REFERENCES core.users (organization_id, user_id)" in migration
    assert "REFERENCES core.roles (organization_id, role_id)" in migration
    assert "REFERENCES core.permissions (organization_id, permission_id)" in migration
