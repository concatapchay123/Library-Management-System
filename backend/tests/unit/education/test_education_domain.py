"""Unit tests for education domain entities and application service."""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID, uuid4

import pytest

from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.authorization import AuthorizationDenied
from openlibrary.modules.education.domain import (
    Department,
    Semester,
    Course,
    Class,
    Student,
    Teacher,
    ClassMembership,
    InvalidSemesterDates,
    InvalidMembershipDates,
    DuplicateIdentifierError,
    EditionUnavailableError,
)
from openlibrary.modules.education.application import EducationService


class _MockAuthorizer:
    def __init__(self, permissions: set[str]) -> None:
        self.permissions = permissions

    def require(self, actor: Principal, permission: str) -> None:
        if permission not in self.permissions:
            raise AuthorizationDenied(f"Missing permission: {permission}")


class _InMemoryEducationStore:
    def __init__(self, enabled_editions: dict[UUID, bool] | None = None) -> None:
        self.enabled_editions = enabled_editions or {}
        self.departments: dict[UUID, Department] = {}
        self.semesters: dict[UUID, Semester] = {}
        self.courses: dict[UUID, Course] = {}
        self.classes: dict[UUID, Class] = {}
        self.students: dict[UUID, Student] = {}
        self.teachers: dict[UUID, Teacher] = {}
        self.memberships: dict[UUID, ClassMembership] = {}

    def is_edition_enabled(self, organization_id: UUID) -> bool:
        return self.enabled_editions.get(organization_id, True)

    def create_department(self, department: Department) -> Department:
        for d in self.departments.values():
            if (
                d.organization_id == department.organization_id
                and d.code == department.code
            ):
                raise DuplicateIdentifierError(
                    f"Department code '{department.code}' already exists"
                )
        self.departments[department.department_id] = department
        return department

    def get_department(
        self, organization_id: UUID, department_id: UUID
    ) -> Department | None:
        dept = self.departments.get(department_id)
        if dept and dept.organization_id == organization_id:
            return dept
        return None

    def list_departments(self, organization_id: UUID) -> list[Department]:
        return [
            d for d in self.departments.values() if d.organization_id == organization_id
        ]

    def create_semester(self, semester: Semester) -> Semester:
        for s in self.semesters.values():
            if (
                s.organization_id == semester.organization_id
                and s.name == semester.name
            ):
                raise DuplicateIdentifierError(
                    f"Semester name '{semester.name}' already exists"
                )
        self.semesters[semester.semester_id] = semester
        return semester

    def get_semester(self, organization_id: UUID, semester_id: UUID) -> Semester | None:
        sem = self.semesters.get(semester_id)
        if sem and sem.organization_id == organization_id:
            return sem
        return None

    def list_semesters(self, organization_id: UUID) -> list[Semester]:
        return [
            s for s in self.semesters.values() if s.organization_id == organization_id
        ]

    def create_course(self, course: Course) -> Course:
        for c in self.courses.values():
            if c.organization_id == course.organization_id and c.code == course.code:
                raise DuplicateIdentifierError(
                    f"Course code '{course.code}' already exists"
                )
        self.courses[course.course_id] = course
        return course

    def get_course(self, organization_id: UUID, course_id: UUID) -> Course | None:
        c = self.courses.get(course_id)
        if c and c.organization_id == organization_id:
            return c
        return None

    def list_courses(self, organization_id: UUID) -> list[Course]:
        return [
            c for c in self.courses.values() if c.organization_id == organization_id
        ]

    def create_class(self, cls: Class) -> Class:
        for c in self.classes.values():
            if c.organization_id == cls.organization_id and c.code == cls.code:
                raise DuplicateIdentifierError(
                    f"Class code '{cls.code}' already exists"
                )
        self.classes[cls.class_id] = cls
        return cls

    def get_class(self, organization_id: UUID, class_id: UUID) -> Class | None:
        c = self.classes.get(class_id)
        if c and c.organization_id == organization_id:
            return c
        return None

    def list_classes(self, organization_id: UUID) -> list[Class]:
        return [
            c for c in self.classes.values() if c.organization_id == organization_id
        ]

    def create_student(self, student: Student) -> Student:
        for s in self.students.values():
            if s.organization_id == student.organization_id:
                if s.student_number == student.student_number:
                    raise DuplicateIdentifierError(
                        f"Student number '{student.student_number}' already exists"
                    )
                if s.user_id == student.user_id:
                    raise DuplicateIdentifierError(
                        "Student profile already exists for user"
                    )
        self.students[student.student_id] = student
        return student

    def get_student(self, organization_id: UUID, student_id: UUID) -> Student | None:
        s = self.students.get(student_id)
        if s and s.organization_id == organization_id:
            return s
        return None

    def list_students(self, organization_id: UUID) -> list[Student]:
        return [
            s for s in self.students.values() if s.organization_id == organization_id
        ]

    def create_teacher(self, teacher: Teacher) -> Teacher:
        for t in self.teachers.values():
            if t.organization_id == teacher.organization_id:
                if t.employee_number == teacher.employee_number:
                    raise DuplicateIdentifierError(
                        f"Teacher employee number '{teacher.employee_number}' already exists"
                    )
                if t.user_id == teacher.user_id:
                    raise DuplicateIdentifierError(
                        "Teacher profile already exists for user"
                    )
        self.teachers[teacher.teacher_id] = teacher
        return teacher

    def get_teacher(self, organization_id: UUID, teacher_id: UUID) -> Teacher | None:
        t = self.teachers.get(teacher_id)
        if t and t.organization_id == organization_id:
            return t
        return None

    def list_teachers(self, organization_id: UUID) -> list[Teacher]:
        return [
            t for t in self.teachers.values() if t.organization_id == organization_id
        ]

    def create_class_membership(self, membership: ClassMembership) -> ClassMembership:
        for m in self.memberships.values():
            if (
                m.organization_id == membership.organization_id
                and m.class_id == membership.class_id
                and m.student_id == membership.student_id
            ):
                raise DuplicateIdentifierError(
                    "Student is already enrolled in this class"
                )
        self.memberships[membership.membership_id] = membership
        return membership

    def list_class_memberships(
        self, organization_id: UUID, class_id: UUID
    ) -> list[ClassMembership]:
        return [
            m
            for m in self.memberships.values()
            if m.organization_id == organization_id and m.class_id == class_id
        ]


def _actor(org_id: UUID | None = None) -> Principal:
    return Principal(
        user_id=uuid4(),
        organization_id=org_id or uuid4(),
        session_id=uuid4(),
    )


def test_education_service_requires_education_read_permission() -> None:
    org_id = uuid4()
    actor = _actor(org_id)
    store = _InMemoryEducationStore()
    authorizer = _MockAuthorizer(permissions={"catalog.read"})  # missing education.read
    service = EducationService(store, authorizer)

    with pytest.raises(AuthorizationDenied):
        service.list_departments(actor=actor)


def test_education_service_requires_education_manage_permission() -> None:
    org_id = uuid4()
    actor = _actor(org_id)
    store = _InMemoryEducationStore()
    authorizer = _MockAuthorizer(
        permissions={"education.read"}
    )  # missing education.manage
    service = EducationService(store, authorizer)

    with pytest.raises(AuthorizationDenied):
        service.create_department(actor=actor, code="MATH", name="Mathematics")


def test_education_service_checks_edition_enablement() -> None:
    org_id = uuid4()
    actor = _actor(org_id)
    # Organization has education disabled
    store = _InMemoryEducationStore(enabled_editions={org_id: False})
    authorizer = _MockAuthorizer(permissions={"education.read", "education.manage"})
    service = EducationService(store, authorizer)

    with pytest.raises(EditionUnavailableError):
        service.list_departments(actor=actor)

    with pytest.raises(EditionUnavailableError):
        service.create_department(actor=actor, code="PHYS", name="Physics")


def test_create_semester_validates_date_range() -> None:
    org_id = uuid4()
    actor = _actor(org_id)
    store = _InMemoryEducationStore()
    authorizer = _MockAuthorizer(permissions={"education.read", "education.manage"})
    service = EducationService(store, authorizer)

    # starts_on >= ends_on must fail
    with pytest.raises(InvalidSemesterDates, match="must be before"):
        service.create_semester(
            actor=actor,
            name="Fall 2026",
            starts_on=date(2026, 12, 1),
            ends_on=date(2026, 9, 1),
        )

    with pytest.raises(InvalidSemesterDates, match="must be before"):
        service.create_semester(
            actor=actor,
            name="Fall 2026",
            starts_on=date(2026, 9, 1),
            ends_on=date(2026, 9, 1),
        )

    # Valid range succeeds
    sem = service.create_semester(
        actor=actor,
        name="Fall 2026",
        starts_on=date(2026, 9, 1),
        ends_on=date(2026, 12, 31),
    )
    assert sem.name == "Fall 2026"
    assert sem.organization_id == org_id


def test_create_membership_validates_dates() -> None:
    org_id = uuid4()
    actor = _actor(org_id)
    store = _InMemoryEducationStore()
    authorizer = _MockAuthorizer(permissions={"education.read", "education.manage"})
    service = EducationService(store, authorizer)

    class_id = uuid4()
    student_id = uuid4()

    # left_at < joined_at must fail
    with pytest.raises(InvalidMembershipDates):
        service.create_class_membership(
            actor=actor,
            class_id=class_id,
            student_id=student_id,
            joined_at=datetime(2026, 9, 15, tzinfo=timezone.utc),
            left_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        )


def test_student_and_teacher_creation_and_isolation() -> None:
    org_a = uuid4()
    org_b = uuid4()
    actor_a = _actor(org_a)
    actor_b = _actor(org_b)
    store = _InMemoryEducationStore()
    authorizer = _MockAuthorizer(permissions={"education.read", "education.manage"})
    service = EducationService(store, authorizer)

    user_a = uuid4()
    user_b = uuid4()

    stu_a = service.create_student(
        actor=actor_a,
        user_id=user_a,
        student_number="S-100",
        department_id=None,
    )
    assert stu_a.student_number == "S-100"
    assert stu_a.organization_id == org_a

    # Org B can use the same student_number
    stu_b = service.create_student(
        actor=actor_b,
        user_id=user_b,
        student_number="S-100",
        department_id=None,
    )
    assert stu_b.student_number == "S-100"
    assert stu_b.organization_id == org_b

    # Org A cannot reuse student_number
    with pytest.raises(DuplicateIdentifierError):
        service.create_student(
            actor=actor_a,
            user_id=uuid4(),
            student_number="S-100",
            department_id=None,
        )

    # Org A cannot create another student for the same user_a
    with pytest.raises(DuplicateIdentifierError):
        service.create_student(
            actor=actor_a,
            user_id=user_a,
            student_number="S-200",
            department_id=None,
        )
