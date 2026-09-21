"""Unit coverage for BE-007 tenant-security migration helpers."""

from importlib import import_module

import pytest


def test_users_profiles_policy_helper_adds_filter_and_every_block_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A new tenant table must receive complete RLS protection at creation."""
    migration = import_module("migrations.versions.0004_users_profiles")
    statements: list[str] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration._add_tenant_predicates("core.users")

    assert statements == [
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "ADD FILTER PREDICATE core.tenant_access_predicate(organization_id) "
        "ON core.users",
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "ADD BLOCK PREDICATE core.tenant_access_predicate(organization_id) "
        "ON core.users AFTER INSERT",
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "ADD BLOCK PREDICATE core.tenant_access_predicate(organization_id) "
        "ON core.users AFTER UPDATE",
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "ADD BLOCK PREDICATE core.tenant_access_predicate(organization_id) "
        "ON core.users BEFORE DELETE",
    ]
