"""Application service and ports for education management."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timezone
from typing import Protocol
from uuid import UUID, uuid4

from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.authorization import AuthorizationPort
from openlibrary.modules.education.domain import (
    BorrowerPolicy,
    Department,
    Semester,
    Course,
    Class,
    Student,
    Teacher,
    ClassMembership,
    InvalidSemesterDates,
    InvalidMembershipDates,
    EditionUnavailableError,
    EducationEntityNotFound,
)

DEFAULT_STUDENT_MAX_ACTIVE_LOANS: int = 5
DEFAULT_STUDENT_DURATION_DAYS: int = 14
DEFAULT_TEACHER_MAX_ACTIVE_LOANS: int = 20
DEFAULT_TEACHER_DURATION_DAYS: int = 90


class EducationStore(Protocol):
    """Persistence port for education records."""

    def is_edition_enabled(self, organization_id: UUID) -> bool: ...

    def create_department(self, department: Department) -> Department: ...

    def get_department(
        self, organization_id: UUID, department_id: UUID
    ) -> Department | None: ...

    def list_departments(self, organization_id: UUID) -> list[Department]: ...

    def create_semester(self, semester: Semester) -> Semester: ...

    def get_semester(
        self, organization_id: UUID, semester_id: UUID
    ) -> Semester | None: ...

    def list_semesters(self, organization_id: UUID) -> list[Semester]: ...

    def create_course(self, course: Course) -> Course: ...

    def get_course(self, organization_id: UUID, course_id: UUID) -> Course | None: ...

    def list_courses(self, organization_id: UUID) -> list[Course]: ...

    def create_class(self, cls: Class) -> Class: ...

    def get_class(self, organization_id: UUID, class_id: UUID) -> Class | None: ...

    def list_classes(self, organization_id: UUID) -> list[Class]: ...

    def create_student(self, student: Student) -> Student: ...

    def get_student(
        self, organization_id: UUID, student_id: UUID
    ) -> Student | None: ...

    def get_student_by_user_id(
        self, organization_id: UUID, user_id: UUID
    ) -> Student | None: ...

    def list_students(self, organization_id: UUID) -> list[Student]: ...

    def create_teacher(self, teacher: Teacher) -> Teacher: ...

    def get_teacher(
        self, organization_id: UUID, teacher_id: UUID
    ) -> Teacher | None: ...

    def get_teacher_by_user_id(
        self, organization_id: UUID, user_id: UUID
    ) -> Teacher | None: ...

    def list_teachers(self, organization_id: UUID) -> list[Teacher]: ...

    def create_class_membership(
        self, membership: ClassMembership
    ) -> ClassMembership: ...

    def list_class_memberships(
        self, organization_id: UUID, class_id: UUID
    ) -> list[ClassMembership]: ...

    def get_borrower_policy(
        self, organization_id: UUID, borrower_type: str
    ) -> BorrowerPolicy | None: ...

    def list_borrower_policies(self, organization_id: UUID) -> list[BorrowerPolicy]: ...

    def upsert_borrower_policy(self, policy: BorrowerPolicy) -> BorrowerPolicy: ...


def _system_now() -> datetime:
    return datetime.now(timezone.utc)


class EducationService:
    """Application use cases for managing education-domain entities."""

    def __init__(
        self,
        store: EducationStore,
        authorizer: AuthorizationPort,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._authorizer = authorizer
        self._clock = clock or _system_now

    def _ensure_edition_enabled(self, organization_id: UUID) -> None:
        if not self._store.is_edition_enabled(organization_id):
            raise EditionUnavailableError(
                f"Education edition is not enabled for organization {organization_id}"
            )

    # --- Departments ---

    def list_departments(self, *, actor: Principal) -> list[Department]:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "education.read")
        return self._store.list_departments(actor.organization_id)

    def get_department(self, *, actor: Principal, department_id: UUID) -> Department:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "education.read")
        department = self._store.get_department(actor.organization_id, department_id)
        if department is None:
            raise EducationEntityNotFound(f"Department {department_id} not found")
        return department

    def create_department(
        self,
        *,
        actor: Principal,
        code: str,
        name: str,
        status: str = "active",
    ) -> Department:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "education.manage")
        clean_code = code.strip()
        clean_name = name.strip()
        if not clean_code or len(clean_code) > 64:
            raise ValueError("Department code must be 1 to 64 characters")
        if not clean_name or len(clean_name) > 255:
            raise ValueError("Department name must be 1 to 255 characters")
        now = self._clock()
        department = Department(
            department_id=uuid4(),
            organization_id=actor.organization_id,
            code=clean_code,
            name=clean_name,
            status=status.strip() or "active",
            created_at=now,
            updated_at=now,
        )
        return self._store.create_department(department)

    # --- Semesters ---

    def list_semesters(self, *, actor: Principal) -> list[Semester]:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "education.read")
        return self._store.list_semesters(actor.organization_id)

    def get_semester(self, *, actor: Principal, semester_id: UUID) -> Semester:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "education.read")
        semester = self._store.get_semester(actor.organization_id, semester_id)
        if semester is None:
            raise EducationEntityNotFound(f"Semester {semester_id} not found")
        return semester

    def create_semester(
        self,
        *,
        actor: Principal,
        name: str,
        starts_on: date,
        ends_on: date,
        status: str = "active",
    ) -> Semester:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "education.manage")
        clean_name = name.strip()
        if not clean_name or len(clean_name) > 255:
            raise ValueError("Semester name must be 1 to 255 characters")
        if starts_on >= ends_on:
            raise InvalidSemesterDates("Semester starts_on must be before ends_on")
        now = self._clock()
        semester = Semester(
            semester_id=uuid4(),
            organization_id=actor.organization_id,
            name=clean_name,
            starts_on=starts_on,
            ends_on=ends_on,
            status=status.strip() or "active",
            created_at=now,
            updated_at=now,
        )
        return self._store.create_semester(semester)

    # --- Courses ---

    def list_courses(self, *, actor: Principal) -> list[Course]:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "education.read")
        return self._store.list_courses(actor.organization_id)

    def get_course(self, *, actor: Principal, course_id: UUID) -> Course:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "education.read")
        course = self._store.get_course(actor.organization_id, course_id)
        if course is None:
            raise EducationEntityNotFound(f"Course {course_id} not found")
        return course

    def create_course(
        self,
        *,
        actor: Principal,
        code: str,
        name: str,
        department_id: UUID | None = None,
        status: str = "active",
    ) -> Course:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "education.manage")
        clean_code = code.strip()
        clean_name = name.strip()
        if not clean_code or len(clean_code) > 64:
            raise ValueError("Course code must be 1 to 64 characters")
        if not clean_name or len(clean_name) > 255:
            raise ValueError("Course name must be 1 to 255 characters")
        now = self._clock()
        course = Course(
            course_id=uuid4(),
            organization_id=actor.organization_id,
            code=clean_code,
            name=clean_name,
            department_id=department_id,
            status=status.strip() or "active",
            created_at=now,
            updated_at=now,
        )
        return self._store.create_course(course)

    # --- Classes ---

    def list_classes(self, *, actor: Principal) -> list[Class]:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "education.read")
        return self._store.list_classes(actor.organization_id)

    def get_class(self, *, actor: Principal, class_id: UUID) -> Class:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "education.read")
        cls = self._store.get_class(actor.organization_id, class_id)
        if cls is None:
            raise EducationEntityNotFound(f"Class {class_id} not found")
        return cls

    def create_class(
        self,
        *,
        actor: Principal,
        code: str,
        name: str,
        semester_id: UUID,
        department_id: UUID | None = None,
        status: str = "active",
    ) -> Class:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "education.manage")
        clean_code = code.strip()
        clean_name = name.strip()
        if not clean_code or len(clean_code) > 64:
            raise ValueError("Class code must be 1 to 64 characters")
        if not clean_name or len(clean_name) > 255:
            raise ValueError("Class name must be 1 to 255 characters")
        now = self._clock()
        cls = Class(
            class_id=uuid4(),
            organization_id=actor.organization_id,
            code=clean_code,
            name=clean_name,
            department_id=department_id,
            semester_id=semester_id,
            status=status.strip() or "active",
            created_at=now,
            updated_at=now,
        )
        return self._store.create_class(cls)

    # --- Students ---

    def list_students(self, *, actor: Principal) -> list[Student]:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "education.read")
        return self._store.list_students(actor.organization_id)

    def get_student(self, *, actor: Principal, student_id: UUID) -> Student:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "education.read")
        student = self._store.get_student(actor.organization_id, student_id)
        if student is None:
            raise EducationEntityNotFound(f"Student {student_id} not found")
        return student

    def create_student(
        self,
        *,
        actor: Principal,
        user_id: UUID,
        student_number: str,
        department_id: UUID | None = None,
        status: str = "active",
    ) -> Student:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "education.manage")
        clean_number = student_number.strip()
        if not clean_number or len(clean_number) > 64:
            raise ValueError("Student number must be 1 to 64 characters")
        now = self._clock()
        student = Student(
            student_id=uuid4(),
            organization_id=actor.organization_id,
            user_id=user_id,
            student_number=clean_number,
            department_id=department_id,
            status=status.strip() or "active",
            created_at=now,
            updated_at=now,
        )
        return self._store.create_student(student)

    # --- Teachers ---

    def list_teachers(self, *, actor: Principal) -> list[Teacher]:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "education.read")
        return self._store.list_teachers(actor.organization_id)

    def get_teacher(self, *, actor: Principal, teacher_id: UUID) -> Teacher:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "education.read")
        teacher = self._store.get_teacher(actor.organization_id, teacher_id)
        if teacher is None:
            raise EducationEntityNotFound(f"Teacher {teacher_id} not found")
        return teacher

    def create_teacher(
        self,
        *,
        actor: Principal,
        user_id: UUID,
        employee_number: str,
        department_id: UUID | None = None,
        status: str = "active",
    ) -> Teacher:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "education.manage")
        clean_number = employee_number.strip()
        if not clean_number or len(clean_number) > 64:
            raise ValueError("Employee number must be 1 to 64 characters")
        now = self._clock()
        teacher = Teacher(
            teacher_id=uuid4(),
            organization_id=actor.organization_id,
            user_id=user_id,
            employee_number=clean_number,
            department_id=department_id,
            status=status.strip() or "active",
            created_at=now,
            updated_at=now,
        )
        return self._store.create_teacher(teacher)

    # --- Class Memberships ---

    def list_class_memberships(
        self, *, actor: Principal, class_id: UUID
    ) -> list[ClassMembership]:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "education.read")
        return self._store.list_class_memberships(actor.organization_id, class_id)

    def create_class_membership(
        self,
        *,
        actor: Principal,
        class_id: UUID,
        student_id: UUID,
        joined_at: datetime | None = None,
        left_at: datetime | None = None,
    ) -> ClassMembership:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "education.manage")
        now = self._clock()
        effective_joined = joined_at or now
        if left_at is not None and left_at < effective_joined:
            raise InvalidMembershipDates(
                "Membership left_at must be at or after joined_at"
            )
        membership = ClassMembership(
            membership_id=uuid4(),
            organization_id=actor.organization_id,
            class_id=class_id,
            student_id=student_id,
            joined_at=effective_joined,
            left_at=left_at,
            created_at=now,
            updated_at=now,
        )
        return self._store.create_class_membership(membership)

    # --- Borrower Policies ---

    def list_borrower_policies(self, *, actor: Principal) -> list[BorrowerPolicy]:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "education.read")
        return self._store.list_borrower_policies(actor.organization_id)

    def get_borrower_policy(
        self, *, actor: Principal, borrower_type: str
    ) -> BorrowerPolicy | None:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "education.read")
        clean_type = borrower_type.strip().lower()
        return self._store.get_borrower_policy(actor.organization_id, clean_type)

    def set_borrower_policy(
        self,
        *,
        actor: Principal,
        borrower_type: str,
        max_active_loans: int,
        duration_days: int,
        status: str = "active",
    ) -> BorrowerPolicy:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "education.manage")
        clean_type = borrower_type.strip().lower()
        if clean_type not in ("student", "teacher"):
            raise ValueError(
                f"Invalid borrower_type '{borrower_type}'; must be 'student' or 'teacher'"
            )
        if max_active_loans <= 0:
            raise ValueError("max_active_loans must be greater than 0")
        if duration_days <= 0:
            raise ValueError("duration_days must be greater than 0")

        now = self._clock()
        existing = self._store.get_borrower_policy(actor.organization_id, clean_type)
        policy_id = existing.policy_id if existing is not None else uuid4()
        created_at = existing.created_at if existing is not None else now

        policy = BorrowerPolicy(
            policy_id=policy_id,
            organization_id=actor.organization_id,
            borrower_type=clean_type,
            max_active_loans=max_active_loans,
            duration_days=duration_days,
            status=status.strip() or "active",
            created_at=created_at,
            updated_at=now,
        )
        return self._store.upsert_borrower_policy(policy)
