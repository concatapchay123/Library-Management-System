"""Validated process configuration for the Flask runtime."""

import os
from collections.abc import Mapping
from dataclasses import dataclass

from flask import Flask

from openlibrary.app.config import AppConfig, ReadinessProbe
from openlibrary.app.factory import create_app


class ConfigurationError(ValueError):
    """Raised before application creation when a required setting is absent."""


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    """Runtime settings whose values are supplied by the deployment environment."""

    app_environment: str
    secret_key: str
    database_runtime_url: str
    redis_url: str

    @classmethod
    def from_environ(cls, environ: Mapping[str, str]) -> "RuntimeSettings":
        """Parse required settings without inventing defaults for sensitive material."""
        return cls(
            app_environment=environ.get("APP_ENV", "development").strip()
            or "development",
            secret_key=_required(environ, "APP_SECRET_KEY"),
            database_runtime_url=_required(environ, "DATABASE_RUNTIME_URL"),
            redis_url=_required(environ, "REDIS_URL"),
        )


def create_app_from_environ(
    environ: Mapping[str, str],
    readiness_probe: ReadinessProbe | None = None,
) -> Flask:
    """Create a configured app only after validating the full runtime contract."""
    settings = RuntimeSettings.from_environ(environ)
    app = create_app(
        AppConfig(readiness_probe=readiness_probe or _dependencies_are_unverified)
    )
    app.config.update(
        APP_ENV=settings.app_environment,
        DATABASE_RUNTIME_URL=settings.database_runtime_url,
        REDIS_URL=settings.redis_url,
        SECRET_KEY=settings.secret_key,
    )
    return app


def create_app_from_process_environment() -> Flask:
    """Create the container application from its process environment."""
    return create_app_from_environ(os.environ)


def _required(environ: Mapping[str, str], setting_name: str) -> str:
    value = environ.get(setting_name, "").strip()
    if not value:
        raise ConfigurationError(f"Missing required setting: {setting_name}")
    return value


def _dependencies_are_unverified() -> bool:
    """Do not report readiness until the dependency probe is explicitly wired."""
    return False
