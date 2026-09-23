"""SQL Server persistence for queue metrics and dead-letter visibility."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import create_engine, text

from openlibrary.modules.core.infrastructure.organizations import set_tenant_context
from openlibrary.modules.ops.application.metrics import (
    FailedJobDetail,
    QueueMetrics,
    QueueMetricsStore,
)


def _parse_dt(val: object) -> datetime:
    if isinstance(val, datetime):
        return val
    return datetime.fromisoformat(str(val))


class SqlServerQueueMetricsStore(QueueMetricsStore):
    """Execute parameterized metrics queries against ops.outbox_events and ops.job_records."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def get_queue_metrics(self, *, organization_id: UUID | None = None) -> QueueMetrics:
        """Query queue status counts across tenants or scoped to one tenant."""
        engine = create_engine(self._database_url)
        try:
            with engine.connect() as connection:
                if organization_id is not None:
                    set_tenant_context(connection, organization_id)
                org_clause = ""
                params: dict[str, object] = {}
                if organization_id is not None:
                    org_clause = "WHERE organization_id = :org_id"
                    params["org_id"] = str(organization_id)

                sql = f"""
                SELECT
                    SUM(CASE WHEN delivered_at IS NULL AND dead_lettered_at IS NULL
                             AND (lease_expires_at IS NULL OR lease_expires_at <= SYSUTCDATETIME())
                             AND (available_at IS NULL OR available_at <= SYSUTCDATETIME())
                             THEN 1 ELSE 0 END) AS pending_count,
                    SUM(CASE WHEN delivered_at IS NULL AND dead_lettered_at IS NULL
                             AND lease_expires_at > SYSUTCDATETIME()
                             THEN 1 ELSE 0 END) AS in_flight_count,
                    SUM(CASE WHEN dead_lettered_at IS NOT NULL THEN 1 ELSE 0 END) AS dead_letter_count,
                    SUM(CASE WHEN delivered_at IS NOT NULL THEN 1 ELSE 0 END) AS delivered_count
                FROM ops.outbox_events
                {org_clause}
                """
                outbox_row = connection.execute(text(sql), params).fetchone()

                job_org_clause = ""
                if organization_id is not None:
                    job_org_clause = "WHERE organization_id = :org_id"

                job_sql = f"""
                SELECT COUNT(1) AS failed_count
                FROM ops.job_records
                {job_org_clause}
                {"AND" if job_org_clause else "WHERE"} status IN ('failed', 'dead_letter')
                """
                job_row = connection.execute(text(job_sql), params).fetchone()

                pending = int(outbox_row.pending_count or 0) if outbox_row else 0
                in_flight = int(outbox_row.in_flight_count or 0) if outbox_row else 0
                dead_letter = (
                    int(outbox_row.dead_letter_count or 0) if outbox_row else 0
                )
                delivered = int(outbox_row.delivered_count or 0) if outbox_row else 0
                failed_jobs = int(job_row.failed_count or 0) if job_row else 0

                return QueueMetrics(
                    pending_count=pending,
                    in_flight_count=in_flight,
                    dead_letter_count=dead_letter,
                    delivered_count=delivered,
                    failed_jobs_count=failed_jobs,
                )
        finally:
            engine.dispose()

    def get_dead_letter_jobs(
        self, *, organization_id: UUID | None = None, limit: int = 50
    ) -> list[FailedJobDetail]:
        """Fetch dead-lettered job details for operational diagnosis."""
        engine = create_engine(self._database_url)
        try:
            with engine.connect() as connection:
                if organization_id is not None:
                    set_tenant_context(connection, organization_id)
                params: dict[str, object] = {"limit": limit}
                org_clause = ""
                if organization_id is not None:
                    org_clause = "AND organization_id = :org_id"
                    params["org_id"] = str(organization_id)

                sql = f"""
                SELECT TOP (:limit)
                    job_id, outbox_event_id, job_type, status, attempts,
                    last_error, updated_at
                FROM ops.job_records
                WHERE status IN ('failed', 'dead_letter')
                {org_clause}
                ORDER BY updated_at DESC
                """
                rows = connection.execute(text(sql), params).fetchall()
                results: list[FailedJobDetail] = []
                for row in rows:
                    results.append(
                        FailedJobDetail(
                            job_id=UUID(str(row.job_id)),
                            outbox_event_id=UUID(str(row.outbox_event_id)),
                            job_type=str(row.job_type),
                            status=str(row.status),
                            attempts=int(row.attempts),
                            last_error=str(row.last_error) if row.last_error else None,
                            updated_at=_parse_dt(row.updated_at),
                        )
                    )
                return results
        finally:
            engine.dispose()
