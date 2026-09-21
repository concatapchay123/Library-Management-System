"""Runtime configuration boundary tests."""

import json
import os
from collections.abc import Mapping
from pathlib import Path
import subprocess
import warnings

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy.exc import SAWarning

from openlibrary.app.runtime import (
    ConfigurationError,
    RuntimeSettings,
    create_app_from_environ,
    create_app_from_process_environment,
)


def valid_environment() -> dict[str, str]:
    """Return every required configuration value without using a real secret."""
    private_key_pem, public_key_pem = jwt_key_material()
    return {
        "APP_SECRET_KEY": "test-only-secret",
        "DATABASE_MIGRATION_URL": "mssql+pyodbc://migrator@example.test/library",
        "DATABASE_RUNTIME_URL": "mssql+pyodbc://runtime@example.test/library",
        "REDIS_URL": "redis://redis:6379/0",
        "JWT_ISSUER": "https://identity.openlibraryos.example",
        "JWT_AUDIENCE": "openlibraryos-api",
        "JWT_SIGNING_KEY_ID": "test-key",
        "JWT_PRIVATE_KEY_PEM": private_key_pem,
        "JWT_PUBLIC_KEYS_JSON": json.dumps({"test-key": public_key_pem}),
        "JWT_ACCESS_TOKEN_TTL_SECONDS": "900",
    }


def jwt_key_material() -> tuple[str, str]:
    """Create ephemeral RSA material so startup validation exercises real keys."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_key_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private_key_pem, public_key_pem


def without_setting(setting_name: str) -> Mapping[str, str]:
    """Return an otherwise valid environment missing one required setting."""
    environment = valid_environment()
    del environment[setting_name]
    return environment


@pytest.mark.parametrize(
    "setting_name",
    [
        "APP_SECRET_KEY",
        "DATABASE_RUNTIME_URL",
        "REDIS_URL",
        "JWT_ISSUER",
        "JWT_AUDIENCE",
        "JWT_SIGNING_KEY_ID",
        "JWT_PRIVATE_KEY_PEM",
        "JWT_PUBLIC_KEYS_JSON",
        "JWT_ACCESS_TOKEN_TTL_SECONDS",
    ],
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
    assert settings.access_token_ttl_seconds == 900
    assert set(settings.jwt_public_keys) == {"test-key"}


@pytest.mark.parametrize("value", ["0", "-1", "not-a-number"])
def test_non_positive_or_invalid_access_token_lifetime_is_rejected(value: str) -> None:
    """A runtime must not accidentally issue non-expiring access tokens."""
    environment = valid_environment()
    environment["JWT_ACCESS_TOKEN_TTL_SECONDS"] = value

    with pytest.raises(ConfigurationError, match="JWT_ACCESS_TOKEN_TTL_SECONDS"):
        RuntimeSettings.from_environ(environment)


def test_app_creation_rejects_malformed_or_mismatched_jwt_key_material() -> None:
    """The API process must fail before serving if signing material is unusable."""
    malformed = valid_environment()
    malformed["JWT_PRIVATE_KEY_PEM"] = "not a PEM"
    mismatched = valid_environment()
    _, other_public_key = jwt_key_material()
    mismatched["JWT_PUBLIC_KEYS_JSON"] = json.dumps({"test-key": other_public_key})

    for environment in (malformed, mismatched):
        with pytest.raises(
            ConfigurationError, match="Invalid JWT signing configuration"
        ):
            create_app_from_environ(environment)


def test_runtime_settings_do_not_require_the_migration_credential() -> None:
    """The app process must not receive the migration-only database identity."""
    environment = valid_environment()
    del environment["DATABASE_MIGRATION_URL"]

    settings = RuntimeSettings.from_environ(environment)

    assert (
        settings.database_runtime_url == "mssql+pyodbc://runtime@example.test/library"
    )


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


def test_app_creation_defers_sql_engine_creation_until_login() -> None:
    """Configuration-only startup must not parse or warn about an unopened ODBC URL."""
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        create_app_from_environ(valid_environment())

    assert not [
        warning for warning in captured if issubclass(warning.category, SAWarning)
    ]


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


def test_compose_keeps_migration_credentials_out_of_runtime_services() -> None:
    """The migration profile is the sole Compose path receiving elevated URLs."""
    environment = os.environ.copy()
    environment.update(valid_environment())
    environment.update(
        {
            "DATABASE_BOOTSTRAP_URL": (
                "mssql+pyodbc://sa:LocalTestPassword!123@database:1433/master?"
                "driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&"
                "TrustServerCertificate=yes"
            ),
            "DATABASE_MIGRATION_URL": (
                "mssql+pyodbc://openlibrary_migrator:LocalTestPassword!123@"
                "database:1433/openlibrary?driver=ODBC+Driver+18+for+SQL+Server&"
                "Encrypt=yes&TrustServerCertificate=yes"
            ),
            "DATABASE_RUNTIME_URL": (
                "mssql+pyodbc://openlibrary_runtime:LocalTestPassword!123@"
                "database:1433/openlibrary?driver=ODBC+Driver+18+for+SQL+Server&"
                "Encrypt=yes&TrustServerCertificate=yes"
            ),
            "MSSQL_SA_PASSWORD": "LocalTestPassword!123",
        }
    )
    repository_root = Path(__file__).resolve().parents[4]

    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            "infra/docker-compose.yml",
            "--profile",
            "migration",
            "--profile",
            "test",
            "config",
            "--format",
            "json",
        ],
        cwd=repository_root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    services = json.loads(result.stdout)["services"]
    assert services["database-init"]["profiles"] == ["migration", "test"]
    assert services["migration"]["profiles"] == ["migration"]
    assert services["migration"]["depends_on"]["database-init"]["condition"] == (
        "service_completed_successfully"
    )
    assert set(services["migration"]["environment"]) >= {
        "DATABASE_BOOTSTRAP_URL",
        "DATABASE_MIGRATION_URL",
        "DATABASE_RUNTIME_URL",
    }
    assert "DATABASE_BOOTSTRAP_URL" not in services["app"]["environment"]
    assert "DATABASE_MIGRATION_URL" not in services["app"]["environment"]
    assert "DATABASE_BOOTSTRAP_URL" not in services["worker"]["environment"]
    assert "DATABASE_MIGRATION_URL" not in services["worker"]["environment"]
    assert services["tests"]["profiles"] == ["test"]
    assert services["tests"]["depends_on"]["database-init"]["condition"] == (
        "service_completed_successfully"
    )
    assert (
        "tests/integration/auth/test_login_persistence.py"
        in services["tests"]["command"][2]
    )
