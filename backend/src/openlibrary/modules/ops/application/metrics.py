"""Queue metrics and dead-letter visibility domain value objects and ports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class QueueMetrics:
    """Aggregated outbox and job execution metrics."""

    pending_count: int
    in_flight_count: int
    dead_letter_count: int
    delivered_count: int
    failed_jobs_count: int

    def to_dict(self) -> dict[str, int]:
        """Convert metrics to a JSON-compatible dictionary."""
        return {
            "pending_count": self.pending_count,
            "in_flight_count": self.in_flight_count,
            "dead_letter_count": self.dead_letter_count,
            "delivered_count": self.delivered_count,
            "failed_jobs_count": self.failed_jobs_count,
        }


@dataclass(frozen=True, slots=True)
class FailedJobDetail:
    """Actionable failure metadata for a dead-letter or failed job."""

    job_id: UUID
    outbox_event_id: UUID
    job_type: str
    status: str
    attempts: int
    last_error: str | None
    updated_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """Convert failed job detail to a JSON-compatible dictionary."""
        return {
            "job_id": str(self.job_id),
            "outbox_event_id": str(self.outbox_event_id),
            "job_type": self.job_type,
            "status": self.status,
            "attempts": self.attempts,
            "last_error": self.last_error,
            "updated_at": self.updated_at.isoformat(),
        }


class QueueMetricsStore(Protocol):
    """Port for querying outbox queue depths and dead-letter failure states."""

    def get_queue_metrics(self, *, organization_id: UUID | None = None) -> QueueMetrics:
        """Calculate active queue depths and status counts."""
        ...

    def get_dead_letter_jobs(
        self, *, organization_id: UUID | None = None, limit: int = 50
    ) -> list[FailedJobDetail]:
        """Fetch recent dead-letter or exhausted job records."""
        ...
