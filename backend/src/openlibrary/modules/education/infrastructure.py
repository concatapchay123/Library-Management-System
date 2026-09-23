"""SQL Server persistence for education records."""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import date, datetime
import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping
from sqlalchemy.exc import IntegrityError

from openlibrary.modules.core.infrastructure.tenancy import SqlServerTenantContext
from openlibrary.modules.education.application import EducationStore
from openlibrary.modules.education.domain import (
    BorrowerPolicy,
    Department,
    Semester,
    Course,
    Class,
    Student,
    Teacher,
    ClassMembership,
    DuplicateIdentifierError,
    ProfileAlreadyExistsError,
    InvalidSemesterDates,
    InvalidMembershipDates,
)


class SqlServerEducationStore(EducationStore):
    """Execute parameterized SQL Server queries for education entities under tenant context."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._tenant_context: SqlServerTenantContext | None = None

    def _tenant_connection(
        self, organization_id: UUID
    ) -> AbstractContextManager[Connection]:
        if self._tenant_context is None:
            self._tenant_context = SqlServerTenantContext(self._database_url)
        return self._tenant_context.connection(organization_id)

    def is_edition_enabled(self, organization_id: UUID) -> bool:
        """Check whether the education edition is active for the organization."""
        with self._tenant_connection(organization_id) as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT organization_type, settings_json "
                        "FROM core.organizations "
                        "WHERE organization_id = :org_id"
                    ),
                    {"org_id": str(organization_id)},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return False
        org_type = str(row["organization_type"]).strip().lower()
        if org_type == "education":
            return True
        try:
            settings = json.loads(str(row["settings_json"]))
            if not isinstance(settings, dict):
                return False
            if settings.get("education_enabled") is True:
                return True
            editions = settings.get("editions")
            if isinstance(editions, dict) and editions.get("education") is True:
                return True
            if isinstance(editions, list) and "education" in editions:
                return True
            enabled_editions = settings.get("enabled_editions")
            if isinstance(enabled_editions, list) and "education" in enabled_editions:
                return True
        except (ValueError, TypeError):
            return False
        return False

    # --- Departments ---

    def create_department(self, department: Department) -> Department:
        with self._tenant_connection(department.organization_id) as connection:
            try:
                connection.execute(
                    text(
                        "INSERT INTO education.departments ("
                        "department_id, organization_id, code, name, status, created_at, updated_at"
                        ") VALUES ("
                        ":department_id, :organization_id, :code, :name, :status, :created_at, :updated_at"
                        ")"
                    ),
                    {
                        "department_id": str(department.department_id),
                        "organization_id": str(department.organization_id),
                        "code": department.code,
                        "name": department.name,
                        "status": department.status,
                        "created_at": department.created_at,
                        "updated_at": department.updated_at,
                    },
                )
            except IntegrityError as err:
                msg = str(err).lower()
                if "uq_education_departments_org_code" in msg or "duplicate" in msg:
                    raise DuplicateIdentifierError(
                        f"Department code '{department.code}' already exists"
                    ) from err
                raise
        return department

    def get_department(
        self, organization_id: UUID, department_id: UUID
    ) -> Department | None:
        with self._tenant_connection(organization_id) as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT department_id, organization_id, code, name, status, created_at, updated_at "
                        "FROM education.departments "
                        "WHERE organization_id = :org_id AND department_id = :dept_id"
                    ),
                    {"org_id": str(organization_id), "dept_id": str(department_id)},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return _department_from_row(row)

    def list_departments(self, organization_id: UUID) -> list[Department]:
        with self._tenant_connection(organization_id) as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT department_id, organization_id, code, name, status, created_at, updated_at "
                        "FROM education.departments "
                        "WHERE organization_id = :org_id "
                        "ORDER BY code"
                    ),
                    {"org_id": str(organization_id)},
                )
                .mappings()
                .all()
            )
        return [_department_from_row(r) for r in rows]

    # --- Semesters ---

    def create_semester(self, semester: Semester) -> Semester:
        with self._tenant_connection(semester.organization_id) as connection:
            try:
                connection.execute(
                    text(
                        "INSERT INTO education.semesters ("
                        "semester_id, organization_id, name, starts_on, ends_on, status, created_at, updated_at"
                        ") VALUES ("
                        ":semester_id, :organization_id, :name, :starts_on, :ends_on, :status, :created_at, :updated_at"
                        ")"
                    ),
                    {
                        "semester_id": str(semester.semester_id),
                        "organization_id": str(semester.organization_id),
                        "name": semester.name,
                        "starts_on": semester.starts_on,
                        "ends_on": semester.ends_on,
                        "status": semester.status,
                        "created_at": semester.created_at,
                        "updated_at": semester.updated_at,
                    },
                )
            except IntegrityError as err:
                msg = str(err).lower()
                if "ck_education_semesters_dates" in msg:
                    raise InvalidSemesterDates(
                        "Semester starts_on must be before ends_on"
                    ) from err
                if "uq_education_semesters_org_name" in msg or "duplicate" in msg:
                    raise DuplicateIdentifierError(
                        f"Semester name '{semester.name}' already exists"
                    ) from err
                raise
        return semester

    def get_semester(self, organization_id: UUID, semester_id: UUID) -> Semester | None:
        with self._tenant_connection(organization_id) as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT semester_id, organization_id, name, starts_on, ends_on, status, created_at, updated_at "
                        "FROM education.semesters "
                        "WHERE organization_id = :org_id AND semester_id = :sem_id"
                    ),
                    {"org_id": str(organization_id), "sem_id": str(semester_id)},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return _semester_from_row(row)

    def list_semesters(self, organization_id: UUID) -> list[Semester]:
        with self._tenant_connection(organization_id) as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT semester_id, organization_id, name, starts_on, ends_on, status, created_at, updated_at "
                        "FROM education.semesters "
                        "WHERE organization_id = :org_id "
                        "ORDER BY starts_on DESC"
                    ),
                    {"org_id": str(organization_id)},
                )
                .mappings()
                .all()
            )
        return [_semester_from_row(r) for r in rows]

    # --- Courses ---

    def create_course(self, course: Course) -> Course:
        with self._tenant_connection(course.organization_id) as connection:
            try:
                connection.execute(
                    text(
                        "INSERT INTO education.courses ("
                        "course_id, organization_id, code, name, department_id, status, created_at, updated_at"
                        ") VALUES ("
                        ":course_id, :organization_id, :code, :name, :department_id, :status, :created_at, :updated_at"
                        ")"
                    ),
                    {
                        "course_id": str(course.course_id),
                        "organization_id": str(course.organization_id),
                        "code": course.code,
                        "name": course.name,
                        "department_id": str(course.department_id)
                        if course.department_id
                        else None,
                        "status": course.status,
                        "created_at": course.created_at,
                        "updated_at": course.updated_at,
                    },
                )
            except IntegrityError as err:
                msg = str(err).lower()
                if "uq_education_courses_org_code" in msg or "duplicate" in msg:
                    raise DuplicateIdentifierError(
                        f"Course code '{course.code}' already exists"
                    ) from err
                raise
        return course

    def get_course(self, organization_id: UUID, course_id: UUID) -> Course | None:
        with self._tenant_connection(organization_id) as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT course_id, organization_id, code, name, department_id, status, created_at, updated_at "
                        "FROM education.courses "
                        "WHERE organization_id = :org_id AND course_id = :course_id"
                    ),
                    {"org_id": str(organization_id), "course_id": str(course_id)},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return _course_from_row(row)

    def list_courses(self, organization_id: UUID) -> list[Course]:
        with self._tenant_connection(organization_id) as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT course_id, organization_id, code, name, department_id, status, created_at, updated_at "
                        "FROM education.courses "
                        "WHERE organization_id = :org_id "
                        "ORDER BY code"
                    ),
                    {"org_id": str(organization_id)},
                )
                .mappings()
                .all()
            )
        return [_course_from_row(r) for r in rows]

    # --- Classes ---

    def create_class(self, cls: Class) -> Class:
        with self._tenant_connection(cls.organization_id) as connection:
            try:
                connection.execute(
                    text(
                        "INSERT INTO education.classes ("
                        "class_id, organization_id, code, name, department_id, semester_id, status, created_at, updated_at"
                        ") VALUES ("
                        ":class_id, :organization_id, :code, :name, :department_id, :semester_id, :status, :created_at, :updated_at"
                        ")"
                    ),
                    {
                        "class_id": str(cls.class_id),
                        "organization_id": str(cls.organization_id),
                        "code": cls.code,
                        "name": cls.name,
                        "department_id": str(cls.department_id)
                        if cls.department_id
                        else None,
                        "semester_id": str(cls.semester_id),
                        "status": cls.status,
                        "created_at": cls.created_at,
                        "updated_at": cls.updated_at,
                    },
                )
            except IntegrityError as err:
                msg = str(err).lower()
                if "uq_education_classes_org_code" in msg or "duplicate" in msg:
                    raise DuplicateIdentifierError(
                        f"Class code '{cls.code}' already exists"
                    ) from err
                raise
        return cls

    def get_class(self, organization_id: UUID, class_id: UUID) -> Class | None:
        with self._tenant_connection(organization_id) as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT class_id, organization_id, code, name, department_id, semester_id, status, created_at, updated_at "
                        "FROM education.classes "
                        "WHERE organization_id = :org_id AND class_id = :class_id"
                    ),
                    {"org_id": str(organization_id), "class_id": str(class_id)},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return _class_from_row(row)

    def list_classes(self, organization_id: UUID) -> list[Class]:
        with self._tenant_connection(organization_id) as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT class_id, organization_id, code, name, department_id, semester_id, status, created_at, updated_at "
                        "FROM education.classes "
                        "WHERE organization_id = :org_id "
                        "ORDER BY code"
                    ),
                    {"org_id": str(organization_id)},
                )
                .mappings()
                .all()
            )
        return [_class_from_row(r) for r in rows]

    # --- Students ---

    def create_student(self, student: Student) -> Student:
        with self._tenant_connection(student.organization_id) as connection:
            try:
                connection.execute(
                    text(
                        "INSERT INTO education.students ("
                        "student_id, organization_id, user_id, student_number, department_id, status, created_at, updated_at"
                        ") VALUES ("
                        ":student_id, :organization_id, :user_id, :student_number, :department_id, :status, :created_at, :updated_at"
                        ")"
                    ),
                    {
                        "student_id": str(student.student_id),
                        "organization_id": str(student.organization_id),
                        "user_id": str(student.user_id),
                        "student_number": student.student_number,
                        "department_id": str(student.department_id)
                        if student.department_id
                        else None,
                        "status": student.status,
                        "created_at": student.created_at,
                        "updated_at": student.updated_at,
                    },
                )
            except IntegrityError as err:
                msg = str(err).lower()
                if "uq_education_students_org_number" in msg:
                    raise DuplicateIdentifierError(
                        f"Student number '{student.student_number}' already exists"
                    ) from err
                if "uq_education_students_org_user" in msg:
                    raise ProfileAlreadyExistsError(
                        f"Student profile already exists for user {student.user_id}"
                    ) from err
                raise
        return student

    def get_student(self, organization_id: UUID, student_id: UUID) -> Student | None:
        with self._tenant_connection(organization_id) as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT student_id, organization_id, user_id, student_number, department_id, status, created_at, updated_at "
                        "FROM education.students "
                        "WHERE organization_id = :org_id AND student_id = :student_id"
                    ),
                    {"org_id": str(organization_id), "student_id": str(student_id)},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return _student_from_row(row)

    def list_students(self, organization_id: UUID) -> list[Student]:
        with self._tenant_connection(organization_id) as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT student_id, organization_id, user_id, student_number, department_id, status, created_at, updated_at "
                        "FROM education.students "
                        "WHERE organization_id = :org_id "
                        "ORDER BY student_number"
                    ),
                    {"org_id": str(organization_id)},
                )
                .mappings()
                .all()
            )
        return [_student_from_row(r) for r in rows]

    # --- Teachers ---

    def create_teacher(self, teacher: Teacher) -> Teacher:
        with self._tenant_connection(teacher.organization_id) as connection:
            try:
                connection.execute(
                    text(
                        "INSERT INTO education.teachers ("
                        "teacher_id, organization_id, user_id, employee_number, department_id, status, created_at, updated_at"
                        ") VALUES ("
                        ":teacher_id, :organization_id, :user_id, :employee_number, :department_id, :status, :created_at, :updated_at"
                        ")"
                    ),
                    {
                        "teacher_id": str(teacher.teacher_id),
                        "organization_id": str(teacher.organization_id),
                        "user_id": str(teacher.user_id),
                        "employee_number": teacher.employee_number,
                        "department_id": str(teacher.department_id)
                        if teacher.department_id
                        else None,
                        "status": teacher.status,
                        "created_at": teacher.created_at,
                        "updated_at": teacher.updated_at,
                    },
                )
            except IntegrityError as err:
                msg = str(err).lower()
                if "uq_education_teachers_org_number" in msg:
                    raise DuplicateIdentifierError(
                        f"Teacher employee number '{teacher.employee_number}' already exists"
                    ) from err
                if "uq_education_teachers_org_user" in msg:
                    raise ProfileAlreadyExistsError(
                        f"Teacher profile already exists for user {teacher.user_id}"
                    ) from err
                raise
        return teacher

    def get_teacher(self, organization_id: UUID, teacher_id: UUID) -> Teacher | None:
        with self._tenant_connection(organization_id) as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT teacher_id, organization_id, user_id, employee_number, department_id, status, created_at, updated_at "
                        "FROM education.teachers "
                        "WHERE organization_id = :org_id AND teacher_id = :teacher_id"
                    ),
                    {"org_id": str(organization_id), "teacher_id": str(teacher_id)},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return _teacher_from_row(row)

    def list_teachers(self, organization_id: UUID) -> list[Teacher]:
        with self._tenant_connection(organization_id) as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT teacher_id, organization_id, user_id, employee_number, department_id, status, created_at, updated_at "
                        "FROM education.teachers "
                        "WHERE organization_id = :org_id "
                        "ORDER BY employee_number"
                    ),
                    {"org_id": str(organization_id)},
                )
                .mappings()
                .all()
            )
        return [_teacher_from_row(r) for r in rows]

    # --- Class Memberships ---

    def create_class_membership(self, membership: ClassMembership) -> ClassMembership:
        with self._tenant_connection(membership.organization_id) as connection:
            try:
                connection.execute(
                    text(
                        "INSERT INTO education.class_memberships ("
                        "membership_id, organization_id, class_id, student_id, joined_at, left_at, created_at, updated_at"
                        ") VALUES ("
                        ":membership_id, :organization_id, :class_id, :student_id, :joined_at, :left_at, :created_at, :updated_at"
                        ")"
                    ),
                    {
                        "membership_id": str(membership.membership_id),
                        "organization_id": str(membership.organization_id),
                        "class_id": str(membership.class_id),
                        "student_id": str(membership.student_id),
                        "joined_at": membership.joined_at,
                        "left_at": membership.left_at,
                        "created_at": membership.created_at,
                        "updated_at": membership.updated_at,
                    },
                )
            except IntegrityError as err:
                msg = str(err).lower()
                if "ck_education_class_memberships_dates" in msg:
                    raise InvalidMembershipDates(
                        "Membership left_at must be at or after joined_at"
                    ) from err
                if "uq_education_memberships_unique" in msg or "duplicate" in msg:
                    raise DuplicateIdentifierError(
                        "Student is already enrolled in this class"
                    ) from err
                raise
        return membership

    def list_class_memberships(
        self, organization_id: UUID, class_id: UUID
    ) -> list[ClassMembership]:
        with self._tenant_connection(organization_id) as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT membership_id, organization_id, class_id, student_id, joined_at, left_at, created_at, updated_at "
                        "FROM education.class_memberships "
                        "WHERE organization_id = :org_id AND class_id = :class_id "
                        "ORDER BY joined_at"
                    ),
                    {"org_id": str(organization_id), "class_id": str(class_id)},
                )
                .mappings()
                .all()
            )
        return [_membership_from_row(r) for r in rows]

    def get_student_by_user_id(
        self, organization_id: UUID, user_id: UUID
    ) -> Student | None:
        with self._tenant_connection(organization_id) as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT student_id, organization_id, user_id, student_number, department_id, status, created_at, updated_at "
                        "FROM education.students "
                        "WHERE organization_id = :org_id AND user_id = :user_id"
                    ),
                    {"org_id": str(organization_id), "user_id": str(user_id)},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return _student_from_row(row)

    def get_teacher_by_user_id(
        self, organization_id: UUID, user_id: UUID
    ) -> Teacher | None:
        with self._tenant_connection(organization_id) as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT teacher_id, organization_id, user_id, employee_number, department_id, status, created_at, updated_at "
                        "FROM education.teachers "
                        "WHERE organization_id = :org_id AND user_id = :user_id"
                    ),
                    {"org_id": str(organization_id), "user_id": str(user_id)},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return _teacher_from_row(row)

    # --- Borrower Policies ---

    def get_borrower_policy(
        self, organization_id: UUID, borrower_type: str
    ) -> BorrowerPolicy | None:
        with self._tenant_connection(organization_id) as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT policy_id, organization_id, borrower_type, max_active_loans, duration_days, status, created_at, updated_at "
                        "FROM education.borrower_policies "
                        "WHERE organization_id = :org_id AND borrower_type = :borrower_type"
                    ),
                    {
                        "org_id": str(organization_id),
                        "borrower_type": borrower_type.strip().lower(),
                    },
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return _borrower_policy_from_row(row)

    def list_borrower_policies(self, organization_id: UUID) -> list[BorrowerPolicy]:
        with self._tenant_connection(organization_id) as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT policy_id, organization_id, borrower_type, max_active_loans, duration_days, status, created_at, updated_at "
                        "FROM education.borrower_policies "
                        "WHERE organization_id = :org_id "
                        "ORDER BY borrower_type"
                    ),
                    {"org_id": str(organization_id)},
                )
                .mappings()
                .all()
            )
        return [_borrower_policy_from_row(r) for r in rows]

    def upsert_borrower_policy(self, policy: BorrowerPolicy) -> BorrowerPolicy:
        with self._tenant_connection(policy.organization_id) as connection:
            connection.execute(
                text(
                    "MERGE education.borrower_policies AS target "
                    "USING (SELECT :policy_id AS policy_id, :org_id AS organization_id, "
                    ":borrower_type AS borrower_type, :max_active_loans AS max_active_loans, "
                    ":duration_days AS duration_days, :status AS status, "
                    ":created_at AS created_at, :updated_at AS updated_at) AS src "
                    "ON target.organization_id = src.organization_id "
                    "AND target.borrower_type = src.borrower_type "
                    "WHEN MATCHED THEN "
                    "  UPDATE SET max_active_loans = src.max_active_loans, "
                    "             duration_days = src.duration_days, "
                    "             status = src.status, "
                    "             updated_at = src.updated_at "
                    "WHEN NOT MATCHED THEN "
                    "  INSERT (policy_id, organization_id, borrower_type, max_active_loans, "
                    "          duration_days, status, created_at, updated_at) "
                    "  VALUES (src.policy_id, src.organization_id, src.borrower_type, "
                    "          src.max_active_loans, src.duration_days, src.status, "
                    "          src.created_at, src.updated_at);"
                ),
                {
                    "policy_id": str(policy.policy_id),
                    "org_id": str(policy.organization_id),
                    "borrower_type": policy.borrower_type.strip().lower(),
                    "max_active_loans": policy.max_active_loans,
                    "duration_days": policy.duration_days,
                    "status": policy.status,
                    "created_at": policy.created_at,
                    "updated_at": policy.updated_at,
                },
            )
        return policy


def _borrower_policy_from_row(row: RowMapping) -> BorrowerPolicy:
    return BorrowerPolicy(
        policy_id=UUID(str(row["policy_id"])),
        organization_id=UUID(str(row["organization_id"])),
        borrower_type=str(row["borrower_type"]),
        max_active_loans=int(row["max_active_loans"]),
        duration_days=int(row["duration_days"]),
        status=str(row["status"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _department_from_row(row: RowMapping) -> Department:
    return Department(
        department_id=UUID(str(row["department_id"])),
        organization_id=UUID(str(row["organization_id"])),
        code=str(row["code"]),
        name=str(row["name"]),
        status=str(row["status"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _semester_from_row(row: RowMapping) -> Semester:
    starts_on = row["starts_on"]
    if isinstance(starts_on, datetime):
        starts_on = starts_on.date()
    elif isinstance(starts_on, str):
        starts_on = date.fromisoformat(starts_on)

    ends_on = row["ends_on"]
    if isinstance(ends_on, datetime):
        ends_on = ends_on.date()
    elif isinstance(ends_on, str):
        ends_on = date.fromisoformat(ends_on)

    return Semester(
        semester_id=UUID(str(row["semester_id"])),
        organization_id=UUID(str(row["organization_id"])),
        name=str(row["name"]),
        starts_on=starts_on,
        ends_on=ends_on,
        status=str(row["status"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _course_from_row(row: RowMapping) -> Course:
    dept_id = row["department_id"]
    return Course(
        course_id=UUID(str(row["course_id"])),
        organization_id=UUID(str(row["organization_id"])),
        code=str(row["code"]),
        name=str(row["name"]),
        department_id=UUID(str(dept_id)) if dept_id is not None else None,
        status=str(row["status"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _class_from_row(row: RowMapping) -> Class:
    dept_id = row["department_id"]
    return Class(
        class_id=UUID(str(row["class_id"])),
        organization_id=UUID(str(row["organization_id"])),
        code=str(row["code"]),
        name=str(row["name"]),
        department_id=UUID(str(dept_id)) if dept_id is not None else None,
        semester_id=UUID(str(row["semester_id"])),
        status=str(row["status"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _student_from_row(row: RowMapping) -> Student:
    dept_id = row["department_id"]
    return Student(
        student_id=UUID(str(row["student_id"])),
        organization_id=UUID(str(row["organization_id"])),
        user_id=UUID(str(row["user_id"])),
        student_number=str(row["student_number"]),
        department_id=UUID(str(dept_id)) if dept_id is not None else None,
        status=str(row["status"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _teacher_from_row(row: RowMapping) -> Teacher:
    dept_id = row["department_id"]
    return Teacher(
        teacher_id=UUID(str(row["teacher_id"])),
        organization_id=UUID(str(row["organization_id"])),
        user_id=UUID(str(row["user_id"])),
        employee_number=str(row["employee_number"]),
        department_id=UUID(str(dept_id)) if dept_id is not None else None,
        status=str(row["status"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _membership_from_row(row: RowMapping) -> ClassMembership:
    return ClassMembership(
        membership_id=UUID(str(row["membership_id"])),
        organization_id=UUID(str(row["organization_id"])),
        class_id=UUID(str(row["class_id"])),
        student_id=UUID(str(row["student_id"])),
        joined_at=row["joined_at"],
        left_at=row["left_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
