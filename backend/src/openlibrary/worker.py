"""Celery worker entrypoint backed by the validated runtime contract."""

import os

from celery import Celery  # type: ignore[import-untyped]  # Celery 5.6 lacks py.typed.

from openlibrary.app.runtime import RuntimeSettings


def create_celery_app(settings: RuntimeSettings) -> Celery:
    """Create a worker using the same Redis setting as the HTTP runtime."""
    return Celery(
        "openlibrary",
        broker=settings.redis_url,
        backend=settings.redis_url,
    )


def main() -> None:
    """Run the worker only after required runtime settings have been validated."""
    celery_app = create_celery_app(RuntimeSettings.from_environ(os.environ))
    celery_app.worker_main(["worker", "--loglevel=INFO"])


if __name__ == "__main__":
    main()
