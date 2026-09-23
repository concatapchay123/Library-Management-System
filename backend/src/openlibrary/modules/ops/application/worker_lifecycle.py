"""Worker health, readiness, lifecycle coordination, and reconnect resilience."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
import signal
import time
from typing import Any, TypeVar

from sqlalchemy import create_engine, text

from openlibrary.modules.ops.application.metrics import (
    QueueMetrics,
    QueueMetricsStore,
)


_LOGGER = logging.getLogger(__name__)
T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class WorkerHealthStatus:
    """Aggregated worker health status and queue metrics."""

    status: str
    database_connected: bool
    broker_connected: bool
    queue_metrics: QueueMetrics
    uptime_seconds: float = 0.0
    active_workers: int = 1

    def to_dict(self) -> dict[str, Any]:
        """Convert status to a JSON-compatible dictionary."""
        return {
            "status": self.status,
            "database_connected": self.database_connected,
            "broker_connected": self.broker_connected,
            "queue_metrics": self.queue_metrics.to_dict(),
            "uptime_seconds": round(self.uptime_seconds, 2),
            "active_workers": self.active_workers,
        }


class WorkerHealthService:
    """Evaluates database, broker connectivity, and queue health."""

    def __init__(
        self,
        *,
        database_url: str,
        redis_url: str,
        metrics_store: QueueMetricsStore | None = None,
        database_probe: Callable[[], bool] | None = None,
        broker_probe: Callable[[], bool] | None = None,
        start_time: float | None = None,
    ) -> None:
        self._database_url = database_url
        self._redis_url = redis_url
        self._metrics_store = metrics_store
        self._database_probe = database_probe
        self._broker_probe = broker_probe
        self._start_time = start_time or time.time()

    def check_health(self) -> WorkerHealthStatus:
        """Run connectivity checks and aggregate queue observability."""
        db_ok = self._check_database()
        broker_ok = self._check_broker()

        metrics = (
            self._metrics_store.get_queue_metrics()
            if self._metrics_store is not None
            else QueueMetrics(0, 0, 0, 0, 0)
        )

        if not db_ok or not broker_ok:
            status = "unavailable"
        elif metrics.dead_letter_count > 0:
            status = "degraded"
        else:
            status = "ok"

        uptime = max(0.0, time.time() - self._start_time)
        return WorkerHealthStatus(
            status=status,
            database_connected=db_ok,
            broker_connected=broker_ok,
            queue_metrics=metrics,
            uptime_seconds=uptime,
        )

    def _check_database(self) -> bool:
        if self._database_probe is not None:
            try:
                return bool(self._database_probe())
            except Exception as exc:
                _LOGGER.warning("Database probe raised: %s", exc)
                return False

        try:
            engine = create_engine(self._database_url)
            try:
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                    return True
            finally:
                engine.dispose()
        except Exception as exc:
            _LOGGER.warning("Database connection health check failed: %s", exc)
            return False

    def _check_broker(self) -> bool:
        if self._broker_probe is not None:
            try:
                return bool(self._broker_probe())
            except Exception as exc:
                _LOGGER.warning("Broker probe raised: %s", exc)
                return False

        try:
            import redis

            client = redis.Redis.from_url(
                self._redis_url, socket_timeout=2.0, socket_connect_timeout=2.0
            )
            try:
                return bool(client.ping())
            finally:
                client.close()
        except Exception as exc:
            _LOGGER.warning("Redis broker health check failed: %s", exc)
            return False


class WorkerGracefulShutdown:
    """Coordinates graceful worker shutdown upon termination signals."""

    def __init__(self) -> None:
        self._running: bool = True
        self._shutdown_requested_at: float | None = None

    def install_signal_handlers(self) -> None:
        """Attach SIGTERM and SIGINT signal listeners if in main thread."""
        try:
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGINT, self._signal_handler)
        except (ValueError, AttributeError):
            pass

    def _signal_handler(self, signum: int, frame: Any) -> None:
        _LOGGER.info("Received termination signal %s; initiating shutdown.", signum)
        self.request_shutdown()

    def request_shutdown(self) -> None:
        """Mark worker state as stopping."""
        self._running = False
        if self._shutdown_requested_at is None:
            self._shutdown_requested_at = time.time()

    def is_running(self) -> bool:
        """Check whether the worker loop should continue claiming jobs."""
        return self._running


class WorkerReconnectPolicy:
    """Executes operations with bounded exponential backoff against transient disconnections."""

    def __init__(
        self,
        max_attempts: int = 5,
        base_delay_seconds: float = 0.5,
        max_delay_seconds: float = 10.0,
    ) -> None:
        self._max_attempts = max_attempts
        self._base_delay_seconds = base_delay_seconds
        self._max_delay_seconds = max_delay_seconds

    def execute_with_retry(
        self,
        operation: Callable[[], T],
        *,
        on_retry: Callable[[Exception, int, float], None] | None = None,
    ) -> T:
        """Execute operation and retry on ConnectionError / TimeoutError."""
        attempt = 0
        while True:
            attempt += 1
            try:
                return operation()
            except (ConnectionError, TimeoutError, OSError) as exc:
                if attempt >= self._max_attempts:
                    _LOGGER.error(
                        "Reconnect policy exhausted after %s attempts: %s",
                        attempt,
                        exc,
                    )
                    raise
                delay = min(
                    self._base_delay_seconds * (2 ** (attempt - 1)),
                    self._max_delay_seconds,
                )
                if on_retry:
                    on_retry(exc, attempt, delay)
                else:
                    _LOGGER.warning(
                        "Transient failure on attempt %s/%s (%s). Retrying in %.2fs...",
                        attempt,
                        self._max_attempts,
                        exc,
                        delay,
                    )
                time.sleep(delay)
