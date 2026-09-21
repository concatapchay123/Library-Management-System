"""Validated process configuration for the Flask runtime."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
import json

from flask import Flask

from openlibrary.app.config import AppConfig, ReadinessProbe
from openlibrary.app.factory import create_app
from openlibrary.modules.core.application.access_tokens import (
    AccessTokenService,
    JwtKey,
)
from openlibrary.modules.core.infrastructure.login import create_sqlserver_login_service


class ConfigurationError(ValueError):
    """Raised before application creation when a required setting is absent."""


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    """Runtime settings whose values are supplied by the deployment environment."""

    app_environment: str
    secret_key: str
    database_runtime_url: str
    redis_url: str
    jwt_issuer: str
    jwt_audience: str
    jwt_signing_key_id: str
    jwt_private_key_pem: str
    jwt_public_keys: dict[str, str]
    access_token_ttl_seconds: int

    @classmethod
    def from_environ(cls, environ: Mapping[str, str]) -> "RuntimeSettings":
        """Parse required settings without inventing defaults for sensitive material."""
        signing_key_id = _required(environ, "JWT_SIGNING_KEY_ID")
        public_keys = _public_keys(environ)
        if signing_key_id not in public_keys:
            raise ConfigurationError(
                "JWT_SIGNING_KEY_ID must be included in JWT_PUBLIC_KEYS_JSON"
            )
        return cls(
            app_environment=environ.get("APP_ENV", "development").strip()
            or "development",
            secret_key=_required(environ, "APP_SECRET_KEY"),
            database_runtime_url=_required(environ, "DATABASE_RUNTIME_URL"),
            redis_url=_required(environ, "REDIS_URL"),
            jwt_issuer=_required(environ, "JWT_ISSUER"),
            jwt_audience=_required(environ, "JWT_AUDIENCE"),
            jwt_signing_key_id=signing_key_id,
            jwt_private_key_pem=_required(environ, "JWT_PRIVATE_KEY_PEM"),
            jwt_public_keys=public_keys,
            access_token_ttl_seconds=_positive_int(
                environ, "JWT_ACCESS_TOKEN_TTL_SECONDS"
            ),
        )


@dataclass(frozen=True, slots=True)
class WorkerSettings:
    """The worker's narrow runtime contract excludes HTTP signing credentials."""

    redis_url: str

    @classmethod
    def from_environ(cls, environ: Mapping[str, str]) -> "WorkerSettings":
        """Parse only the worker's broker configuration."""
        return cls(redis_url=_required(environ, "REDIS_URL"))


def create_app_from_environ(
    environ: Mapping[str, str],
    readiness_probe: ReadinessProbe | None = None,
) -> Flask:
    """Create a configured app only after validating the full runtime contract."""
    settings = RuntimeSettings.from_environ(environ)
    app = create_app(
        AppConfig(
            readiness_probe=readiness_probe or _dependencies_are_unverified,
            login_service=create_sqlserver_login_service(settings.database_runtime_url),
            access_tokens=_access_tokens(settings),
        )
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


def _public_keys(environ: Mapping[str, str]) -> dict[str, str]:
    """Parse the configured rotation key ring without accepting loose JSON values."""
    setting_name = "JWT_PUBLIC_KEYS_JSON"
    try:
        raw_keys = json.loads(_required(environ, setting_name))
    except json.JSONDecodeError as error:
        raise ConfigurationError(f"Invalid {setting_name}") from error
    if not isinstance(raw_keys, dict) or not raw_keys:
        raise ConfigurationError(f"Invalid {setting_name}")
    keys: dict[str, str] = {}
    for key_id, key_pem in raw_keys.items():
        if not isinstance(key_id, str) or not key_id.strip():
            raise ConfigurationError(f"Invalid {setting_name}")
        if not isinstance(key_pem, str) or not key_pem.strip():
            raise ConfigurationError(f"Invalid {setting_name}")
        keys[key_id] = key_pem.replace("\\n", "\n")
    return keys


def _positive_int(environ: Mapping[str, str], setting_name: str) -> int:
    try:
        value = int(_required(environ, setting_name))
    except ValueError as error:
        raise ConfigurationError(f"Invalid {setting_name}") from error
    if value <= 0:
        raise ConfigurationError(f"Invalid {setting_name}")
    return value


def _access_tokens(settings: RuntimeSettings) -> AccessTokenService:
    """Build the key ring explicitly so rotation keeps prior verification keys live."""
    signing_key_id = settings.jwt_signing_key_id
    try:
        return AccessTokenService(
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            access_token_ttl=timedelta(seconds=settings.access_token_ttl_seconds),
            signing_key=JwtKey(
                key_id=signing_key_id,
                public_key_pem=settings.jwt_public_keys[signing_key_id].encode(),
                private_key_pem=settings.jwt_private_key_pem.replace(
                    "\\n", "\n"
                ).encode(),
            ),
            verification_keys={
                key_id: public_key.encode()
                for key_id, public_key in settings.jwt_public_keys.items()
            },
        )
    except ValueError as error:
        raise ConfigurationError("Invalid JWT signing configuration") from error


def _dependencies_are_unverified() -> bool:
    """Do not report readiness until the dependency probe is explicitly wired."""
    return False
