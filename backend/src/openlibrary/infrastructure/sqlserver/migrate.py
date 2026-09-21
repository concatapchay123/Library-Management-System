"""SQL Server migration bootstrap and runtime-permission verification."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
import re
from typing import Protocol, cast

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url


_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}\Z")
_DEFAULT_MIGRATION_LOGIN = "openlibrary_migrator"
_DEFAULT_RUNTIME_LOGIN = "openlibrary_runtime"


class _Cursor(Protocol):
    """The small cursor surface used by the SQL Server adapter."""

    def execute(self, statement: str) -> "_Cursor": ...

    def fetchone(self) -> tuple[object, ...] | None: ...

    def __iter__(self) -> Iterator[tuple[object, ...]]: ...


class _PyodbcConnection(Protocol):
    """The small connection surface used by the SQL Server adapter."""

    def cursor(self) -> _Cursor: ...

    def close(self) -> None: ...


class _PyodbcModule(Protocol):
    """Typed boundary for pyodbc, which does not publish typing metadata."""

    def connect(
        self, connection_string: str, *, autocommit: bool
    ) -> _PyodbcConnection: ...


pyodbc = cast(_PyodbcModule, import_module("pyodbc"))


class RuntimePermissionError(RuntimeError):
    """Raised when the runtime identity has an unsafe SQL Server permission."""


@dataclass(frozen=True, slots=True)
class DatabaseIdentities:
    """Validated migration and runtime login names from deployment URLs."""

    migration_login: str
    runtime_login: str


class SqlServerConnection:
    """Small autocommit wrapper for SQL Server bootstrap and catalog operations."""

    def __init__(self, connection: _PyodbcConnection) -> None:
        self._connection = connection

    def execute(self, statement: str) -> None:
        """Execute one trusted SQL Server statement."""
        cursor = self._connection.cursor()
        try:
            cursor.execute(statement)
        finally:
            del statement

    def fetch_value(self, statement: str) -> object:
        """Return the first column of the first row from a catalog query."""
        row = self._connection.cursor().execute(statement).fetchone()
        if row is None:
            raise LookupError("SQL Server query returned no rows")
        return row[0]

    def fetch_values(self, statement: str) -> list[object]:
        """Return the first column from every row in a catalog query."""
        return [row[0] for row in self._connection.cursor().execute(statement)]


@contextmanager
def connect(
    database_url: str, database: str | None = None
) -> Iterator[SqlServerConnection]:
    """Connect through the SQL Server ODBC driver without logging credentials."""
    connection_string = _odbc_connection_string(database_url, database)
    del database_url
    try:
        connection = pyodbc.connect(connection_string, autocommit=True)
    finally:
        del connection_string
    try:
        yield SqlServerConnection(connection)
    finally:
        connection.close()


def database_url_for(database_url: str, database_name: str) -> str:
    """Return an existing SQLAlchemy URL pointed at one selected database name."""
    if not database_name:
        raise ValueError("SQL Server database name is required")
    return (
        make_url(database_url)
        .set(database=database_name)
        .render_as_string(hide_password=False)
    )


def bootstrap_database_identities(
    *,
    bootstrap_url: str,
    migration_url: str,
    runtime_url: str,
) -> DatabaseIdentities:
    """Create distinct logins/users before migrations run against an empty database."""
    migration = make_url(migration_url)
    runtime = make_url(runtime_url)
    database_name = migration.database or ""
    if not database_name:
        raise ValueError("Migration SQL Server URL requires a database name")
    migration_login = _identifier(migration.username or "")
    runtime_login = _identifier(runtime.username or "")
    if migration_login == runtime_login:
        raise ValueError("Migration and runtime SQL Server identities must differ")
    if not migration.password or not runtime.password:
        raise ValueError("Migration and runtime SQL Server URLs require passwords")

    with connect(bootstrap_url, database="master") as server:
        _create_login(server, migration_login, migration.password)
        _create_login(server, runtime_login, runtime.password)

    with connect(bootstrap_url, database=database_name) as database:
        _ensure_database_master_key(database, migration.password)
        _create_database_user(database, migration_login)
        _create_database_user(database, runtime_login)
        database.execute(
            "IF IS_ROLEMEMBER('db_ddladmin', "
            f"N'{migration_login}') = 0 "
            f"ALTER ROLE db_ddladmin ADD MEMBER [{migration_login}]"
        )
        database.execute(f"GRANT ALTER ANY SECURITY POLICY TO [{migration_login}]")
        database.execute(f"GRANT ALTER ANY CERTIFICATE TO [{migration_login}]")
        database.execute(f"GRANT ALTER ANY USER TO [{migration_login}]")
        database.execute(f"GRANT ALTER ANY ROLE TO [{migration_login}]")
        database.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON SCHEMA::dbo TO [{migration_login}]"
        )
    return DatabaseIdentities(
        migration_login=migration_login,
        runtime_login=runtime_login,
    )


def run_migrations(
    database_url: str, *, runtime_login: str = _DEFAULT_RUNTIME_LOGIN
) -> None:
    """Apply every Alembic revision through the migration-only database URL."""
    config_path = Path.cwd() / "alembic.ini"
    if not config_path.is_file():
        raise RuntimeError(
            "Run migrations from the backend directory containing alembic.ini"
        )
    config = Config(str(config_path))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    config.attributes["runtime_login"] = _identifier(runtime_login)
    command.upgrade(config, "head")


def verify_runtime_restrictions(
    runtime_url: str, *, migration_login: str = _DEFAULT_MIGRATION_LOGIN
) -> None:
    """Fail closed when the runtime login gains ownership or forbidden capabilities."""
    runtime = make_url(runtime_url)
    migration_login = _identifier(migration_login)
    runtime_login = _identifier(runtime.username or "")
    with connect(runtime_url) as connection:
        is_db_owner = connection.fetch_value("SELECT IS_MEMBER('db_owner')")
        control = connection.fetch_value(
            "SELECT HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'CONTROL')"
        )
        security_policy = connection.fetch_value(
            "SELECT HAS_PERMS_BY_NAME("
            "DB_NAME(), 'DATABASE', 'ALTER ANY SECURITY POLICY')"
        )
        impersonate = connection.fetch_value(
            f"SELECT HAS_PERMS_BY_NAME('{migration_login}', 'LOGIN', 'IMPERSONATE')"
        )

    forbidden = {
        "db_owner": is_db_owner,
        "CONTROL": control,
        "ALTER ANY SECURITY POLICY": security_policy,
        f"IMPERSONATE {migration_login}": impersonate,
    }
    present = [name for name, value in forbidden.items() if value == 1]
    if present:
        raise RuntimePermissionError(
            f"Runtime identity [{runtime_login}] has forbidden permissions: {', '.join(present)}"
        )


def _create_login(
    connection: SqlServerConnection, login_name: str, password: str
) -> None:
    escaped_password = password.replace("'", "''")
    connection.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.server_principals "
        f"WHERE name = N'{login_name}') "
        f"CREATE LOGIN [{login_name}] WITH PASSWORD = N'{escaped_password}', "
        "CHECK_POLICY = ON"
    )


def _ensure_database_master_key(connection: SqlServerConnection, password: str) -> None:
    """Create the database master key once for migration-owned module signing."""
    escaped_password = password.replace("'", "''")
    statement = (
        "IF NOT EXISTS (SELECT 1 FROM sys.symmetric_keys "
        "WHERE name = N'##MS_DatabaseMasterKey##') "
        "CREATE MASTER KEY ENCRYPTION BY PASSWORD = "
        f"N'{escaped_password}'"
    )
    del password
    del escaped_password
    try:
        connection.execute(statement)
    finally:
        del statement


def _create_database_user(connection: SqlServerConnection, login_name: str) -> None:
    connection.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.database_principals "
        f"WHERE name = N'{login_name}') "
        f"CREATE USER [{login_name}] FOR LOGIN [{login_name}]"
    )


def _odbc_connection_string(database_url: str, database: str | None) -> str:
    url = make_url(database_url)
    if url.drivername != "mssql+pyodbc":
        raise ValueError("SQL Server URLs must use the mssql+pyodbc dialect")
    if not url.host or not url.username or url.password is None:
        raise ValueError("SQL Server URL requires host, username, and password")
    selected_database = database or url.database
    if not selected_database:
        raise ValueError("SQL Server URL requires a database name")
    driver = url.query.get("driver", "ODBC Driver 18 for SQL Server")
    server = url.host if url.port is None else f"{url.host},{url.port}"
    attributes = [
        f"DRIVER={{{driver}}}",
        f"SERVER={server}",
        f"DATABASE={selected_database}",
        f"UID={url.username}",
        f"PWD={_odbc_value(url.password)}",
    ]
    for key in ("Encrypt", "TrustServerCertificate"):
        value = url.query.get(key)
        if value:
            attributes.append(f"{key}={value}")
    return ";".join(attributes)


def _identifier(value: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"Unsafe SQL Server identifier: {value!r}")
    return value


def _odbc_value(value: str) -> str:
    """Brace an ODBC value so configured passwords cannot terminate its field."""
    return "{" + value.replace("}", "}}") + "}"
