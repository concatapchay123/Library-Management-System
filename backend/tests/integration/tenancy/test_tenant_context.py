"""SQL Server proof for request tenant context and catalog enforcement."""

from __future__ import annotations

from collections.abc import Iterator
import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import DBAPIError

from openlibrary.infrastructure.sqlserver.migrate import (
    bootstrap_database_identities,
    connect,
    database_url_for,
    run_migrations,
)
from openlibrary.modules.core.infrastructure.tenancy import (
    SqlServerTenantContext,
    TenantCatalogError,
    verify_tenant_catalog,
)
from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.authorization import AuthorizationService
from openlibrary.modules.core.application.books import BookCatalogService
from openlibrary.modules.core.infrastructure.books import SqlServerBookStore
from openlibrary.modules.core.infrastructure.rbac import SqlServerRbacStore


@pytest.fixture(scope="module")
def database_urls() -> dict[str, str]:
    required = (
        "DATABASE_BOOTSTRAP_URL",
        "DATABASE_MIGRATION_URL",
        "DATABASE_RUNTIME_URL",
    )
    missing = [name for name in required if not os.environ.get(name, "").strip()]
    if missing:
        pytest.skip(f"SQL Server integration requires: {', '.join(missing)}")
    return {name: os.environ[name] for name in required}


@pytest.fixture(scope="module")
def tenant_database_urls(database_urls: dict[str, str]) -> Iterator[dict[str, str]]:
    database_name = f"openlibrary_be011_{uuid4().hex}"
    with connect(database_urls["DATABASE_BOOTSTRAP_URL"], database="master") as server:
        server.execute(f"CREATE DATABASE [{database_name}]")
    urls = {
        name: database_url_for(url, database_name)
        for name, url in database_urls.items()
    }
    migration_login = f"be011_migrator_{uuid4().hex}"
    runtime_login = f"be011_runtime_{uuid4().hex}"
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
        identities = bootstrap_database_identities(
            bootstrap_url=urls["DATABASE_BOOTSTRAP_URL"],
            migration_url=urls["DATABASE_MIGRATION_URL"],
            runtime_url=urls["DATABASE_RUNTIME_URL"],
        )
        run_migrations(
            urls["DATABASE_MIGRATION_URL"], runtime_login=identities.runtime_login
        )
        yield urls
    finally:
        with connect(
            database_urls["DATABASE_BOOTSTRAP_URL"], database="master"
        ) as server:
            server.execute(
                f"ALTER DATABASE [{database_name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE"
            )
            server.execute(f"DROP DATABASE [{database_name}]")
            server.execute(f"DROP LOGIN [{runtime_login}]")
            server.execute(f"DROP LOGIN [{migration_login}]")


def _seed_tenants(url: str) -> tuple[UUID, UUID]:
    organization_a, organization_b = uuid4(), uuid4()
    with create_engine(url).begin() as connection:
        connection.execute(
            text(
                "INSERT INTO core.organizations "
                "(organization_id, name, slug, organization_type, status, timezone, settings_json) "
                "VALUES (:a, N'A', :a_slug, 'education', 'active', 'UTC', N'{}'), "
                "(:b, N'B', :b_slug, 'education', 'active', 'UTC', N'{}')"
            ),
            {
                "a": str(organization_a),
                "b": str(organization_b),
                "a_slug": f"a-{organization_a.hex}",
                "b_slug": f"b-{organization_b.hex}",
            },
        )
    return organization_a, organization_b


def test_context_fails_closed_for_cross_tenant_reads_and_writes_and_pool_reuse(
    tenant_database_urls: dict[str, str],
) -> None:
    organization_a, organization_b = _seed_tenants(
        tenant_database_urls["DATABASE_BOOTSTRAP_URL"]
    )
    engine = create_engine(
        tenant_database_urls["DATABASE_RUNTIME_URL"], pool_size=1, max_overflow=0
    )
    context = SqlServerTenantContext(
        tenant_database_urls["DATABASE_RUNTIME_URL"], engine=engine
    )

    with context.connection(organization_a) as connection:
        ids = {
            UUID(str(row.organization_id))
            for row in connection.execute(
                text("SELECT organization_id FROM core.organizations")
            )
        }
        assert ids == {organization_a}
        update = connection.execute(
            text(
                "UPDATE core.organizations SET timezone = 'UTC' "
                "WHERE organization_id = :id"
            ),
            {"id": str(organization_b)},
        )
        deleted = connection.execute(
            text("DELETE FROM core.organizations WHERE organization_id = :id"),
            {"id": str(organization_b)},
        )
        assert update.rowcount == deleted.rowcount == 0

    with context.connection(organization_b) as connection:
        ids = {
            UUID(str(row.organization_id))
            for row in connection.execute(
                text("SELECT organization_id FROM core.organizations")
            )
        }
        assert ids == {organization_b}
        with pytest.raises(DBAPIError):
            connection.execute(
                text(
                    "INSERT INTO core.organizations (organization_id, name, slug, organization_type, status, timezone, settings_json) VALUES (:id, N'foreign', :slug, 'education', 'active', 'UTC', N'{}')"
                ),
                {"id": str(organization_a), "slug": f"foreign-{uuid4().hex}"},
            )

    with context.raw_connection() as connection:
        ids = list(
            connection.execute(text("SELECT organization_id FROM core.organizations"))
        )
        assert ids == []
    context.dispose()


def test_catalog_rejects_a_policy_free_tenant_fixture(
    tenant_database_urls: dict[str, str],
) -> None:
    engine: Engine = create_engine(tenant_database_urls["DATABASE_MIGRATION_URL"])
    with engine.begin() as connection:
        verify_tenant_catalog(connection)
        connection.execute(
            text(
                "CREATE TABLE core.be011_policy_free (organization_id uniqueidentifier NOT NULL, item_id uniqueidentifier NOT NULL PRIMARY KEY)"
            )
        )
        with pytest.raises(TenantCatalogError, match="core.be011_policy_free"):
            verify_tenant_catalog(connection)
        connection.execute(text("DROP TABLE core.be011_policy_free"))
    engine.dispose()


def test_books_are_visible_only_to_the_current_tenant(
    tenant_database_urls: dict[str, str],
) -> None:
    """RLS and the catalog adapter must make a foreign book indistinguishable from absent."""
    organization_a, organization_b = _seed_tenants(
        tenant_database_urls["DATABASE_BOOTSTRAP_URL"]
    )
    store = SqlServerBookStore(tenant_database_urls["DATABASE_RUNTIME_URL"])
    authorizer = AuthorizationService(
        SqlServerRbacStore(tenant_database_urls["DATABASE_RUNTIME_URL"])
    )
    service = BookCatalogService(store, authorizer)
    # Insert direct permission grants only for this disposable integration fixture.
    # The service still resolves them through tenant-scoped RBAC joins.
    actor_a, actor_b = _catalog_actors(
        tenant_database_urls["DATABASE_BOOTSTRAP_URL"], organization_a, organization_b
    )
    book_a = service.create(
        actor=actor_a,
        title="Tenant A title",
        isbn="9780000000001",
        authors=["A"],
        published_year=2024,
    )
    book_b = service.create(
        actor=actor_b,
        title="Tenant B title",
        isbn="9780000000002",
        authors=["B"],
        published_year=2025,
    )

    assert service.list(actor=actor_a, limit=20, cursor=None, filters={}).items == (
        book_a,
    )
    with pytest.raises(KeyError):
        service.get(actor=actor_a, book_id=book_b.book_id)


def _catalog_actors(
    bootstrap_url: str, organization_a: UUID, organization_b: UUID
) -> tuple[Principal, Principal]:
    actors = tuple(
        Principal(uuid4(), organization_id, uuid4())
        for organization_id in (organization_a, organization_b)
    )
    with create_engine(bootstrap_url).begin() as connection:
        for actor in actors:
            role_id, read_id, manage_id = uuid4(), uuid4(), uuid4()
            connection.execute(
                text(
                    "INSERT INTO core.users (user_id, organization_id, email, password_hash, status) "
                    "VALUES (:user_id, :organization_id, :email, 'not-a-secret', 'active'); "
                    "INSERT INTO core.roles (role_id, organization_id, name) "
                    "VALUES (:role_id, :organization_id, 'catalog-manager'); "
                    "INSERT INTO core.permissions (permission_id, organization_id, code) VALUES "
                    "(:read_id, :organization_id, 'catalog.read'), "
                    "(:manage_id, :organization_id, 'catalog.manage'); "
                    "INSERT INTO core.user_roles (organization_id, user_id, role_id) "
                    "VALUES (:organization_id, :user_id, :role_id); "
                    "INSERT INTO core.role_permissions (organization_id, role_id, permission_id) VALUES "
                    "(:organization_id, :role_id, :read_id), "
                    "(:organization_id, :role_id, :manage_id)"
                ),
                {
                    "user_id": str(actor.user_id),
                    "organization_id": str(actor.organization_id),
                    "email": f"{actor.user_id.hex}@example.test",
                    "role_id": str(role_id),
                    "read_id": str(read_id),
                    "manage_id": str(manage_id),
                },
            )
    return actors
