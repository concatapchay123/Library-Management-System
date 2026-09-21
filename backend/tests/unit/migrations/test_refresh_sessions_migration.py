"""Schema contracts for the BE-009 refresh-session migration."""

from importlib import import_module
from types import SimpleNamespace

import pytest


def test_refresh_session_predicate_helper_covers_filter_and_every_block_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refresh state is tenant data and needs the full shared RLS policy."""
    migration = import_module("migrations.versions.0005_refresh_sessions")
    statements: list[str] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration._add_tenant_predicates("core.refresh_sessions")

    assert statements == [
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "ADD FILTER PREDICATE core.tenant_access_predicate(organization_id) "
        "ON core.refresh_sessions",
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "ADD BLOCK PREDICATE core.tenant_access_predicate(organization_id) "
        "ON core.refresh_sessions AFTER INSERT",
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "ADD BLOCK PREDICATE core.tenant_access_predicate(organization_id) "
        "ON core.refresh_sessions AFTER UPDATE",
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "ADD BLOCK PREDICATE core.tenant_access_predicate(organization_id) "
        "ON core.refresh_sessions BEFORE DELETE",
    ]


def test_refresh_session_schema_uses_hashes_composite_foreign_keys_and_narrow_resolver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A browser secret must never become a durable column or broad pre-auth query."""
    migration = import_module("migrations.versions.0005_refresh_sessions")
    statements: list[str] = []
    monkeypatch.setattr(
        migration.context,
        "config",
        SimpleNamespace(attributes={"runtime_login": "runtime"}),
        raising=False,
    )
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration.upgrade()

    rendered = "\n".join(statements)
    assert "CREATE TABLE core.refresh_sessions" in rendered
    assert "token_hash char(64) NOT NULL" in rendered
    assert "csrf_hash char(64) NOT NULL" in rendered
    assert "refresh_token" not in rendered.casefold()
    assert "UNIQUE (organization_id, session_id)" in rendered
    assert "FOREIGN KEY (organization_id, user_id)" in rendered
    assert "FOREIGN KEY (organization_id, parent_session_id)" in rendered
    assert "UNIQUE INDEX IX_core_refresh_sessions_token_hash" in rendered
    assert (
        "CREATE PROCEDURE core.resolve_refresh_session @token_hash char(64)" in rendered
    )
    assert "WHERE token_hash = @token_hash AND revoked_at IS NULL" in rendered
    assert (
        "GRANT EXECUTE ON OBJECT::core.resolve_refresh_session TO [runtime]" in rendered
    )
