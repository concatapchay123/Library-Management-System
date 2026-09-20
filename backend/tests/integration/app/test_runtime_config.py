"""Runtime configuration boundary tests."""

import os
from collections.abc import Mapping
from pathlib import Path
import subprocess

import pytest

from openlibrary.app.runtime import (
    ConfigurationError,
    RuntimeSettings,
    create_app_from_environ,
    create_app_from_process_environment,
)


def valid_environment() -> dict[str, str]:
    """Return every required configuration value without using a real secret."""
    return {
        "APP_SECRET_KEY": "test-only-secret",
        "DATABASE_MIGRATION_URL": "mssql+pyodbc://migrator@example.test/library",
        "DATABASE_RUNTIME_URL": "mssql+pyodbc://runtime@example.test/library",
        "REDIS_URL": "redis://redis:6379/0",
    }


def without_setting(setting_name: str) -> Mapping[str, str]:
    """Return an otherwise valid environment missing one required setting."""
    environment = valid_environment()
    del environment[setting_name]
    return environment


@pytest.mark.parametrize(
    "setting_name",
    ["APP_SECRET_KEY", "DATABASE_MIGRATION_URL", "DATABASE_RUNTIME_URL", "REDIS_URL"],
)
def test_missing_required_setting_is_rejected(setting_name: str) -> None:
    """The server must not accept requests without a required runtime value."""
    with pytest.raises(ConfigurationError, match=setting_name):
        RuntimeSettings.from_environ(without_setting(setting_name))


def test_blank_required_setting_is_rejected() -> None:
    """Whitespace cannot accidentally turn a required secret into a fallback."""
    environment = valid_environment()
    environment["APP_SECRET_KEY"] = "   "

    with pytest.raises(ConfigurationError, match="APP_SECRET_KEY"):
        RuntimeSettings.from_environ(environment)


def test_non_secret_development_environment_has_a_safe_default() -> None:
    """Only the non-secret environment name receives a default."""
    settings = RuntimeSettings.from_environ(valid_environment())

    assert settings.app_environment == "development"
    assert settings.redis_url == "redis://redis:6379/0"


def test_app_creation_rejects_missing_required_settings_before_requests() -> None:
    """A misconfigured runtime cannot expose even the liveness endpoint."""
    with pytest.raises(ConfigurationError, match="DATABASE_RUNTIME_URL"):
        create_app_from_environ(without_setting("DATABASE_RUNTIME_URL"))


def test_process_environment_entrypoint_uses_the_validated_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The container entrypoint does not bypass runtime configuration validation."""
    for setting_name, value in valid_environment().items():
        monkeypatch.setenv(setting_name, value)

    app = create_app_from_process_environment()

    assert app.test_client().get("/api/v1/health/live").status_code == 200


def test_compose_requires_redis_url() -> None:
    """Compose must not silently replace the documented Redis connection URL."""
    environment = os.environ.copy()
    environment.update(valid_environment())
    environment["MSSQL_SA_PASSWORD"] = "LocalTestPassword!123"
    environment.pop("REDIS_URL", None)
    repository_root = Path(__file__).resolve().parents[4]

    result = subprocess.run(
        ["docker", "compose", "-f", "infra/docker-compose.yml", "config", "--quiet"],
        cwd=repository_root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "REDIS_URL is required" in result.stderr
