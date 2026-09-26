"""Tests for Celery worker composition root and task registration (C-01)."""

from openlibrary.app.runtime import WorkerSettings
from openlibrary.worker import create_celery_app


def test_worker_settings_reads_database_and_redis() -> None:
    environ = {
        "REDIS_URL": "redis://localhost:6379/0",
        "DATABASE_RUNTIME_URL": "mssql+pyodbc://sa:pass@localhost:1433/db?driver=ODBC+Driver+18",
    }
    settings = WorkerSettings.from_environ(environ)
    assert settings.redis_url == "redis://localhost:6379/0"
    assert "DATABASE_RUNTIME_URL" in dir(settings) or hasattr(
        settings, "database_runtime_url"
    )
    assert settings.database_runtime_url == environ["DATABASE_RUNTIME_URL"]


def test_create_celery_app_registers_tasks_and_dispatcher() -> None:
    environ = {
        "REDIS_URL": "redis://localhost:6379/0",
        "DATABASE_RUNTIME_URL": "mssql+pyodbc://sa:pass@localhost:1433/db?driver=ODBC+Driver+18",
    }
    settings = WorkerSettings.from_environ(environ)
    celery_app = create_celery_app(settings)

    # 1. Celery app has registered tasks
    assert "openlibrary.dispatch_outbox" in celery_app.tasks
    assert "openlibrary.run_scheduled_circulation" in celery_app.tasks

    # 2. Celery beat schedule is configured
    assert celery_app.conf.beat_schedule is not None
    assert "dispatch-outbox-periodic" in celery_app.conf.beat_schedule

    # 3. Worker has dispatcher attribute configured with registered handlers
    assert hasattr(celery_app, "dispatcher")
    dispatcher = celery_app.dispatcher
    assert "circulation.loan_checked_out" in dispatcher._handlers
    assert "circulation.reservation_created" in dispatcher._handlers
    assert "circulation.scheduled_overdue_evaluation" in dispatcher._handlers
