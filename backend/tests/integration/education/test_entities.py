"""Integration tests for education entities and tenant-scoped relations."""

from __future__ import annotations

from collections.abc import Iterator
import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError

from openlibrary.infrastructure.sqlserver.migrate import (
    bootstrap_database_identities,
    connect,
    database_url_for,
    run_migrations,
)
from openlibrary.modules.core.infrastructure.tenancy import (
    verify_tenant_catalog,
)
from openlibrary.modules.education.infrastructure import SqlServerEducationStore


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
    database_name = f"openlibrary_be020_{uuid4().hex}"
    with connect(database_urls["DATABASE_BOOTSTRAP_URL"], database="master") as server:
        server.execute(f"CREATE DATABASE [{database_name}]")
    urls = {
        name: database_url_for(url, database_name)
        for name, url in database_urls.items()
    }
    migration_login = f"be020_migrator_{uuid4().hex}"
    runtime_login = f"be020_runtime_{uuid4().hex}"
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


def _seed_education_tenants(url: str) -> tuple[UUID, UUID, UUID]:
    """Seed three tenants: two education tenants and one public library tenant."""
    org_edu_a, org_edu_b, org_pub = uuid4(), uuid4(), uuid4()
    with create_engine(url).begin() as connection:
        connection.execute(
            text(
                "INSERT INTO core.organizations "
                "(organization_id, name, slug, organization_type, status, timezone, settings_json) "
                "VALUES (:a, N'Edu Org A', :a_slug, 'education', 'active', 'UTC', N'{}'), "
                "(:b, N'Edu Org B', :b_slug, 'education', 'active', 'UTC', N'{}'), "
                "(:c, N'Public Library', :c_slug, 'public_library', 'active', 'UTC', N'{}')"
            ),
            {
                "a": str(org_edu_a),
                "b": str(org_edu_b),
                "c": str(org_pub),
                "a_slug": f"edu-a-{uuid4().hex[:8]}",
                "b_slug": f"edu-b-{uuid4().hex[:8]}",
                "c_slug": f"pub-{uuid4().hex[:8]}",
            },
        )
    return org_edu_a, org_edu_b, org_pub


def test_tenant_catalog_verifies_all_education_tables(
    tenant_database_urls: dict[str, str],
) -> None:
    """The tenant catalog verifier must pass for all newly migrated education tables."""
    engine = create_engine(tenant_database_urls["DATABASE_MIGRATION_URL"])
    with engine.connect() as connection:
        verify_tenant_catalog(connection)


def test_student_and_teacher_identifiers_are_unique_only_per_tenant(
    tenant_database_urls: dict[str, str],
) -> None:
    """Student and teacher identifiers can be shared across tenants, but not within a tenant."""
    org_a, org_b, _ = _seed_education_tenants(
        tenant_database_urls["DATABASE_BOOTSTRAP_URL"]
    )
    user_a1, user_a2 = uuid4(), uuid4()
    user_b1 = uuid4()
    user_t_a1, user_t_b1 = uuid4(), uuid4()

    with create_engine(
        tenant_database_urls["DATABASE_BOOTSTRAP_URL"]
    ).begin() as connection:
        # Seed users in core.users
        for org, u, email in [
            (org_a, user_a1, f"a1_{uuid4().hex[:6]}@example.com"),
            (org_a, user_a2, f"a2_{uuid4().hex[:6]}@example.com"),
            (org_b, user_b1, f"b1_{uuid4().hex[:6]}@example.com"),
            (org_a, user_t_a1, f"ta1_{uuid4().hex[:6]}@example.com"),
            (org_b, user_t_b1, f"tb1_{uuid4().hex[:6]}@example.com"),
        ]:
            connection.execute(
                text(
                    "INSERT INTO core.users (user_id, organization_id, email, password_hash, status) "
                    "VALUES (:user_id, :org_id, :email, 'hash', 'active')"
                ),
                {"user_id": str(u), "org_id": str(org), "email": email},
            )

        # Student with identifier 'STU-001' in Org A
        connection.execute(
            text(
                "INSERT INTO education.students (student_id, organization_id, user_id, student_number, status) "
                "VALUES (:student_id, :org_id, :user_id, 'STU-001', 'active')"
            ),
            {"student_id": str(uuid4()), "org_id": str(org_a), "user_id": str(user_a1)},
        )

        # Same identifier 'STU-001' is ALLOWED in Org B
        connection.execute(
            text(
                "INSERT INTO education.students (student_id, organization_id, user_id, student_number, status) "
                "VALUES (:student_id, :org_id, :user_id, 'STU-001', 'active')"
            ),
            {"student_id": str(uuid4()), "org_id": str(org_b), "user_id": str(user_b1)},
        )

        # Duplicate identifier 'STU-001' in Org A must be REJECTED
        with pytest.raises((IntegrityError, DBAPIError)):
            connection.execute(
                text(
                    "INSERT INTO education.students (student_id, organization_id, user_id, student_number, status) "
                    "VALUES (:student_id, :org_id, :user_id, 'STU-001', 'active')"
                ),
                {
                    "student_id": str(uuid4()),
                    "org_id": str(org_a),
                    "user_id": str(user_a2),
                },
            )

        # Teacher with employee number 'EMP-001' in Org A
        connection.execute(
            text(
                "INSERT INTO education.teachers (teacher_id, organization_id, user_id, employee_number, status) "
                "VALUES (:teacher_id, :org_id, :user_id, 'EMP-001', 'active')"
            ),
            {
                "teacher_id": str(uuid4()),
                "org_id": str(org_a),
                "user_id": str(user_t_a1),
            },
        )

        # Same employee number 'EMP-001' is ALLOWED in Org B
        connection.execute(
            text(
                "INSERT INTO education.teachers (teacher_id, organization_id, user_id, employee_number, status) "
                "VALUES (:teacher_id, :org_id, :user_id, 'EMP-001', 'active')"
            ),
            {
                "teacher_id": str(uuid4()),
                "org_id": str(org_b),
                "user_id": str(user_t_b1),
            },
        )


def test_invalid_semester_dates_rejected_by_check_constraint(
    tenant_database_urls: dict[str, str],
) -> None:
    """Semester date range where starts_on >= ends_on must be rejected."""
    org_a, _, _ = _seed_education_tenants(
        tenant_database_urls["DATABASE_BOOTSTRAP_URL"]
    )
    with create_engine(
        tenant_database_urls["DATABASE_BOOTSTRAP_URL"]
    ).begin() as connection:
        with pytest.raises((IntegrityError, DBAPIError)):
            connection.execute(
                text(
                    "INSERT INTO education.semesters (semester_id, organization_id, name, starts_on, ends_on, status) "
                    "VALUES (:semester_id, :org_id, 'Fall 2026', '2026-12-31', '2026-09-01', 'active')"
                ),
                {"semester_id": str(uuid4()), "org_id": str(org_a)},
            )


def test_invalid_class_membership_dates_rejected(
    tenant_database_urls: dict[str, str],
) -> None:
    """Class membership where left_at < joined_at must be rejected."""
    org_a, _, _ = _seed_education_tenants(
        tenant_database_urls["DATABASE_BOOTSTRAP_URL"]
    )
    user_id = uuid4()
    student_id = uuid4()
    semester_id = uuid4()
    class_id = uuid4()

    with create_engine(
        tenant_database_urls["DATABASE_BOOTSTRAP_URL"]
    ).begin() as connection:
        connection.execute(
            text(
                "INSERT INTO core.users (user_id, organization_id, email, password_hash, status) "
                "VALUES (:user_id, :org_id, :email, 'hash', 'active')"
            ),
            {
                "user_id": str(user_id),
                "org_id": str(org_a),
                "email": f"m_{uuid4().hex[:6]}@example.com",
            },
        )
        connection.execute(
            text(
                "INSERT INTO education.students (student_id, organization_id, user_id, student_number, status) "
                "VALUES (:student_id, :org_id, :user_id, :num, 'active')"
            ),
            {
                "student_id": str(student_id),
                "org_id": str(org_a),
                "user_id": str(user_id),
                "num": f"S-{uuid4().hex[:6]}",
            },
        )
        connection.execute(
            text(
                "INSERT INTO education.semesters (semester_id, organization_id, name, starts_on, ends_on, status) "
                "VALUES (:semester_id, :org_id, 'Sem 1', '2026-01-01', '2026-06-30', 'active')"
            ),
            {"semester_id": str(semester_id), "org_id": str(org_a)},
        )
        connection.execute(
            text(
                "INSERT INTO education.classes (class_id, organization_id, code, name, semester_id, status) "
                "VALUES (:class_id, :org_id, :code, 'Math 101', :semester_id, 'active')"
            ),
            {
                "class_id": str(class_id),
                "org_id": str(org_a),
                "code": f"CLS-{uuid4().hex[:6]}",
                "semester_id": str(semester_id),
            },
        )

        with pytest.raises((IntegrityError, DBAPIError)):
            connection.execute(
                text(
                    "INSERT INTO education.class_memberships "
                    "(membership_id, organization_id, class_id, student_id, joined_at, left_at) "
                    "VALUES (:m_id, :org_id, :class_id, :student_id, '2026-05-01', '2026-04-01')"
                ),
                {
                    "m_id": str(uuid4()),
                    "org_id": str(org_a),
                    "class_id": str(class_id),
                    "student_id": str(student_id),
                },
            )


def test_cross_tenant_composite_foreign_keys_prevented(
    tenant_database_urls: dict[str, str],
) -> None:
    """An education entity in Org A cannot reference an entity in Org B."""
    org_a, org_b, _ = _seed_education_tenants(
        tenant_database_urls["DATABASE_BOOTSTRAP_URL"]
    )
    semester_b = uuid4()
    with create_engine(
        tenant_database_urls["DATABASE_BOOTSTRAP_URL"]
    ).begin() as connection:
        connection.execute(
            text(
                "INSERT INTO education.semesters (semester_id, organization_id, name, starts_on, ends_on, status) "
                "VALUES (:semester_id, :org_id, 'Sem Org B', '2026-01-01', '2026-06-30', 'active')"
            ),
            {"semester_id": str(semester_b), "org_id": str(org_b)},
        )

        # Trying to create a class in Org A referencing semester_b in Org B must fail FK constraint
        with pytest.raises((IntegrityError, DBAPIError)):
            connection.execute(
                text(
                    "INSERT INTO education.classes (class_id, organization_id, code, name, semester_id, status) "
                    "VALUES (:class_id, :org_id, 'CLS-CROSS', 'Cross Org Class', :semester_id, 'active')"
                ),
                {
                    "class_id": str(uuid4()),
                    "org_id": str(org_a),
                    "semester_id": str(semester_b),
                },
            )


def test_cross_tenant_access_rejected_by_rls(
    tenant_database_urls: dict[str, str],
) -> None:
    """A runtime session for Org A cannot read or write Org B's education records."""
    org_a, org_b, _ = _seed_education_tenants(
        tenant_database_urls["DATABASE_BOOTSTRAP_URL"]
    )
    dept_a, dept_b = uuid4(), uuid4()

    # Seed through migration login (unrestricted by RLS)
    with create_engine(
        tenant_database_urls["DATABASE_BOOTSTRAP_URL"]
    ).begin() as connection:
        connection.execute(
            text(
                "INSERT INTO education.departments (department_id, organization_id, code, name, status) "
                "VALUES (:id_a, :org_a, 'CS-A', 'Computer Science A', 'active'), "
                "(:id_b, :org_b, 'CS-B', 'Computer Science B', 'active')"
            ),
            {
                "id_a": str(dept_a),
                "org_a": str(org_a),
                "id_b": str(dept_b),
                "org_b": str(org_b),
            },
        )

    # Connect with runtime login and set session context for Org A
    runtime_engine = create_engine(tenant_database_urls["DATABASE_RUNTIME_URL"])
    with runtime_engine.connect() as connection:
        connection.execute(
            text("EXEC sp_set_session_context @key=N'organization_id', @value=:org_id"),
            {"org_id": str(org_a)},
        )

        # SELECT: Org A should see only CS-A
        rows = connection.execute(
            text("SELECT department_id, code FROM education.departments")
        ).fetchall()
        dept_ids = [UUID(str(row.department_id)) for row in rows]
        assert dept_a in dept_ids
        assert dept_b not in dept_ids

        # UPDATE: Org A trying to update CS-B affects 0 rows or is blocked
        result = connection.execute(
            text(
                "UPDATE education.departments SET name = 'Hacked' WHERE department_id = :id_b"
            ),
            {"id_b": str(dept_b)},
        )
        assert result.rowcount == 0

        # INSERT: Org A trying to insert row with organization_id = Org B must be blocked by RLS
        with pytest.raises((IntegrityError, DBAPIError)):
            connection.execute(
                text(
                    "INSERT INTO education.departments (department_id, organization_id, code, name, status) "
                    "VALUES (:id, :org_b, 'MAL-B', 'Malicious', 'active')"
                ),
                {"id": str(uuid4()), "org_b": str(org_b)},
            )


def test_education_service_rejects_disabled_edition(
    tenant_database_urls: dict[str, str],
) -> None:
    """An organization without the education edition enabled is rejected with EditionUnavailableError."""
    _, _, org_pub = _seed_education_tenants(
        tenant_database_urls["DATABASE_BOOTSTRAP_URL"]
    )
    store = SqlServerEducationStore(tenant_database_urls["DATABASE_RUNTIME_URL"])
    # Public library organization has organization_type = 'public_library' and no education setting
    assert store.is_edition_enabled(org_pub) is False
