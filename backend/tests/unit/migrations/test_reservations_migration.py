"""Static SQL contracts and unit tests for the BE-018 reservations migration."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest


def test_reservations_migration_declares_tenant_controls_and_composite_fks() -> None:
    migration = (
        Path(__file__).resolve().parents[3]
        / "migrations"
        / "versions"
        / "0014_reservations.py"
    ).read_text(encoding="utf-8")

    assert "CREATE TABLE core.reservations" in migration
    assert "CONSTRAINT PK_core_reservations PRIMARY KEY" in migration
    assert (
        "CONSTRAINT UQ_core_reservations_organization_reservation UNIQUE (organization_id, reservation_id)"
        in migration
    )
    assert (
        "CONSTRAINT FK_core_reservations_organization FOREIGN KEY (organization_id)"
        " REFERENCES core.organizations (organization_id)" in migration
    )
    assert (
        "CONSTRAINT FK_core_reservations_book FOREIGN KEY (organization_id, book_id)"
        " REFERENCES core.books (organization_id, book_id)" in migration
    )
    assert (
        "CONSTRAINT FK_core_reservations_requester FOREIGN KEY (organization_id, requester_user_id)"
        " REFERENCES core.users (organization_id, user_id)" in migration
    )
    assert (
        "CONSTRAINT FK_core_reservations_copy FOREIGN KEY (organization_id, copy_id)"
        " REFERENCES core.book_copies (organization_id, copy_id)" in migration
    )
    assert "IX_core_reservations_tenant_book_status" in migration
    assert "IX_core_reservations_tenant_requester_status" in migration
    assert "IX_core_reservations_tenant_hold_expires" in migration
    assert "UQ_core_reservations_held_copy" in migration
    assert '_add_tenant_predicates("core.reservations")' in migration


def test_reservations_downgrade_removes_predicates_and_drops_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = import_module("migrations.versions.0014_reservations")
    statements: list[str] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration.downgrade()

    assert statements == [
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "DROP FILTER PREDICATE ON core.reservations",
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "DROP BLOCK PREDICATE ON core.reservations AFTER INSERT",
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "DROP BLOCK PREDICATE ON core.reservations AFTER UPDATE",
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "DROP BLOCK PREDICATE ON core.reservations BEFORE DELETE",
        "DROP TABLE core.reservations",
    ]
