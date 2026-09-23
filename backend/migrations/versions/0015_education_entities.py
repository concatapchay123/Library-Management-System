"""Create education entities and tenant-scoped relations with RLS.

Revision ID: 0015_education_entities
Revises: 0014_reservations
Create Date: 2026-09-23
"""

from alembic import op


revision = "0015_education_entities"
down_revision = "0014_reservations"
branch_labels = None
depends_on = None

_TABLES = [
    "education.departments",
    "education.semesters",
    "education.courses",
    "education.classes",
    "education.students",
    "education.teachers",
    "education.class_memberships",
    "education.borrower_policies",
]


def _add_tenant_predicates(table_name: str) -> None:
    """Attach every data operation to the shared fail-closed tenant policy."""
    op.execute(
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        "ADD FILTER PREDICATE core.tenant_access_predicate(organization_id) "
        f"ON {table_name}"
    )
    for operation in ("AFTER INSERT", "AFTER UPDATE", "BEFORE DELETE"):
        op.execute(
            "ALTER SECURITY POLICY core.organization_tenant_policy "
            "ADD BLOCK PREDICATE core.tenant_access_predicate(organization_id) "
            f"ON {table_name} {operation}"
        )


def _drop_tenant_predicates(table_name: str) -> None:
    """Detach all predicates before dropping a tenant-owned table."""
    op.execute(
        "ALTER SECURITY POLICY core.organization_tenant_policy "
        f"DROP FILTER PREDICATE ON {table_name}"
    )
    for operation in ("AFTER INSERT", "AFTER UPDATE", "BEFORE DELETE"):
        op.execute(
            "ALTER SECURITY POLICY core.organization_tenant_policy "
            f"DROP BLOCK PREDICATE ON {table_name} {operation}"
        )


def upgrade() -> None:
    """Create education tables with composite tenant keys and RLS predicates."""
    # 1. departments
    op.execute(
        "CREATE TABLE education.departments ("
        "department_id uniqueidentifier NOT NULL "
        "CONSTRAINT PK_education_departments PRIMARY KEY, "
        "organization_id uniqueidentifier NOT NULL, "
        "code nvarchar(64) NOT NULL, "
        "name nvarchar(255) NOT NULL, "
        "status varchar(32) NOT NULL CONSTRAINT DF_education_departments_status DEFAULT 'active', "
        "created_at datetime2 NOT NULL CONSTRAINT DF_education_departments_created_at DEFAULT SYSUTCDATETIME(), "
        "updated_at datetime2 NOT NULL CONSTRAINT DF_education_departments_updated_at DEFAULT SYSUTCDATETIME(), "
        "CONSTRAINT UQ_education_departments_org_dept UNIQUE (organization_id, department_id), "
        "CONSTRAINT UQ_education_departments_org_code UNIQUE (organization_id, code), "
        "CONSTRAINT FK_education_departments_organization FOREIGN KEY (organization_id) REFERENCES core.organizations (organization_id))"
    )
    _add_tenant_predicates("education.departments")

    # 2. semesters
    op.execute(
        "CREATE TABLE education.semesters ("
        "semester_id uniqueidentifier NOT NULL "
        "CONSTRAINT PK_education_semesters PRIMARY KEY, "
        "organization_id uniqueidentifier NOT NULL, "
        "name nvarchar(255) NOT NULL, "
        "starts_on date NOT NULL, "
        "ends_on date NOT NULL, "
        "status varchar(32) NOT NULL CONSTRAINT DF_education_semesters_status DEFAULT 'active', "
        "created_at datetime2 NOT NULL CONSTRAINT DF_education_semesters_created_at DEFAULT SYSUTCDATETIME(), "
        "updated_at datetime2 NOT NULL CONSTRAINT DF_education_semesters_updated_at DEFAULT SYSUTCDATETIME(), "
        "CONSTRAINT CK_education_semesters_dates CHECK (starts_on < ends_on), "
        "CONSTRAINT UQ_education_semesters_org_sem UNIQUE (organization_id, semester_id), "
        "CONSTRAINT UQ_education_semesters_org_name UNIQUE (organization_id, name), "
        "CONSTRAINT FK_education_semesters_organization FOREIGN KEY (organization_id) REFERENCES core.organizations (organization_id))"
    )
    _add_tenant_predicates("education.semesters")

    # 3. courses
    op.execute(
        "CREATE TABLE education.courses ("
        "course_id uniqueidentifier NOT NULL "
        "CONSTRAINT PK_education_courses PRIMARY KEY, "
        "organization_id uniqueidentifier NOT NULL, "
        "code nvarchar(64) NOT NULL, "
        "name nvarchar(255) NOT NULL, "
        "department_id uniqueidentifier NULL, "
        "status varchar(32) NOT NULL CONSTRAINT DF_education_courses_status DEFAULT 'active', "
        "created_at datetime2 NOT NULL CONSTRAINT DF_education_courses_created_at DEFAULT SYSUTCDATETIME(), "
        "updated_at datetime2 NOT NULL CONSTRAINT DF_education_courses_updated_at DEFAULT SYSUTCDATETIME(), "
        "CONSTRAINT UQ_education_courses_org_course UNIQUE (organization_id, course_id), "
        "CONSTRAINT UQ_education_courses_org_code UNIQUE (organization_id, code), "
        "CONSTRAINT FK_education_courses_organization FOREIGN KEY (organization_id) REFERENCES core.organizations (organization_id), "
        "CONSTRAINT FK_education_courses_department FOREIGN KEY (organization_id, department_id) REFERENCES education.departments (organization_id, department_id))"
    )
    _add_tenant_predicates("education.courses")

    # 4. classes
    op.execute(
        "CREATE TABLE education.classes ("
        "class_id uniqueidentifier NOT NULL "
        "CONSTRAINT PK_education_classes PRIMARY KEY, "
        "organization_id uniqueidentifier NOT NULL, "
        "code nvarchar(64) NOT NULL, "
        "name nvarchar(255) NOT NULL, "
        "department_id uniqueidentifier NULL, "
        "semester_id uniqueidentifier NOT NULL, "
        "status varchar(32) NOT NULL CONSTRAINT DF_education_classes_status DEFAULT 'active', "
        "created_at datetime2 NOT NULL CONSTRAINT DF_education_classes_created_at DEFAULT SYSUTCDATETIME(), "
        "updated_at datetime2 NOT NULL CONSTRAINT DF_education_classes_updated_at DEFAULT SYSUTCDATETIME(), "
        "CONSTRAINT UQ_education_classes_org_class UNIQUE (organization_id, class_id), "
        "CONSTRAINT UQ_education_classes_org_code UNIQUE (organization_id, code), "
        "CONSTRAINT FK_education_classes_organization FOREIGN KEY (organization_id) REFERENCES core.organizations (organization_id), "
        "CONSTRAINT FK_education_classes_department FOREIGN KEY (organization_id, department_id) REFERENCES education.departments (organization_id, department_id), "
        "CONSTRAINT FK_education_classes_semester FOREIGN KEY (organization_id, semester_id) REFERENCES education.semesters (organization_id, semester_id))"
    )
    _add_tenant_predicates("education.classes")

    # 5. students
    op.execute(
        "CREATE TABLE education.students ("
        "student_id uniqueidentifier NOT NULL "
        "CONSTRAINT PK_education_students PRIMARY KEY, "
        "organization_id uniqueidentifier NOT NULL, "
        "user_id uniqueidentifier NOT NULL, "
        "student_number nvarchar(64) NOT NULL, "
        "department_id uniqueidentifier NULL, "
        "status varchar(32) NOT NULL CONSTRAINT DF_education_students_status DEFAULT 'active', "
        "created_at datetime2 NOT NULL CONSTRAINT DF_education_students_created_at DEFAULT SYSUTCDATETIME(), "
        "updated_at datetime2 NOT NULL CONSTRAINT DF_education_students_updated_at DEFAULT SYSUTCDATETIME(), "
        "CONSTRAINT UQ_education_students_org_student UNIQUE (organization_id, student_id), "
        "CONSTRAINT UQ_education_students_org_user UNIQUE (organization_id, user_id), "
        "CONSTRAINT UQ_education_students_org_number UNIQUE (organization_id, student_number), "
        "CONSTRAINT FK_education_students_organization FOREIGN KEY (organization_id) REFERENCES core.organizations (organization_id), "
        "CONSTRAINT FK_education_students_user FOREIGN KEY (organization_id, user_id) REFERENCES core.users (organization_id, user_id), "
        "CONSTRAINT FK_education_students_department FOREIGN KEY (organization_id, department_id) REFERENCES education.departments (organization_id, department_id))"
    )
    _add_tenant_predicates("education.students")

    # 6. teachers
    op.execute(
        "CREATE TABLE education.teachers ("
        "teacher_id uniqueidentifier NOT NULL "
        "CONSTRAINT PK_education_teachers PRIMARY KEY, "
        "organization_id uniqueidentifier NOT NULL, "
        "user_id uniqueidentifier NOT NULL, "
        "employee_number nvarchar(64) NOT NULL, "
        "department_id uniqueidentifier NULL, "
        "status varchar(32) NOT NULL CONSTRAINT DF_education_teachers_status DEFAULT 'active', "
        "created_at datetime2 NOT NULL CONSTRAINT DF_education_teachers_created_at DEFAULT SYSUTCDATETIME(), "
        "updated_at datetime2 NOT NULL CONSTRAINT DF_education_teachers_updated_at DEFAULT SYSUTCDATETIME(), "
        "CONSTRAINT UQ_education_teachers_org_teacher UNIQUE (organization_id, teacher_id), "
        "CONSTRAINT UQ_education_teachers_org_user UNIQUE (organization_id, user_id), "
        "CONSTRAINT UQ_education_teachers_org_number UNIQUE (organization_id, employee_number), "
        "CONSTRAINT FK_education_teachers_organization FOREIGN KEY (organization_id) REFERENCES core.organizations (organization_id), "
        "CONSTRAINT FK_education_teachers_user FOREIGN KEY (organization_id, user_id) REFERENCES core.users (organization_id, user_id), "
        "CONSTRAINT FK_education_teachers_department FOREIGN KEY (organization_id, department_id) REFERENCES education.departments (organization_id, department_id))"
    )
    _add_tenant_predicates("education.teachers")

    # 7. class_memberships
    op.execute(
        "CREATE TABLE education.class_memberships ("
        "membership_id uniqueidentifier NOT NULL "
        "CONSTRAINT PK_education_class_memberships PRIMARY KEY, "
        "organization_id uniqueidentifier NOT NULL, "
        "class_id uniqueidentifier NOT NULL, "
        "student_id uniqueidentifier NOT NULL, "
        "joined_at datetime2 NOT NULL CONSTRAINT DF_education_memberships_joined_at DEFAULT SYSUTCDATETIME(), "
        "left_at datetime2 NULL, "
        "created_at datetime2 NOT NULL CONSTRAINT DF_education_memberships_created_at DEFAULT SYSUTCDATETIME(), "
        "updated_at datetime2 NOT NULL CONSTRAINT DF_education_memberships_updated_at DEFAULT SYSUTCDATETIME(), "
        "CONSTRAINT CK_education_class_memberships_dates CHECK (left_at IS NULL OR joined_at <= left_at), "
        "CONSTRAINT UQ_education_memberships_org_mem UNIQUE (organization_id, membership_id), "
        "CONSTRAINT UQ_education_memberships_unique UNIQUE (organization_id, class_id, student_id), "
        "CONSTRAINT FK_education_memberships_organization FOREIGN KEY (organization_id) REFERENCES core.organizations (organization_id), "
        "CONSTRAINT FK_education_memberships_class FOREIGN KEY (organization_id, class_id) REFERENCES education.classes (organization_id, class_id), "
        "CONSTRAINT FK_education_memberships_student FOREIGN KEY (organization_id, student_id) REFERENCES education.students (organization_id, student_id))"
    )
    _add_tenant_predicates("education.class_memberships")

    # 8. borrower_policies
    op.execute(
        "CREATE TABLE education.borrower_policies ("
        "policy_id uniqueidentifier NOT NULL "
        "CONSTRAINT PK_education_borrower_policies PRIMARY KEY, "
        "organization_id uniqueidentifier NOT NULL, "
        "borrower_type varchar(32) NOT NULL, "
        "max_active_loans int NOT NULL, "
        "duration_days int NOT NULL, "
        "status varchar(32) NOT NULL CONSTRAINT DF_education_policies_status DEFAULT 'active', "
        "created_at datetime2 NOT NULL CONSTRAINT DF_education_policies_created_at DEFAULT SYSUTCDATETIME(), "
        "updated_at datetime2 NOT NULL CONSTRAINT DF_education_policies_updated_at DEFAULT SYSUTCDATETIME(), "
        "CONSTRAINT UQ_education_policies_org_policy UNIQUE (organization_id, policy_id), "
        "CONSTRAINT UQ_education_policies_type UNIQUE (organization_id, borrower_type), "
        "CONSTRAINT FK_education_policies_organization FOREIGN KEY (organization_id) REFERENCES core.organizations (organization_id))"
    )
    _add_tenant_predicates("education.borrower_policies")


def downgrade() -> None:
    """Detach RLS predicates and drop education tables in reverse dependency order."""
    for table_name in reversed(_TABLES):
        _drop_tenant_predicates(table_name)
        op.execute(f"DROP TABLE {table_name}")
