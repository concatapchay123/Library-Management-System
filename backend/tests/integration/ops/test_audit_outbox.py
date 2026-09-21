"""SQL Server integration coverage for BE-005 audit and outbox persistence."""

from collections.abc import Iterator
import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.exc import DBAPIError, IntegrityError

from openlibrary.infrastructure.sqlserver.migrate import (
    bootstrap_database_identities,
    connect,
    database_url_for,
    run_migrations,
)
from openlibrary.modules.core.infrastructure.organizations import set_tenant_context


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
    """Create one isolated database and least-privilege identities for this module."""
    database_name = f"openlibrary_be005_{uuid4().hex}"
    bootstrap_url = database_urls["DATABASE_BOOTSTRAP_URL"]

    with connect(bootstrap_url, database="master") as connection:
        connection.execute(f"CREATE DATABASE [{database_name}]")

    urls = SqlServerUrls(
        {
            name: database_url_for(url, database_name)
            for name, url in database_urls.items()
        }
    )
    migration_login = f"be005_migrator_{uuid4().hex}"
    runtime_login = f"be005_runtime_{uuid4().hex}"
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
    """Migrate an isolated database and create one tenant through bootstrap access."""
    identities = bootstrap_database_identities(
        bootstrap_url=clean_database_urls["DATABASE_BOOTSTRAP_URL"],
        migration_url=clean_database_urls["DATABASE_MIGRATION_URL"],
        runtime_url=clean_database_urls["DATABASE_RUNTIME_URL"],
    )
    run_migrations(
        clean_database_urls["DATABASE_MIGRATION_URL"],
        runtime_login=identities.runtime_login,
    )
    organization_id = uuid4()
    with connect(clean_database_urls["DATABASE_BOOTSTRAP_URL"]) as connection:
        connection.execute(
            "INSERT INTO core.organizations "
            "(organization_id, name, slug, organization_type, status, timezone, "
            "settings_json) VALUES "
            f"('{organization_id}', N'Campus A', 'campus-a', 'education', 'active', "
            "'Asia/Ho_Chi_Minh', N'{}')"
        )
    clean_database_urls["ORGANIZATION_ID"] = str(organization_id)
    return clean_database_urls


@pytest.fixture
def runtime_connection(seeded_database_urls: SqlServerUrls) -> Iterator[Connection]:
    """Connect as the runtime principal with one server-derived tenant context."""
    engine = create_engine(seeded_database_urls["DATABASE_RUNTIME_URL"])
    with engine.connect() as connection:
        set_tenant_context(connection, UUID(seeded_database_urls["ORGANIZATION_ID"]))
        connection.commit()
        yield connection
    engine.dispose()


def _table_names(database_url: str) -> set[str]:
    engine = create_engine(database_url)
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT SCHEMA_NAME(schema_id) AS schema_name, name "
                "FROM sys.tables WHERE SCHEMA_NAME(schema_id) = 'ops'"
            )
        )
        names = {f"{row.schema_name}.{row.name}" for row in rows}
    engine.dispose()
    return names


def _security_predicates(
    database_url: str, table_name: str
) -> set[tuple[str, str | None]]:
    engine = create_engine(database_url)
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT predicate_type_desc, operation_desc "
                "FROM sys.security_predicates "
                "WHERE target_object_id = OBJECT_ID(:table_name)"
            ),
            {"table_name": table_name},
        )
        predicates = {
            (str(row.predicate_type_desc), row.operation_desc) for row in rows
        }
    engine.dispose()
    return predicates


def _writer() -> object:
    """Return the BE-005 transaction port once its production module exists."""
    from openlibrary.modules.ops.infrastructure.sqlserver import (
        SqlServerAuditedTransaction,
    )

    return SqlServerAuditedTransaction()


def _events(
    organization_id: UUID, idempotency_key: str
) -> tuple[object, tuple[object, ...]]:
    """Construct literals that represent one safe audited domain mutation."""
    from openlibrary.modules.ops.application.persistence import AuditEvent, OutboxEvent

    correlation_id = uuid4()
    return (
        AuditEvent(
            action="organization.timezone_changed",
            entity_type="organization",
            entity_id=organization_id,
            payload={
                "before": {"timezone": "Asia/Ho_Chi_Minh"},
                "after": {"timezone": "UTC"},
            },
            correlation_id=correlation_id,
        ),
        (
            OutboxEvent(
                event_type="organization.timezone_changed",
                aggregate_type="organization",
                aggregate_id=organization_id,
                payload_version=1,
                payload={"timezone": "UTC"},
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
            ),
        ),
    )


def _change_timezone(
    connection: Connection, organization_id: UUID, timezone: str
) -> str:
    connection.execute(
        text(
            "UPDATE core.organizations SET timezone = :timezone "
            "WHERE organization_id = :organization_id"
        ),
        {"timezone": timezone, "organization_id": str(organization_id)},
    )
    return timezone


def _record_count(connection: Connection, table_name: str, record_id: UUID) -> int:
    """Count one durable record without leaking state from another test."""
    statements = {
        "ops.audit_events": text(
            "SELECT COUNT(*) FROM ops.audit_events WHERE audit_id = :record_id"
        ),
        "ops.outbox_events": text(
            "SELECT COUNT(*) FROM ops.outbox_events WHERE event_id = :record_id"
        ),
    }
    if table_name not in statements:
        raise ValueError(f"unsupported durable table: {table_name}")
    return int(
        connection.execute(
            statements[table_name], {"record_id": str(record_id)}
        ).scalar_one()
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"access_token": "untrusted"},
        {"payment": {"card_number": "4111111111111111", "cvv": "123"}},
    ],
)
def test_event_models_reject_sensitive_payloads(payload: dict[str, object]) -> None:
    """Removing payload validation would allow credentials into durable event data."""
    from openlibrary.modules.ops.application.persistence import AuditEvent, OutboxEvent

    organization_id = uuid4()
    with pytest.raises(ValueError, match="sensitive"):
        AuditEvent(
            action="organization.timezone_changed",
            entity_type="organization",
            entity_id=organization_id,
            payload=payload,
            correlation_id=uuid4(),
        )
    with pytest.raises(ValueError, match="sensitive"):
        OutboxEvent(
            event_type="organization.timezone_changed",
            aggregate_type="organization",
            aggregate_id=organization_id,
            payload_version=1,
            payload=payload,
            correlation_id=uuid4(),
            idempotency_key="sensitive-payload",
        )


def test_event_models_generate_distinct_record_ids() -> None:
    """Reusing one default UUID would make unrelated durable records collide."""
    from openlibrary.modules.ops.application.persistence import AuditEvent, OutboxEvent

    organization_id = uuid4()
    correlation_id = uuid4()
    first_audit = AuditEvent(
        action="organization.timezone_changed",
        entity_type="organization",
        entity_id=organization_id,
        payload={"after": {"timezone": "UTC"}},
        correlation_id=correlation_id,
    )
    second_audit = AuditEvent(
        action="organization.timezone_changed",
        entity_type="organization",
        entity_id=organization_id,
        payload={"after": {"timezone": "UTC"}},
        correlation_id=correlation_id,
    )
    first_outbox = OutboxEvent(
        event_type="organization.timezone_changed",
        aggregate_type="organization",
        aggregate_id=organization_id,
        payload_version=1,
        payload={"timezone": "UTC"},
        correlation_id=correlation_id,
        idempotency_key="first",
    )
    second_outbox = OutboxEvent(
        event_type="organization.timezone_changed",
        aggregate_type="organization",
        aggregate_id=organization_id,
        payload_version=1,
        payload={"timezone": "UTC"},
        correlation_id=correlation_id,
        idempotency_key="second",
    )

    assert first_audit.audit_id != second_audit.audit_id
    assert first_outbox.event_id != second_outbox.event_id


def test_audit_and_outbox_tables_are_tenant_protected(
    seeded_database_urls: SqlServerUrls,
) -> None:
    """Dropping the BE-005 migration must remove these protected durable records."""
    assert _table_names(seeded_database_urls["DATABASE_BOOTSTRAP_URL"]) >= {
        "ops.audit_events",
        "ops.outbox_events",
    }
    expected_predicates = {
        ("FILTER", None),
        ("BLOCK", "AFTER INSERT"),
        ("BLOCK", "AFTER UPDATE"),
        ("BLOCK", "BEFORE DELETE"),
    }
    assert (
        _security_predicates(
            seeded_database_urls["DATABASE_BOOTSTRAP_URL"], "ops.audit_events"
        )
        == expected_predicates
    )
    assert (
        _security_predicates(
            seeded_database_urls["DATABASE_BOOTSTRAP_URL"], "ops.outbox_events"
        )
        == expected_predicates
    )


def test_transaction_commits_mutation_audit_and_outbox_together(
    runtime_connection: Connection,
    seeded_database_urls: SqlServerUrls,
) -> None:
    """Removing one writer step must leave this successful state transition incomplete."""
    organization_id = UUID(seeded_database_urls["ORGANIZATION_ID"])
    audit_event, outbox_events = _events(organization_id, "timezone-change-1")

    result = _writer().run(
        runtime_connection,
        lambda connection: _change_timezone(connection, organization_id, "UTC"),
        audit_event,
        outbox_events,
    )

    assert result == "UTC"
    assert (
        runtime_connection.execute(
            text("SELECT timezone FROM core.organizations WHERE organization_id = :id"),
            {"id": str(organization_id)},
        ).scalar_one()
        == "UTC"
    )
    assert (
        _record_count(runtime_connection, "ops.audit_events", audit_event.audit_id) == 1
    )
    assert (
        _record_count(
            runtime_connection, "ops.outbox_events", outbox_events[0].event_id
        )
        == 1
    )


def test_transaction_rolls_back_mutation_and_audit_when_outbox_insert_fails(
    runtime_connection: Connection,
    seeded_database_urls: SqlServerUrls,
) -> None:
    """A duplicate durable effect must not commit the protected mutation or audit row."""
    organization_id = UUID(seeded_database_urls["ORGANIZATION_ID"])
    writer = _writer()
    first_audit, first_outbox = _events(organization_id, "duplicate-timezone-change")
    writer.run(
        runtime_connection,
        lambda connection: _change_timezone(connection, organization_id, "UTC"),
        first_audit,
        first_outbox,
    )
    duplicate_audit, duplicate_outbox = _events(
        organization_id, "duplicate-timezone-change"
    )
    runtime_connection.execute(text("SELECT 1")).scalar_one()

    with pytest.raises(IntegrityError):
        writer.run(
            runtime_connection,
            lambda connection: _change_timezone(
                connection, organization_id, "Asia/Bangkok"
            ),
            duplicate_audit,
            duplicate_outbox,
        )

    assert (
        runtime_connection.execute(
            text("SELECT timezone FROM core.organizations WHERE organization_id = :id"),
            {"id": str(organization_id)},
        ).scalar_one()
        == "UTC"
    )
    assert (
        _record_count(runtime_connection, "ops.audit_events", first_audit.audit_id) == 1
    )
    assert (
        _record_count(runtime_connection, "ops.audit_events", duplicate_audit.audit_id)
        == 0
    )
    assert (
        _record_count(runtime_connection, "ops.outbox_events", first_outbox[0].event_id)
        == 1
    )
    assert (
        _record_count(
            runtime_connection, "ops.outbox_events", duplicate_outbox[0].event_id
        )
        == 0
    )


def test_runtime_cannot_modify_or_delete_audit_events(
    runtime_connection: Connection,
    seeded_database_urls: SqlServerUrls,
) -> None:
    """Removing the audit permission denial would make immutable evidence mutable."""
    organization_id = UUID(seeded_database_urls["ORGANIZATION_ID"])
    audit_event, outbox_events = _events(organization_id, "immutable-audit")
    _writer().run(
        runtime_connection,
        lambda connection: _change_timezone(connection, organization_id, "UTC"),
        audit_event,
        outbox_events,
    )

    with pytest.raises(DBAPIError):
        runtime_connection.execute(
            text("UPDATE ops.audit_events SET action = 'tampered'")
        )
    runtime_connection.rollback()
    with pytest.raises(DBAPIError):
        runtime_connection.execute(text("DELETE FROM ops.audit_events"))
    runtime_connection.rollback()
    assert (
        _record_count(runtime_connection, "ops.audit_events", audit_event.audit_id) == 1
    )
