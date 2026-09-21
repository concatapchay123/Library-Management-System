"""Real SQL Server catalog checks for the BE-010 RBAC schema."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from openlibrary.infrastructure.sqlserver.migrate import (
    bootstrap_database_identities,
    connect,
    database_url_for,
    run_migrations,
)
from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.authorization import (
    AuthorizationService,
    RbacService,
)
from openlibrary.modules.core.infrastructure.organizations import set_tenant_context
from openlibrary.modules.core.infrastructure.rbac import SqlServerRbacStore


@pytest.fixture(scope="module")
def rbac_database_urls() -> dict[str, str]:
    """Migrate an isolated database only when real SQL Server credentials exist."""
    required = (
        "DATABASE_BOOTSTRAP_URL",
        "DATABASE_MIGRATION_URL",
        "DATABASE_RUNTIME_URL",
    )
    missing = [name for name in required if not os.environ.get(name, "").strip()]
    if missing:
        pytest.skip(f"SQL Server integration requires: {', '.join(missing)}")
    database_name = f"openlibrary_be010_{uuid4().hex}"
    bootstrap_url = os.environ["DATABASE_BOOTSTRAP_URL"]
    with connect(bootstrap_url, database="master") as connection:
        connection.execute(f"CREATE DATABASE [{database_name}]")
    migration_login = f"be010_migrator_{uuid4().hex}"
    runtime_login = f"be010_runtime_{uuid4().hex}"
    urls = {
        "bootstrap": database_url_for(bootstrap_url, database_name),
        "migration": make_url(
            database_url_for(os.environ["DATABASE_MIGRATION_URL"], database_name)
        )
        .set(username=migration_login)
        .render_as_string(hide_password=False),
        "runtime": make_url(
            database_url_for(os.environ["DATABASE_RUNTIME_URL"], database_name)
        )
        .set(username=runtime_login)
        .render_as_string(hide_password=False),
    }
    try:
        identities = bootstrap_database_identities(
            bootstrap_url=urls["bootstrap"],
            migration_url=urls["migration"],
            runtime_url=urls["runtime"],
        )
        run_migrations(urls["migration"], runtime_login=identities.runtime_login)
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


def test_rbac_tables_have_composite_relations_and_complete_rls(
    rbac_database_urls: dict[str, str],
) -> None:
    """A live upgrade creates the tenant ownership controls declared by BE-010."""
    expected_predicates = {
        ("FILTER", None),
        ("BLOCK", "AFTER INSERT"),
        ("BLOCK", "AFTER UPDATE"),
        ("BLOCK", "BEFORE DELETE"),
    }
    engine = create_engine(rbac_database_urls["migration"])
    try:
        with engine.connect() as connection:
            tables = {
                str(row.name)
                for row in connection.execute(
                    text(
                        "SELECT name FROM sys.tables "
                        "WHERE schema_id = SCHEMA_ID('core') "
                        "AND name IN ('roles', 'permissions', 'user_roles', "
                        "'role_permissions')"
                    )
                )
            }
            predicates = {
                table: {
                    (
                        str(row.predicate_type_desc).replace("_PREDICATE", ""),
                        row.operation_desc,
                    )
                    for row in connection.execute(
                        text(
                            "SELECT predicate_type_desc, operation_desc "
                            "FROM sys.security_predicates "
                            "WHERE target_object_id = OBJECT_ID(:table_name)"
                        ),
                        {"table_name": f"core.{table}"},
                    )
                }
                for table in tables
            }
            foreign_key_columns = {
                (
                    str(row.parent_table),
                    str(row.referenced_table),
                    str(row.parent_column),
                )
                for row in connection.execute(
                    text(
                        "SELECT OBJECT_NAME(fkc.parent_object_id) AS parent_table, "
                        "OBJECT_NAME(fkc.referenced_object_id) AS referenced_table, "
                        "COL_NAME(fkc.parent_object_id, fkc.parent_column_id) "
                        "AS parent_column FROM sys.foreign_key_columns AS fkc "
                        "WHERE OBJECT_NAME(fkc.parent_object_id) IN "
                        "('user_roles', 'role_permissions')"
                    )
                )
            }
    finally:
        engine.dispose()

    assert tables == {"roles", "permissions", "user_roles", "role_permissions"}
    assert all(values == expected_predicates for values in predicates.values())
    assert ("user_roles", "users", "organization_id") in foreign_key_columns
    assert ("user_roles", "roles", "organization_id") in foreign_key_columns
    assert ("role_permissions", "roles", "organization_id") in foreign_key_columns
    assert (
        "role_permissions",
        "permissions",
        "organization_id",
    ) in foreign_key_columns


def test_sql_server_assignment_revocation_and_audit_are_tenant_scoped(
    rbac_database_urls: dict[str, str],
) -> None:
    """The live adapter reads revocations immediately and persists both audit events."""
    organization_id = uuid4()
    actor_user_id = uuid4()
    target_user_id = uuid4()
    manager_role_id = uuid4()
    target_role_id = uuid4()
    manage_permission_id = uuid4()
    target_permission_id = uuid4()
    with connect(rbac_database_urls["bootstrap"]) as connection:
        connection.execute(
            "INSERT INTO core.organizations "
            "(organization_id, name, slug, organization_type, status, timezone, "
            "settings_json) VALUES "
            f"('{organization_id}', N'BE-010 tenant', 'be010-{organization_id.hex[:12]}', "
            "'education', 'active', 'UTC', N'{}')"
        )
        for user_id, email in (
            (actor_user_id, "manager@example.test"),
            (target_user_id, "target@example.test"),
        ):
            connection.execute(
                "INSERT INTO core.users "
                "(user_id, organization_id, email, password_hash, status) VALUES "
                f"('{user_id}', '{organization_id}', '{email}', 'not-a-secret', 'active')"
            )

    engine = create_engine(rbac_database_urls["runtime"])
    try:
        with engine.connect() as connection:
            set_tenant_context(connection, organization_id)
            connection.execute(
                text(
                    "INSERT INTO core.roles (role_id, organization_id, name) VALUES "
                    "(:role_id, :organization_id, :name)"
                ),
                {
                    "role_id": str(manager_role_id),
                    "organization_id": str(organization_id),
                    "name": "manager",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO core.roles (role_id, organization_id, name) VALUES "
                    "(:role_id, :organization_id, :name)"
                ),
                {
                    "role_id": str(target_role_id),
                    "organization_id": str(organization_id),
                    "name": "catalog-editor",
                },
            )
            for permission_id, code in (
                (manage_permission_id, "role.manage"),
                (target_permission_id, "catalog.manage"),
            ):
                connection.execute(
                    text(
                        "INSERT INTO core.permissions "
                        "(permission_id, organization_id, code) VALUES "
                        "(:permission_id, :organization_id, :code)"
                    ),
                    {
                        "permission_id": str(permission_id),
                        "organization_id": str(organization_id),
                        "code": code,
                    },
                )
            connection.execute(
                text(
                    "INSERT INTO core.user_roles (organization_id, user_id, role_id) "
                    "VALUES (:organization_id, :user_id, :role_id)"
                ),
                {
                    "organization_id": str(organization_id),
                    "user_id": str(actor_user_id),
                    "role_id": str(manager_role_id),
                },
            )
            for role_id, permission_id in (
                (manager_role_id, manage_permission_id),
                (target_role_id, target_permission_id),
            ):
                connection.execute(
                    text(
                        "INSERT INTO core.role_permissions "
                        "(organization_id, role_id, permission_id) VALUES "
                        "(:organization_id, :role_id, :permission_id)"
                    ),
                    {
                        "organization_id": str(organization_id),
                        "role_id": str(role_id),
                        "permission_id": str(permission_id),
                    },
                )
            connection.commit()
    finally:
        engine.dispose()

    actor = Principal(actor_user_id, organization_id, uuid4())
    target = Principal(target_user_id, organization_id, uuid4())
    store = SqlServerRbacStore(rbac_database_urls["runtime"])
    authorizer = AuthorizationService(store)
    rbac = RbacService(store, authorizer)

    rbac.assign_role(user_id=target_user_id, role_id=target_role_id, actor=actor)
    assert authorizer.allows(target, "catalog.manage")
    rbac.revoke_role(user_id=target_user_id, role_id=target_role_id, actor=actor)
    assert not authorizer.allows(target, "catalog.manage")

    audit_engine = create_engine(rbac_database_urls["runtime"])
    try:
        with audit_engine.connect() as connection:
            set_tenant_context(connection, organization_id)
            actions = {
                str(row.action)
                for row in connection.execute(
                    text(
                        "SELECT action FROM ops.audit_events "
                        "WHERE entity_type = 'user_role' AND entity_id = :role_id"
                    ),
                    {"role_id": str(target_role_id)},
                )
            }
    finally:
        audit_engine.dispose()

    assert actions == {"rbac.role_assigned", "rbac.role_revoked"}
