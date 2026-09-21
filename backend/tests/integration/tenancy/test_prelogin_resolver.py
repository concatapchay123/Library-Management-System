"""SQL Server integration tests for pre-login tenant discovery and RLS."""

from collections.abc import Iterator
from dataclasses import fields
import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.exc import DBAPIError

from openlibrary.infrastructure.sqlserver.migrate import (
    bootstrap_database_identities,
    connect,
    database_url_for,
    run_migrations,
)
from openlibrary.modules.core.infrastructure.organizations import (
    clear_tenant_context,
    resolve_login_tenant,
    set_tenant_context,
)


class SqlServerUrls(dict[str, str]):
    """Credential-bearing integration settings with a safe pytest representation."""

    def __repr__(self) -> str:
        return "SqlServerUrls(redacted)"


@pytest.fixture(scope="module")
def database_urls() -> SqlServerUrls:
    """Return SQL Server URLs supplied only by an integration environment."""
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
    """Create a disposable database with distinct migration and runtime users."""
    database_name = f"openlibrary_be004_{uuid4().hex}"
    bootstrap_url = database_urls["DATABASE_BOOTSTRAP_URL"]

    with connect(bootstrap_url, database="master") as connection:
        connection.execute(f"CREATE DATABASE [{database_name}]")

    urls = SqlServerUrls(
        {
            name: database_url_for(url, database_name)
            for name, url in database_urls.items()
        }
    )
    migration_login = f"be004_migrator_{uuid4().hex}"
    runtime_login = f"be004_runtime_{uuid4().hex}"
    urls["DATABASE_MIGRATION_URL"] = (
        make_url(urls["DATABASE_MIGRATION_URL"])
        .set(username=migration_login)
        .render_as_string(hide_password=False)
    )
    urls["DATABASE_RUNTIME_URL"] = (
        make_url(urls["DATABASE_RUNTIME_URL"])
        .set(username=runtime_login)
        .render_as_string(hide_password=False)
    )
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


@pytest.fixture(scope="module")
def seeded_database_urls(clean_database_urls: SqlServerUrls) -> SqlServerUrls:
    """Migrate and seed two tenants through the deployment-only identity."""
    identities = bootstrap_database_identities(
        bootstrap_url=clean_database_urls["DATABASE_BOOTSTRAP_URL"],
        migration_url=clean_database_urls["DATABASE_MIGRATION_URL"],
        runtime_url=clean_database_urls["DATABASE_RUNTIME_URL"],
    )
    run_migrations(
        clean_database_urls["DATABASE_MIGRATION_URL"],
        runtime_login=identities.runtime_login,
    )
    organization_a = uuid4()
    organization_b = uuid4()
    with connect(clean_database_urls["DATABASE_BOOTSTRAP_URL"]) as connection:
        connection.execute(
            "INSERT INTO core.organizations "
            "(organization_id, name, slug, organization_type, status, timezone, "
            "settings_json) VALUES "
            f"('{organization_a}', N'Campus A', 'campus-a', 'education', 'active', "
            "'Asia/Ho_Chi_Minh', N'{}'), "
            f"('{organization_b}', N'Campus B', 'campus-b', 'education', 'disabled', "
            "'Asia/Ho_Chi_Minh', N'{}')"
        )
    clean_database_urls["ORGANIZATION_A"] = str(organization_a)
    clean_database_urls["ORGANIZATION_B"] = str(organization_b)
    return clean_database_urls


@pytest.fixture
def runtime_connection(seeded_database_urls: dict[str, str]) -> Iterator[Connection]:
    """Connect as the runtime principal without pre-populated tenant context."""
    engine = create_engine(seeded_database_urls["DATABASE_RUNTIME_URL"])
    with engine.connect() as connection:
        yield connection
    engine.dispose()


def _visible_organization_ids(connection: Connection) -> set[UUID]:
    rows = connection.execute(text("SELECT organization_id FROM core.organizations"))
    return {UUID(str(row.organization_id)) for row in rows}


def test_runtime_can_discover_login_tenant_only_through_resolver(
    runtime_connection: Connection,
) -> None:
    """Removing the procedure or its owner context must break pre-login discovery."""
    assert _visible_organization_ids(runtime_connection) == set()

    tenant = resolve_login_tenant(runtime_connection, "campus-a")

    assert tenant is not None
    assert tenant.slug == "campus-a"
    assert tenant.status == "active"
    assert {field.name for field in fields(tenant)} == {
        "organization_id",
        "slug",
        "status",
    }


def test_tenant_context_filters_reads_and_blocks_foreign_inserts(
    runtime_connection: Connection,
    seeded_database_urls: dict[str, str],
) -> None:
    """Changing or removing the predicate must expose this cross-tenant write."""
    organization_a = UUID(seeded_database_urls["ORGANIZATION_A"])
    foreign_organization = uuid4()

    set_tenant_context(runtime_connection, organization_a)
    assert _visible_organization_ids(runtime_connection) == {organization_a}

    with pytest.raises(DBAPIError):
        runtime_connection.execute(
            text(
                "INSERT INTO core.organizations "
                "(organization_id, name, slug, organization_type, status, timezone, "
                "settings_json) VALUES "
                "(:organization_id, N'Unexpected', 'foreign-tenant', 'education', "
                "'active', 'UTC', N'{}')"
            ),
            {"organization_id": str(foreign_organization)},
        )

    runtime_connection.rollback()
    clear_tenant_context(runtime_connection)
    assert _visible_organization_ids(runtime_connection) == set()


def test_organization_policy_has_filter_and_block_predicates(
    seeded_database_urls: dict[str, str],
) -> None:
    """Removing either predicate must fail the RLS catalog contract."""
    engine: Engine = create_engine(seeded_database_urls["DATABASE_BOOTSTRAP_URL"])
    with engine.connect() as connection:
        predicates = {
            (row.predicate_type_desc, row.operation_desc)
            for row in connection.execute(
                text(
                    "SELECT predicate_type_desc, operation_desc "
                    "FROM sys.security_predicates "
                    "WHERE target_object_id = OBJECT_ID(N'core.organizations')"
                )
            )
        }
    engine.dispose()

    assert predicates == {("FILTER", None), ("BLOCK", "AFTER INSERT")}
