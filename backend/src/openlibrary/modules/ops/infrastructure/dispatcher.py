"""SQL Server implementation of the outbox dispatcher and deduplication ports."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

from openlibrary.modules.core.infrastructure.organizations import set_tenant_context
from openlibrary.modules.ops.application.persistence import (
    ClaimedOutboxEvent,
    JobRecord,
)


class SqlServerOutboxClaimStore:
    """SQL Server adapter for pre-context outbox claiming and status transitions."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def claim_next_event(
        self,
        *,
        lease_token: UUID,
        lease_duration_seconds: int = 30,
    ) -> ClaimedOutboxEvent | None:
        """Execute ops.claim_outbox_event before tenant context exists."""
        engine = create_engine(self._database_url)
        try:
            with engine.connect() as connection:
                row = connection.execute(
                    text("EXEC ops.claim_outbox_event :lease_token, :lease_seconds"),
                    {
                        "lease_token": str(lease_token),
                        "lease_seconds": lease_duration_seconds,
                    },
                ).fetchone()
                connection.commit()
                if row is None:
                    return None
                return ClaimedOutboxEvent(
                    event_id=UUID(str(row.event_id)),
                    organization_id=UUID(str(row.organization_id)),
                    event_type=str(row.event_type),
                    aggregate_type=str(row.aggregate_type),
                    aggregate_id=UUID(str(row.aggregate_id)),
                    payload_version=int(row.payload_version),
                    payload_json=str(row.payload_json),
                    correlation_id=UUID(str(row.correlation_id)),
                    idempotency_key=str(row.idempotency_key),
                    attempts=int(row.attempts),
                    lease_token=UUID(str(row.lease_token)),
                    lease_expires_at=row.lease_expires_at,
                    created_at=row.created_at,
                )
        finally:
            engine.dispose()

    def mark_delivered(
        self,
        *,
        event_id: UUID,
        lease_token: UUID,
        organization_id: UUID | None = None,
    ) -> bool:
        """Mark outbox event delivered and release the lease."""
        engine = create_engine(self._database_url)
        try:
            with engine.connect() as connection:
                if organization_id is not None:
                    set_tenant_context(connection, organization_id)
                result = connection.execute(
                    text(
                        "UPDATE ops.outbox_events "
                        "SET delivered_at = SYSUTCDATETIME(), "
                        "lease_token = NULL, "
                        "lease_expires_at = NULL "
                        "WHERE event_id = :event_id AND lease_token = :lease_token"
                    ),
                    {
                        "event_id": str(event_id),
                        "lease_token": str(lease_token),
                    },
                )
                connection.commit()
                return result.rowcount > 0
        finally:
            engine.dispose()

    def record_failure(
        self,
        *,
        event_id: UUID,
        lease_token: UUID,
        error_message: str,
        retry_delay_seconds: int = 0,
        is_dead_letter: bool = False,
        organization_id: UUID | None = None,
    ) -> None:
        """Update retry schedule or transition event into dead-letter state."""
        engine = create_engine(self._database_url)
        try:
            with engine.connect() as connection:
                if organization_id is not None:
                    set_tenant_context(connection, organization_id)
                if is_dead_letter:
                    connection.execute(
                        text(
                            "UPDATE ops.outbox_events "
                            "SET dead_lettered_at = SYSUTCDATETIME(), "
                            "lease_token = NULL, "
                            "lease_expires_at = NULL, "
                            "last_error = :error_message "
                            "WHERE event_id = :event_id AND lease_token = :lease_token"
                        ),
                        {
                            "event_id": str(event_id),
                            "lease_token": str(lease_token),
                            "error_message": error_message,
                        },
                    )
                else:
                    connection.execute(
                        text(
                            "UPDATE ops.outbox_events "
                            "SET available_at = DATEADD(second, :delay, SYSUTCDATETIME()), "
                            "lease_token = NULL, "
                            "lease_expires_at = NULL, "
                            "last_error = :error_message "
                            "WHERE event_id = :event_id AND lease_token = :lease_token"
                        ),
                        {
                            "event_id": str(event_id),
                            "lease_token": str(lease_token),
                            "delay": retry_delay_seconds,
                            "error_message": error_message,
                        },
                    )
                connection.commit()
        finally:
            engine.dispose()


class SqlServerConsumerDeduplicationStore:
    """SQL Server adapter for recording consumer idempotency in ops.job_records."""

    def is_processed(
        self,
        connection: Connection,
        *,
        organization_id: UUID,
        outbox_event_id: UUID,
        job_type: str,
        deduplication_key: str | None = None,
    ) -> bool:
        """Check if job_records indicates completion for this event and job type."""
        row = connection.execute(
            text(
                "SELECT status FROM ops.job_records "
                "WHERE organization_id = :organization_id "
                "AND outbox_event_id = :outbox_event_id "
                "AND job_type = :job_type"
            ),
            {
                "organization_id": str(organization_id),
                "outbox_event_id": str(outbox_event_id),
                "job_type": job_type,
            },
        ).fetchone()
        if row is None:
            return False
        return str(row.status) == "completed"

    def record_processed(
        self,
        connection: Connection,
        *,
        organization_id: UUID,
        outbox_event_id: UUID,
        job_type: str,
        payload_version: int,
        deduplication_key: str | None = None,
    ) -> JobRecord:
        """Record completed status for consumer side effect idempotency."""
        return self.record_job_status(
            connection,
            organization_id=organization_id,
            outbox_event_id=outbox_event_id,
            job_type=job_type,
            payload_version=payload_version,
            status="completed",
            attempts=1,
        )

    def record_job_status(
        self,
        connection: Connection,
        *,
        organization_id: UUID,
        outbox_event_id: UUID,
        job_type: str,
        payload_version: int,
        status: str,
        attempts: int,
        next_run_at: datetime | None = None,
        last_error: str | None = None,
    ) -> JobRecord:
        """Upsert a job record in ops.job_records within tenant context."""
        connection.execute(
            text(
                "MERGE ops.job_records AS target "
                "USING (SELECT :job_id AS job_id, :organization_id AS organization_id, "
                ":outbox_event_id AS outbox_event_id, :job_type AS job_type, "
                ":payload_version AS payload_version, :status AS status, "
                ":attempts AS attempts, :next_run_at AS next_run_at, "
                ":last_error AS last_error, SYSUTCDATETIME() AS now) AS src "
                "ON target.organization_id = src.organization_id "
                "AND target.outbox_event_id = src.outbox_event_id "
                "AND target.job_type = src.job_type "
                "WHEN MATCHED THEN "
                "  UPDATE SET status = src.status, attempts = src.attempts, "
                "  next_run_at = src.next_run_at, last_error = src.last_error, "
                "  updated_at = src.now "
                "WHEN NOT MATCHED THEN "
                "  INSERT (job_id, organization_id, outbox_event_id, job_type, "
                "  payload_version, status, attempts, next_run_at, last_error, created_at, updated_at) "
                "  VALUES (src.job_id, src.organization_id, src.outbox_event_id, src.job_type, "
                "  src.payload_version, src.status, src.attempts, src.next_run_at, src.last_error, src.now, src.now);"
            ),
            {
                "job_id": str(uuid4()),
                "organization_id": str(organization_id),
                "outbox_event_id": str(outbox_event_id),
                "job_type": job_type,
                "payload_version": payload_version,
                "status": status,
                "attempts": attempts,
                "next_run_at": next_run_at,
                "last_error": last_error,
            },
        )
        return self._get_job_record(
            connection, organization_id, outbox_event_id, job_type
        )

    def _get_job_record(
        self,
        connection: Connection,
        organization_id: UUID,
        outbox_event_id: UUID,
        job_type: str,
    ) -> JobRecord:
        row = connection.execute(
            text(
                "SELECT job_id, organization_id, outbox_event_id, job_type, "
                "payload_version, status, attempts, next_run_at, last_error, "
                "created_at, updated_at "
                "FROM ops.job_records "
                "WHERE organization_id = :organization_id "
                "AND outbox_event_id = :outbox_event_id "
                "AND job_type = :job_type"
            ),
            {
                "organization_id": str(organization_id),
                "outbox_event_id": str(outbox_event_id),
                "job_type": job_type,
            },
        ).fetchone()
        if row is None:
            raise LookupError(
                f"Job record not found for outbox event {outbox_event_id} and job type {job_type}"
            )
        return JobRecord(
            job_id=UUID(str(row.job_id)),
            organization_id=UUID(str(row.organization_id)),
            outbox_event_id=UUID(str(row.outbox_event_id)),
            job_type=str(row.job_type),
            payload_version=int(row.payload_version),
            status=str(row.status),
            attempts=int(row.attempts),
            next_run_at=row.next_run_at,
            last_error=row.last_error,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
