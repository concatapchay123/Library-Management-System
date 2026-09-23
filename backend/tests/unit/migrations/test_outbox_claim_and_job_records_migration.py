"""Static SQL contracts and unit tests for the BE-015 outbox claim and job records migration."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest


def test_outbox_claim_migration_declares_tables_procedure_and_rls() -> None:
    migration = (
        Path(__file__).resolve().parents[3]
        / "migrations"
        / "versions"
        / "0011_outbox_claim_jobs.py"
    ).read_text(encoding="utf-8")

    assert "ALTER TABLE ops.outbox_events ADD" in migration
    assert "lease_token uniqueidentifier NULL" in migration
    assert "lease_expires_at datetime2(3) NULL" in migration
    assert "attempts int NOT NULL" in migration
    assert "available_at datetime2(3) NOT NULL" in migration
    assert "delivered_at datetime2(3) NULL" in migration
    assert "dead_lettered_at datetime2(3) NULL" in migration
    assert "last_error nvarchar(max) NULL" in migration
    assert "CONSTRAINT UQ_ops_outbox_events_organization_event" in migration

    assert "CREATE TABLE ops.job_records" in migration
    assert "CONSTRAINT PK_ops_job_records PRIMARY KEY" in migration
    assert "CONSTRAINT CK_ops_job_records_payload_version CHECK" in migration
    assert "CONSTRAINT CK_ops_job_records_status CHECK" in migration
    assert "CONSTRAINT FK_ops_job_records_organization FOREIGN KEY" in migration
    assert "CONSTRAINT FK_ops_job_records_outbox_events FOREIGN KEY" in migration
    assert "CONSTRAINT UQ_ops_job_records_organization_job" in migration
    assert "CONSTRAINT UQ_ops_job_records_tenant_event_job" in migration
    assert '_add_tenant_predicates("ops.job_records")' in migration

    assert "CREATE PROCEDURE ops.claim_outbox_event" in migration
    assert "WITH EXECUTE AS OWNER" in migration
    assert "UPDLOCK, READPAST, ROWLOCK" in migration
    assert "ADD SIGNATURE TO OBJECT::ops.claim_outbox_event" in migration
    assert "GRANT EXECUTE ON OBJECT::ops.claim_outbox_event" in migration


def test_outbox_claim_downgrade_removes_predicates_and_drops_objects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = import_module("migrations.versions.0011_outbox_claim_jobs")
    statements: list[str] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration.downgrade()

    assert statements == [
        "DROP SIGNATURE FROM OBJECT::ops.claim_outbox_event "
        "BY CERTIFICATE core_login_resolver_certificate",
        "DROP PROCEDURE ops.claim_outbox_event",
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "DROP FILTER PREDICATE ON ops.job_records",
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "DROP BLOCK PREDICATE ON ops.job_records AFTER INSERT",
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "DROP BLOCK PREDICATE ON ops.job_records AFTER UPDATE",
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "DROP BLOCK PREDICATE ON ops.job_records BEFORE DELETE",
        "DROP TABLE ops.job_records",
        "DROP INDEX IX_ops_outbox_events_claim ON ops.outbox_events",
        "ALTER TABLE ops.outbox_events "
        "DROP CONSTRAINT UQ_ops_outbox_events_organization_event",
        "ALTER TABLE ops.outbox_events "
        "DROP CONSTRAINT DF_ops_outbox_events_available_at",
        "ALTER TABLE ops.outbox_events DROP CONSTRAINT DF_ops_outbox_events_attempts",
        "ALTER TABLE ops.outbox_events "
        "DROP COLUMN lease_token, lease_expires_at, attempts, available_at, "
        "delivered_at, dead_lettered_at, last_error",
    ]
