"""Static SQL contracts and unit tests for the BE-022 public library memberships migration."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest


def test_public_library_migration_declares_tenant_controls_and_composite_fks() -> None:
    migration = (
        Path(__file__).resolve().parents[3]
        / "migrations"
        / "versions"
        / "0016_public_library_memberships.py"
    ).read_text(encoding="utf-8")

    # Table 1: membership_plans
    assert "CREATE TABLE public_library.membership_plans" in migration
    assert "CONSTRAINT PK_public_library_membership_plans PRIMARY KEY" in migration
    assert (
        "CONSTRAINT UQ_public_library_plans_org_plan UNIQUE (organization_id, plan_id)"
        in migration
    )
    assert (
        "CONSTRAINT UQ_public_library_plans_org_code UNIQUE (organization_id, code)"
        in migration
    )
    assert (
        "CONSTRAINT FK_public_library_plans_organization FOREIGN KEY (organization_id)"
        in migration
    )
    assert '_add_tenant_predicates("public_library.membership_plans")' in migration

    # Table 2: members
    assert "CREATE TABLE public_library.members" in migration
    assert "CONSTRAINT PK_public_library_members PRIMARY KEY" in migration
    assert (
        "CONSTRAINT UQ_public_library_members_org_member UNIQUE (organization_id, member_id)"
        in migration
    )
    assert (
        "CONSTRAINT UQ_public_library_members_org_user UNIQUE (organization_id, user_id)"
        in migration
    )
    assert (
        "CONSTRAINT UQ_public_library_members_org_number UNIQUE (organization_id, member_number)"
        in migration
    )
    assert (
        "CONSTRAINT FK_public_library_members_organization FOREIGN KEY (organization_id)"
        in migration
    )
    assert (
        "CONSTRAINT FK_public_library_members_user FOREIGN KEY (organization_id, user_id)"
        in migration
    )
    assert '_add_tenant_predicates("public_library.members")' in migration

    # Table 3: subscriptions
    assert "CREATE TABLE public_library.subscriptions" in migration
    assert "CONSTRAINT PK_public_library_subscriptions PRIMARY KEY" in migration
    assert (
        "CONSTRAINT CK_public_library_subscriptions_dates CHECK (starts_at < ends_at)"
        in migration
    )
    assert (
        "CONSTRAINT UQ_public_library_subscriptions_org_sub UNIQUE (organization_id, subscription_id)"
        in migration
    )
    assert (
        "CONSTRAINT FK_public_library_subscriptions_organization FOREIGN KEY (organization_id)"
        in migration
    )
    assert (
        "CONSTRAINT FK_public_library_subscriptions_member FOREIGN KEY (organization_id, member_id)"
        in migration
    )
    assert (
        "CONSTRAINT FK_public_library_subscriptions_plan FOREIGN KEY (organization_id, plan_id)"
        in migration
    )
    assert '_add_tenant_predicates("public_library.subscriptions")' in migration

    # Indexes
    assert "IX_public_library_subscriptions_member_status" in migration
    assert "IX_public_library_members_user" in migration


def test_public_library_downgrade_removes_predicates_and_drops_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = import_module("migrations.versions.0016_public_library_memberships")
    statements: list[str] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration.downgrade()

    # Drops indexes first
    assert (
        "DROP INDEX IX_public_library_members_user ON public_library.members"
        in statements
    )
    assert (
        "DROP INDEX IX_public_library_subscriptions_member_status ON public_library.subscriptions"
        in statements
    )

    # Drops tables in reverse order
    assert "DROP TABLE public_library.subscriptions" in statements
    assert "DROP TABLE public_library.members" in statements
    assert "DROP TABLE public_library.membership_plans" in statements
