"""Create durable dispatcher claim metadata, job records, and atomic claim procedure.

Revision ID: 0011_outbox_claim_jobs
Revises: 0010_copy_status_history
Create Date: 2026-09-23
"""

from alembic import context, op


revision = "0011_outbox_claim_jobs"
down_revision = "0010_copy_status_history"
branch_labels = None
depends_on = None


def _add_tenant_predicates(table_name: str) -> None:
    """Attach every data operation to the shared fail-closed tenant policy."""
    op.execute(
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "ADD FILTER PREDICATE core.tenant_access_predicate(organization_id) "
        f"ON {table_name}"
    )
    for operation in ("AFTER INSERT", "AFTER UPDATE", "BEFORE DELETE"):
        op.execute(
            "ALTER SECURITY POLICY core.organization_tenant_policy "
            "ADD BLOCK PREDICATE core.tenant_access_predicate(organization_id) "
            f"ON {table_name} {operation}"
        )


def _drop_tenant_predicates(table_name: str) -> None:
    """Detach all predicates before dropping a tenant-owned table."""
    op.execute(
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        f"DROP FILTER PREDICATE ON {table_name}"
    )
    for operation in ("AFTER INSERT", "AFTER UPDATE", "BEFORE DELETE"):
        op.execute(
            "ALTER SECURITY POLICY core.organization_tenant_policy "
            f"DROP BLOCK PREDICATE ON {table_name} {operation}"
        )


def upgrade() -> None:
    """Add claim metadata to outbox, create job records, and deploy atomic claim procedure."""
    runtime_login = context.config.attributes["runtime_login"]

    op.execute(
        "ALTER TABLE ops.outbox_events ADD "
        "lease_token uniqueidentifier NULL, "
        "lease_expires_at datetime2(3) NULL, "
        "attempts int NOT NULL "
        "CONSTRAINT DF_ops_outbox_events_attempts DEFAULT 0, "
        "available_at datetime2(3) NOT NULL "
        "CONSTRAINT DF_ops_outbox_events_available_at DEFAULT SYSUTCDATETIME(), "
        "delivered_at datetime2(3) NULL, "
        "dead_lettered_at datetime2(3) NULL, "
        "last_error nvarchar(max) NULL, "
        "CONSTRAINT UQ_ops_outbox_events_organization_event UNIQUE (organization_id, event_id)"
    )
    op.execute(
        "CREATE INDEX IX_ops_outbox_events_claim "
        "ON ops.outbox_events (available_at, created_at) "
        "WHERE delivered_at IS NULL AND dead_lettered_at IS NULL"
    )

    op.execute(
        "CREATE TABLE ops.job_records ("
        "job_id uniqueidentifier NOT NULL "
        "CONSTRAINT PK_ops_job_records PRIMARY KEY, "
        "organization_id uniqueidentifier NOT NULL, "
        "outbox_event_id uniqueidentifier NOT NULL, "
        "job_type varchar(128) NOT NULL, "
        "payload_version smallint NOT NULL "
        "CONSTRAINT CK_ops_job_records_payload_version CHECK (payload_version > 0), "
        "status varchar(32) NOT NULL "
        "CONSTRAINT CK_ops_job_records_status CHECK (status IN ('pending', 'processing', 'completed', 'dead_letter', 'failed')), "
        "attempts int NOT NULL "
        "CONSTRAINT DF_ops_job_records_attempts DEFAULT 0, "
        "next_run_at datetime2(3) NULL, "
        "last_error nvarchar(max) NULL, "
        "created_at datetime2(3) NOT NULL "
        "CONSTRAINT DF_ops_job_records_created_at DEFAULT SYSUTCDATETIME(), "
        "updated_at datetime2(3) NOT NULL "
        "CONSTRAINT DF_ops_job_records_updated_at DEFAULT SYSUTCDATETIME(), "
        "CONSTRAINT FK_ops_job_records_organization FOREIGN KEY (organization_id) "
        "REFERENCES core.organizations (organization_id), "
        "CONSTRAINT FK_ops_job_records_outbox_events FOREIGN KEY (organization_id, outbox_event_id) "
        "REFERENCES ops.outbox_events (organization_id, event_id), "
        "CONSTRAINT UQ_ops_job_records_organization_job UNIQUE (organization_id, job_id), "
        "CONSTRAINT UQ_ops_job_records_tenant_event_job UNIQUE (organization_id, outbox_event_id, job_type)"
        ")"
    )
    op.execute(
        "CREATE INDEX IX_ops_job_records_organization_status "
        "ON ops.job_records (organization_id, status, next_run_at)"
    )
    _add_tenant_predicates("ops.job_records")

    op.execute(
        "CREATE PROCEDURE ops.claim_outbox_event "
        "@lease_token uniqueidentifier, "
        "@lease_seconds int = 30 "
        "WITH EXECUTE AS OWNER "
        "AS BEGIN SET NOCOUNT ON; SET XACT_ABORT ON; "
        "WITH NextEvent AS ("
        "SELECT TOP (1) * FROM ops.outbox_events WITH (UPDLOCK, READPAST, ROWLOCK) "
        "WHERE delivered_at IS NULL AND dead_lettered_at IS NULL "
        "AND available_at <= SYSUTCDATETIME() "
        "AND (lease_expires_at IS NULL OR lease_expires_at < SYSUTCDATETIME()) "
        "ORDER BY available_at ASC, created_at ASC) "
        "UPDATE NextEvent SET "
        "lease_token = @lease_token, "
        "lease_expires_at = DATEADD(second, @lease_seconds, SYSUTCDATETIME()), "
        "attempts = attempts + 1 "
        "OUTPUT "
        "inserted.event_id, inserted.organization_id, inserted.event_type, "
        "inserted.aggregate_type, inserted.aggregate_id, inserted.payload_version, "
        "inserted.payload_json, inserted.correlation_id, inserted.idempotency_key, "
        "inserted.attempts, inserted.lease_token, inserted.lease_expires_at, inserted.created_at; "
        "END"
    )
    op.execute(
        "ADD SIGNATURE TO OBJECT::ops.claim_outbox_event "
        "BY CERTIFICATE core_login_resolver_certificate"
    )
    op.execute(f"GRANT EXECUTE ON OBJECT::ops.claim_outbox_event TO [{runtime_login}]")


def downgrade() -> None:
    """Revert dispatcher claim metadata and drop procedure in dependency order."""
    op.execute(
        "DROP SIGNATURE FROM OBJECT::ops.claim_outbox_event "
        "BY CERTIFICATE core_login_resolver_certificate"
    )
    op.execute("DROP PROCEDURE ops.claim_outbox_event")
    _drop_tenant_predicates("ops.job_records")
    op.execute("DROP TABLE ops.job_records")
    op.execute("DROP INDEX IX_ops_outbox_events_claim ON ops.outbox_events")
    op.execute(
        "ALTER TABLE ops.outbox_events "
        "DROP CONSTRAINT UQ_ops_outbox_events_organization_event"
    )
    op.execute(
        "ALTER TABLE ops.outbox_events "
        "DROP CONSTRAINT DF_ops_outbox_events_available_at"
    )
    op.execute(
        "ALTER TABLE ops.outbox_events DROP CONSTRAINT DF_ops_outbox_events_attempts"
    )
    op.execute(
        "ALTER TABLE ops.outbox_events "
        "DROP COLUMN lease_token, lease_expires_at, attempts, available_at, "
        "delivered_at, dead_lettered_at, last_error"
    )
