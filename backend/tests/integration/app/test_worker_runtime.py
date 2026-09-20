"""Celery worker configuration tests."""

from openlibrary.app.runtime import RuntimeSettings
from openlibrary.worker import create_celery_app


def test_worker_uses_the_validated_redis_url() -> None:
    """The worker cannot silently select a second broker configuration."""
    settings = RuntimeSettings.from_environ(
        {
            "APP_SECRET_KEY": "test-only-secret",
            "DATABASE_MIGRATION_URL": "mssql+pyodbc://migrator@example.test/library",
            "DATABASE_RUNTIME_URL": "mssql+pyodbc://runtime@example.test/library",
            "REDIS_URL": "redis://redis:6379/0",
        }
    )

    celery_app = create_celery_app(settings)

    assert celery_app.conf.broker_url == "redis://redis:6379/0"
    assert celery_app.conf.result_backend == "redis://redis:6379/0"
