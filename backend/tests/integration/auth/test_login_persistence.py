"""SQL Server coverage for BE-007 tenant-scoped credential persistence."""

from collections.abc import Iterator
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url

from openlibrary.infrastructure.sqlserver.migrate import (
    bootstrap_database_identities,
    connect,
    database_url_for,
    run_migrations,
)
from openlibrary.modules.core.domain.passwords import PasswordService
from openlibrary.modules.core.infrastructure.login import create_sqlserver_login_service


class SqlServerUrls(dict[str, str]):
    """Credential-bearing integration settings with a safe pytest representation."""

    def __repr__(self) -> str:
        return "SqlServerUrls(redacted)"


@pytest.fixture(scope="module")
def database_urls() -> SqlServerUrls:
    """Return SQL Server URLs supplied only by the dedicated integration environment."""
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
def seeded_database_urls(database_urls: SqlServerUrls) -> Iterator[SqlServerUrls]:
    """Create a disposable database containing duplicate tenant-local emails."""
    database_name = f"openlibrary_be007_{uuid4().hex}"
    bootstrap_url = database_urls["DATABASE_BOOTSTRAP_URL"]
    with connect(bootstrap_url, database="master") as connection:
        connection.execute(f"CREATE DATABASE [{database_name}]")

    urls = SqlServerUrls(
        {
            name: database_url_for(url, database_name)
            for name, url in database_urls.items()
        }
    )
    migration_login = f"be007_migrator_{uuid4().hex}"
    runtime_login = f"be007_runtime_{uuid4().hex}"
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
        _seed_database(urls["DATABASE_BOOTSTRAP_URL"])
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


def _seed_database(database_url: str) -> None:
    """Create active/disabled tenants and tenant-local credential records."""
    organization_a, organization_b, organization_disabled = uuid4(), uuid4(), uuid4()
    user_a, user_b = uuid4(), uuid4()
    password_hash = PasswordService().hash("correct-horse-battery-staple")
    with connect(database_url) as connection:
        connection.execute(
            "INSERT INTO core.organizations "
            "(organization_id, name, slug, organization_type, status, timezone, "
            "settings_json) VALUES "
            f"('{organization_a}', N'Campus A', 'campus-a', 'education', 'active', "
            "'Asia/Ho_Chi_Minh', N'{}'), "
            f"('{organization_b}', N'Campus B', 'campus-b', 'education', 'active', "
            "'Asia/Ho_Chi_Minh', N'{}'), "
            f"('{organization_disabled}', N'Disabled Campus', 'disabled-campus', "
            "'education', 'disabled', 'Asia/Ho_Chi_Minh', N'{}')"
        )
        connection.execute(
            "INSERT INTO core.users "
            "(user_id, organization_id, email, password_hash, status) VALUES "
            f"('{user_a}', '{organization_a}', N'librarian@example.test', "
            f"'{password_hash}', 'active'), "
            f"('{user_b}', '{organization_b}', N'librarian@example.test', "
            f"'{password_hash}', 'active')"
        )


def test_duplicate_tenant_emails_authenticate_only_after_slug_resolution(
    seeded_database_urls: SqlServerUrls,
) -> None:
    """Removing the resolver/context ordering would leak or select a foreign user."""
    service = create_sqlserver_login_service(
        seeded_database_urls["DATABASE_RUNTIME_URL"]
    )

    campus_a = service.login(
        organization_slug="campus-a",
        email="librarian@example.test",
        password="correct-horse-battery-staple",
        correlation_id="campus-a-login",
    )
    campus_b = service.login(
        organization_slug="campus-b",
        email="librarian@example.test",
        password="correct-horse-battery-staple",
        correlation_id="campus-b-login",
    )

    assert campus_a is not None
    assert campus_b is not None
    assert campus_a.organization_id != campus_b.organization_id
    assert campus_a.user_id != campus_b.user_id


def test_login_failures_are_audited_without_credential_content(
    seeded_database_urls: SqlServerUrls,
) -> None:
    """Unknown, disabled, and wrong-password paths must be uniform and durable."""
    service = create_sqlserver_login_service(
        seeded_database_urls["DATABASE_RUNTIME_URL"]
    )

    failures = (
        service.login(
            organization_slug="missing-campus",
            email="librarian@example.test",
            password="wrong-password",
            correlation_id="missing-campus-login",
        ),
        service.login(
            organization_slug="disabled-campus",
            email="librarian@example.test",
            password="wrong-password",
            correlation_id="disabled-campus-login",
        ),
        service.login(
            organization_slug="campus-a",
            email="librarian@example.test",
            password="wrong-password",
            correlation_id="wrong-password-login",
        ),
    )

    assert failures == (None, None, None)
    engine: Engine = create_engine(seeded_database_urls["DATABASE_BOOTSTRAP_URL"])
    with engine.connect() as connection:
        tenant_events = list(
            connection.execute(
                text(
                    "SELECT action, payload_json FROM ops.audit_events "
                    "WHERE action = 'authentication.login_failed'"
                )
            )
        )
        unresolved_events = int(
            connection.execute(
                text("SELECT COUNT(*) FROM ops.prelogin_security_events")
            ).scalar_one()
        )
    engine.dispose()

    assert len(tenant_events) == 2
    assert unresolved_events == 1
    assert {str(row.action) for row in tenant_events} == {"authentication.login_failed"}
    assert all("wrong-password" not in str(row.payload_json) for row in tenant_events)
    assert all(
        "librarian@example.test" not in str(row.payload_json) for row in tenant_events
    )


def test_users_and_profiles_have_composite_relations_and_rls(
    seeded_database_urls: SqlServerUrls,
) -> None:
    """A migration without tenant keys or complete predicates must fail catalog checks."""
    engine: Engine = create_engine(seeded_database_urls["DATABASE_BOOTSTRAP_URL"])
    with engine.connect() as connection:
        user_keys = {
            str(row.name)
            for row in connection.execute(
                text(
                    "SELECT name FROM sys.key_constraints "
                    "WHERE parent_object_id = OBJECT_ID(N'core.users')"
                )
            )
        }
        profile_fk_columns = [
            str(row.parent_column_name)
            for row in connection.execute(
                text(
                    "SELECT COL_NAME(fkc.parent_object_id, fkc.parent_column_id) "
                    "AS parent_column_name FROM sys.foreign_key_columns AS fkc "
                    "JOIN sys.foreign_keys AS fk ON fk.object_id = fkc.constraint_object_id "
                    "WHERE fk.name = N'FK_core_user_profiles_user' "
                    "ORDER BY fkc.constraint_column_id"
                )
            )
        ]
        policies = {
            table_name: {
                (str(row.predicate_type_desc), row.operation_desc)
                for row in connection.execute(
                    text(
                        "SELECT predicate_type_desc, operation_desc "
                        "FROM sys.security_predicates "
                        "WHERE target_object_id = OBJECT_ID(:table_name)"
                    ),
                    {"table_name": table_name},
                )
            }
            for table_name in ("core.users", "core.user_profiles")
        }
    engine.dispose()

    assert user_keys >= {
        "PK_core_users",
        "UQ_core_users_organization_user",
        "UQ_core_users_organization_email",
    }
    assert profile_fk_columns == ["organization_id", "user_id"]
    assert all(
        predicates
        == {
            ("FILTER", None),
            ("BLOCK", "AFTER INSERT"),
            ("BLOCK", "AFTER UPDATE"),
            ("BLOCK", "BEFORE DELETE"),
        }
        for predicates in policies.values()
    )
