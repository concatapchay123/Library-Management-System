"""Static SQL contracts and unit tests for the BE-025 notifications migration."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest


def test_notifications_migration_declares_tenant_controls_and_composite_fks() -> None:
    migration = (
        Path(__file__).resolve().parents[3]
        / "migrations"
        / "versions"
        / "0019_notifications.py"
    ).read_text(encoding="utf-8")

    assert "CREATE TABLE core.notifications" in migration
    assert "CONSTRAINT PK_core_notifications PRIMARY KEY" in migration
    assert (
        "CONSTRAINT UQ_core_notifications_organization_notification UNIQUE (organization_id, notification_id)"
        in migration
    )
    assert (
        "CONSTRAINT FK_core_notifications_organization FOREIGN KEY (organization_id)"
        " REFERENCES core.organizations (organization_id)" in migration
    )
    assert (
        "CONSTRAINT FK_core_notifications_user FOREIGN KEY (organization_id, user_id)"
        " REFERENCES core.users (organization_id, user_id)" in migration
    )
    assert (
        "CONSTRAINT FK_core_notifications_outbox_events FOREIGN KEY (organization_id, outbox_event_id)"
        " REFERENCES ops.outbox_events (organization_id, event_id)" in migration
    )
    assert "IX_core_notifications_inbox" in migration
    assert "UQ_core_notifications_event_user" in migration
    assert '_add_tenant_predicates("core.notifications")' in migration


def test_notifications_downgrade_removes_predicates_and_drops_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = import_module("migrations.versions.0019_notifications")
    statements: list[str] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration.downgrade()

    assert statements == [
        "DROP INDEX UQ_core_notifications_event_user ON core.notifications",
        "DROP INDEX IX_core_notifications_inbox ON core.notifications",
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "DROP FILTER PREDICATE ON core.notifications",
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "DROP BLOCK PREDICATE ON core.notifications AFTER INSERT",
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "DROP BLOCK PREDICATE ON core.notifications AFTER UPDATE",
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "DROP BLOCK PREDICATE ON core.notifications BEFORE DELETE",
        "DROP TABLE core.notifications",
    ]
