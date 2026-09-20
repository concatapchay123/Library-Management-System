"""SQL Server migration identity and runtime-permission integration tests."""

from collections.abc import Iterator
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import pytest
from pyodbc import Error
from sqlalchemy.engine import make_url

from openlibrary.infrastructure.sqlserver.migrate import (
    bootstrap_database_identities,
    connect,
    database_url_for,
    run_migrations,
    verify_runtime_restrictions,
)


class SqlServerUrls(dict[str, str]):
    """Credential-bearing integration settings with a safe pytest representation."""

    def __repr__(self) -> str:
        return "SqlServerUrls(redacted)"


@pytest.fixture(scope="module")
def database_urls() -> SqlServerUrls:
    """Return the operator-supplied SQL Server URLs or skip outside integration runs."""
    required_names = (
        "DATABASE_BOOTSTRAP_URL",
        "DATABASE_MIGRATION_URL",
        "DATABASE_RUNTIME_URL",
    )
    missing = [name for name in required_names if not os.environ.get(name, "").strip()]
    if missing:
        pytest.skip(f"SQL Server integration requires: {', '.join(missing)}")
    return SqlServerUrls({name: os.environ[name] for name in required_names})


@pytest.fixture(scope="module")
def clean_database_urls(database_urls: SqlServerUrls) -> Iterator[SqlServerUrls]:
    """Create an isolated database so the migration proves a clean bootstrap path."""
    database_name = f"openlibrary_be003_{uuid4().hex}"
    bootstrap_url = database_urls["DATABASE_BOOTSTRAP_URL"]

    with connect(bootstrap_url, database="master") as connection:
        connection.execute(f"CREATE DATABASE [{database_name}]")

    urls = SqlServerUrls(
        {
            name: database_url_for(url, database_name)
            for name, url in database_urls.items()
        }
    )
    # Use unique non-default names so grants cannot silently rely on the
    # illustrative documentation names or leak principals across test runs.
    migration_login = f"be003_migrator_{uuid4().hex}"
    runtime_login = f"be003_runtime_{uuid4().hex}"
    urls["DATABASE_MIGRATION_URL"] = make_url(
        urls["DATABASE_MIGRATION_URL"]
    ).set(username=migration_login).render_as_string(hide_password=False)
    urls["DATABASE_RUNTIME_URL"] = make_url(
        urls["DATABASE_RUNTIME_URL"]
    ).set(username=runtime_login).render_as_string(hide_password=False)
    try:
        yield urls
    finally:
        with connect(bootstrap_url, database="master") as connection:
            connection.execute(
                "ALTER DATABASE "
                f"[{database_name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE"
            )
            connection.execute(f"DROP DATABASE [{database_name}]")
            connection.execute(f"DROP LOGIN [{runtime_login}]")
            connection.execute(f"DROP LOGIN [{migration_login}]")


def test_documented_runner_executes_from_the_backend_directory(
    clean_database_urls: dict[str, str],
) -> None:
    """The documented command locates Alembic configuration after normal install."""
    environment = os.environ.copy()
    environment.update(clean_database_urls)
    backend_root = Path(__file__).resolve().parents[3]

    result = subprocess.run(
        [sys.executable, "scripts/run_migrations.py"],
        cwd=backend_root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_clean_database_migration_creates_distinct_identities(
    clean_database_urls: dict[str, str],
) -> None:
    """A clean database gets schemas, versioning, and separate SQL principals."""
    identities = bootstrap_database_identities(
        bootstrap_url=clean_database_urls["DATABASE_BOOTSTRAP_URL"],
        migration_url=clean_database_urls["DATABASE_MIGRATION_URL"],
        runtime_url=clean_database_urls["DATABASE_RUNTIME_URL"],
    )
    run_migrations(
        clean_database_urls["DATABASE_MIGRATION_URL"],
        runtime_login=identities.runtime_login,
    )

    with connect(clean_database_urls["DATABASE_MIGRATION_URL"]) as connection:
        schemas = connection.fetch_values(
            "SELECT name FROM sys.schemas "
            "WHERE name IN ('core', 'ops', 'education', 'public_library')"
        )
        version = connection.fetch_value("SELECT version_num FROM alembic_version")
    with connect(clean_database_urls["DATABASE_RUNTIME_URL"]) as runtime:
        runtime_guard_count = runtime.fetch_value(
            "SELECT COUNT(*) FROM core.runtime_permission_guard"
        )

    assert set(schemas) == {"core", "ops", "education", "public_library"}
    assert version
    assert runtime_guard_count == 0


def test_runtime_identity_cannot_run_ddl_or_alter_security_policy(
    clean_database_urls: dict[str, str],
) -> None:
    """The runtime user is denied SQL Server DDL and RLS-policy alteration."""
    identities = bootstrap_database_identities(
        bootstrap_url=clean_database_urls["DATABASE_BOOTSTRAP_URL"],
        migration_url=clean_database_urls["DATABASE_MIGRATION_URL"],
        runtime_url=clean_database_urls["DATABASE_RUNTIME_URL"],
    )
    run_migrations(
        clean_database_urls["DATABASE_MIGRATION_URL"],
        runtime_login=identities.runtime_login,
    )

    with connect(clean_database_urls["DATABASE_RUNTIME_URL"]) as runtime:
        with pytest.raises(Error):
            runtime.execute("CREATE TABLE core.runtime_escape (id int NOT NULL)")
        with pytest.raises(Error):
            runtime.execute(
                "ALTER SECURITY POLICY core.runtime_permission_guard WITH (STATE = OFF)"
            )

    verify_runtime_restrictions(
        clean_database_urls["DATABASE_RUNTIME_URL"],
        migration_login=identities.migration_login,
    )
