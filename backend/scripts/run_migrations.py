"""Run the clean-database SQL Server bootstrap and Alembic migration command."""

from __future__ import annotations

import os

from openlibrary.infrastructure.sqlserver.migrate import (
    bootstrap_database_identities,
    run_migrations,
    verify_runtime_restrictions,
)


def main() -> None:
    """Read operator-owned credentials and run the migration-only workflow."""
    bootstrap_url = _required("DATABASE_BOOTSTRAP_URL")
    migration_url = _required("DATABASE_MIGRATION_URL")
    runtime_url = _required("DATABASE_RUNTIME_URL")
    identities = bootstrap_database_identities(
        bootstrap_url=bootstrap_url,
        migration_url=migration_url,
        runtime_url=runtime_url,
    )
    run_migrations(migration_url, runtime_login=identities.runtime_login)
    verify_runtime_restrictions(
        runtime_url,
        migration_login=identities.migration_login,
    )
    print("SQL Server migration and runtime permission verification succeeded.")


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required setting: {name}")
    return value


if __name__ == "__main__":
    main()
