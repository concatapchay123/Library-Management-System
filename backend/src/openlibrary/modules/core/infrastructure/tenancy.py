"""Request-scoped SQL Server tenant context and schema contract checks."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import UUID

from flask import g
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from openlibrary.modules.core.infrastructure.organizations import (
    clear_tenant_context,
    set_tenant_context,
)


class TenantCatalogError(RuntimeError):
    """Raised when a tenant-addressable SQL Server table lacks its safeguards."""


class SqlServerTenantContext:
    """Lease pooled connections with fail-closed, transaction-scoped tenant state."""

    def __init__(self, database_url: str, *, engine: Engine | None = None) -> None:
        self._database_url = database_url
        self._engine = engine

    @contextmanager
    def connection(self, organization_id: UUID) -> Iterator[Connection]:
        """Set context before use and invalidate the physical connection on bad cleanup."""
        with self._get_engine().connect() as connection:
            try:
                set_tenant_context(connection, organization_id)
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
            finally:
                try:
                    clear_tenant_context(connection)
                    connection.commit()
                except BaseException:
                    connection.invalidate()
                    raise

    @contextmanager
    def raw_connection(self) -> Iterator[Connection]:
        """Expose an unscoped lease only for controlled verifier tests and bootstrap code."""
        with self._get_engine().connect() as connection:
            yield connection

    def dispose(self) -> None:
        if self._engine is not None:
            self._engine.dispose()

    def _get_engine(self) -> Engine:
        if self._engine is None:
            self._engine = create_engine(self._database_url)
        return self._engine


class TenantRequestContext:
    """Make the verified principal's tenant available for the entire protected request."""

    def __init__(self, tenant_context: SqlServerTenantContext) -> None:
        self._tenant_context = tenant_context

    @contextmanager
    def request(self, organization_id: UUID) -> Iterator[Connection]:
        with self._tenant_context.connection(organization_id) as connection:
            g.tenant_connection = connection
            try:
                yield connection
            finally:
                g.pop("tenant_connection", None)


@dataclass(frozen=True, slots=True)
class _TenantTable:
    schema_name: str
    table_name: str

    @property
    def qualified_name(self) -> str:
        return f"{self.schema_name}.{self.table_name}"


def verify_tenant_catalog(connection: Connection) -> None:
    """Reject tenant tables without all RLS operations or tenant-aware relations."""
    tenant_tables = [
        _TenantTable(str(row.schema_name), str(row.table_name))
        for row in connection.execute(
            text(
                "SELECT schema_info.name AS schema_name, table_info.name AS table_name "
                "FROM sys.tables AS table_info "
                "JOIN sys.schemas AS schema_info ON schema_info.schema_id = table_info.schema_id "
                "JOIN sys.columns AS column_info ON column_info.object_id = table_info.object_id "
                "WHERE column_info.name = N'organization_id' "
                "ORDER BY schema_info.name, table_info.name"
            )
        )
    ]
    for tenant_table in tenant_tables:
        _verify_rls_predicates(connection, tenant_table)
    _verify_tenant_foreign_keys(connection)


def _verify_rls_predicates(connection: Connection, tenant_table: _TenantTable) -> None:
    rows = connection.execute(
        text(
            "SELECT predicate_type_desc, operation_desc "
            "FROM sys.security_predicates "
            "WHERE target_object_id = OBJECT_ID(:qualified_name)"
        ),
        {"qualified_name": tenant_table.qualified_name},
    )
    predicates = {(str(row.predicate_type_desc), row.operation_desc) for row in rows}
    expected = {
        ("FILTER", None),
        ("BLOCK", "AFTER INSERT"),
        ("BLOCK", "AFTER UPDATE"),
        ("BLOCK", "BEFORE DELETE"),
    }
    missing = expected - predicates
    if missing:
        operations = ", ".join(
            f"{kind} {operation or ''}".strip() for kind, operation in sorted(missing)
        )
        raise TenantCatalogError(
            f"{tenant_table.qualified_name} is missing tenant RLS predicates: {operations}"
        )


def _verify_tenant_foreign_keys(connection: Connection) -> None:
    rows = connection.execute(
        text(
            "SELECT foreign_key.name AS foreign_key_name, "
            "child_schema.name AS child_schema, child_table.name AS child_table, "
            "parent_schema.name AS parent_schema, parent_table.name AS parent_table, "
            "child_column.name AS child_column, parent_column.name AS parent_column "
            "FROM sys.foreign_keys AS foreign_key "
            "JOIN sys.foreign_key_columns AS foreign_key_column "
            "ON foreign_key_column.constraint_object_id = foreign_key.object_id "
            "JOIN sys.tables AS child_table ON child_table.object_id = foreign_key.parent_object_id "
            "JOIN sys.schemas AS child_schema ON child_schema.schema_id = child_table.schema_id "
            "JOIN sys.columns AS child_column ON child_column.object_id = child_table.object_id "
            "AND child_column.column_id = foreign_key_column.parent_column_id "
            "JOIN sys.tables AS parent_table ON parent_table.object_id = foreign_key.referenced_object_id "
            "JOIN sys.schemas AS parent_schema ON parent_schema.schema_id = parent_table.schema_id "
            "JOIN sys.columns AS parent_column ON parent_column.object_id = parent_table.object_id "
            "AND parent_column.column_id = foreign_key_column.referenced_column_id "
            "JOIN sys.columns AS parent_organization ON parent_organization.object_id = parent_table.object_id "
            "AND parent_organization.name = N'organization_id'"
        )
    )
    foreign_keys: dict[tuple[str, str, str, str, str], set[tuple[str, str]]] = {}
    for row in rows:
        key = (
            str(row.foreign_key_name),
            str(row.child_schema),
            str(row.child_table),
            str(row.parent_schema),
            str(row.parent_table),
        )
        foreign_keys.setdefault(key, set()).add(
            (str(row.child_column), str(row.parent_column))
        )
    for (
        name,
        child_schema,
        child_table,
        parent_schema,
        parent_table,
    ), columns in foreign_keys.items():
        if ("organization_id", "organization_id") not in columns:
            raise TenantCatalogError(
                f"{child_schema}.{child_table} foreign key {name} to "
                f"{parent_schema}.{parent_table} omits organization_id"
            )
