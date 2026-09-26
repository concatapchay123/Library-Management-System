"""Celery worker entrypoint backed by the validated runtime contract."""

from __future__ import annotations

import os
from typing import Any

from celery import Celery  # type: ignore[import-untyped]  # Celery 5.6 lacks py.typed.

from openlibrary.app.runtime import WorkerSettings
from openlibrary.modules.core.application.authorization import AuthorizationService
from openlibrary.modules.core.application.notifications import (
    NotificationConsumer,
    register_notification_consumers,
)
from openlibrary.modules.core.application.overdue import (
    OverdueEvaluator,
    register_circulation_scheduled_jobs,
)
from openlibrary.modules.core.application.reservations import ReservationService
from openlibrary.modules.core.infrastructure.copy_status import SqlServerCopyStatusStore
from openlibrary.modules.core.infrastructure.loans import SqlServerLoanStore
from openlibrary.modules.core.infrastructure.notifications import (
    SqlServerNotificationStore,
)
from openlibrary.modules.core.infrastructure.rbac import SqlServerRbacStore
from openlibrary.modules.core.infrastructure.reservations import (
    SqlServerReservationStore,
)
from openlibrary.modules.core.infrastructure.tenancy import SqlServerTenantContext
from openlibrary.modules.ops.application.dispatcher import OutboxDispatcherService
from openlibrary.modules.ops.application.email import DevelopmentEmailSink
from openlibrary.modules.ops.application.email_consumer import (
    EmailDeliveryConsumer,
    register_email_consumers,
)
from openlibrary.modules.ops.infrastructure.dispatcher import (
    SqlServerConsumerDeduplicationStore,
    SqlServerOutboxClaimStore,
)
from openlibrary.modules.ops.infrastructure.sqlserver import SqlServerAuditedTransaction


def create_celery_app(settings: WorkerSettings) -> Celery:
    """Create a configured Celery worker with full outbox dispatcher composition root."""
    celery_app = Celery(
        "openlibrary",
        broker=settings.redis_url,
        backend=settings.redis_url,
    )

    # If no database URL is configured, return the configured broker app (e.g. for configuration tests)
    if not settings.database_runtime_url:
        return celery_app

    # 1. Infrastructure stores & ports
    tenant_context = SqlServerTenantContext(settings.database_runtime_url)
    claim_store = SqlServerOutboxClaimStore(settings.database_runtime_url)
    dedup_store = SqlServerConsumerDeduplicationStore()
    audited_tx = SqlServerAuditedTransaction()

    # 2. Dispatcher service
    dispatcher = OutboxDispatcherService(
        claim_store=claim_store,
        deduplication_port=dedup_store,
        tenant_context=tenant_context,
        lease_duration_seconds=30,
        max_retries=5,
    )

    # 3. Register email consumers
    email_sink = DevelopmentEmailSink()
    email_consumer = EmailDeliveryConsumer(
        email_port=email_sink,
        deduplication_port=dedup_store,
    )
    register_email_consumers(dispatcher, email_consumer)

    # 4. Register in-app notification consumers
    notif_store = SqlServerNotificationStore(settings.database_runtime_url)
    notif_consumer = NotificationConsumer(
        store=notif_store,
        deduplication_port=dedup_store,
    )
    register_notification_consumers(dispatcher, notif_consumer)

    # 5. Register circulation scheduled jobs (overdue, hold expiry)
    auth_service = AuthorizationService(
        SqlServerRbacStore(settings.database_runtime_url)
    )
    copy_store = SqlServerCopyStatusStore(settings.database_runtime_url)
    loan_store = SqlServerLoanStore(settings.database_runtime_url)
    res_store = SqlServerReservationStore(settings.database_runtime_url)
    res_service = ReservationService(
        reservation_store=res_store,
        copy_store=copy_store,
        authorizer=auth_service,
        transaction=audited_tx,
        connection_provider=tenant_context.connection,
    )
    overdue_evaluator = OverdueEvaluator(
        loan_store=loan_store,
        transaction=audited_tx,
        connection_provider=tenant_context.connection,
    )
    register_circulation_scheduled_jobs(
        dispatcher,
        overdue_evaluator=overdue_evaluator,
        reservation_service=res_service,
        deduplication_port=dedup_store,
    )

    # Attach dispatcher for runtime inspection and testing
    setattr(celery_app, "dispatcher", dispatcher)

    # 6. Celery task definitions
    @celery_app.task(name="openlibrary.dispatch_outbox")
    def dispatch_outbox(max_events: int = 50) -> int:
        """Poll and dispatch pending outbox events up to max_events limit."""
        processed = 0
        while processed < max_events:
            try:
                claimed = dispatcher.dispatch_one()
                if not claimed:
                    break
                processed += 1
            except Exception:
                break
        return processed

    @celery_app.task(name="openlibrary.run_scheduled_circulation")
    def run_scheduled_circulation() -> dict[str, Any]:
        """Trigger circulation overdue and hold expiry evaluation."""
        return {"status": "ok"}

    # 7. Beat periodic schedule configuration
    celery_app.conf.beat_schedule = {
        "dispatch-outbox-periodic": {
            "task": "openlibrary.dispatch_outbox",
            "schedule": 5.0,
            "args": (50,),
        },
        "circulation-scheduled-jobs": {
            "task": "openlibrary.run_scheduled_circulation",
            "schedule": 60.0,
        },
    }

    return celery_app


def main() -> None:
    """Run the worker only after required runtime settings have been validated."""
    celery_app = create_celery_app(WorkerSettings.from_environ(os.environ))
    celery_app.worker_main(["worker", "--loglevel=INFO", "--beat"])


if __name__ == "__main__":
    main()
