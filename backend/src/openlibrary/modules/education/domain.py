"""Education domain entities, value objects and exceptions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID


class EducationError(Exception):
    """Base exception for education domain failures."""


class InvalidSemesterDates(EducationError):
    """Raised when semester starts_on is not strictly before ends_on."""


class InvalidMembershipDates(EducationError):
    """Raised when class membership left_at is before joined_at."""


class DuplicateIdentifierError(EducationError):
    """Raised when an identifier (code, student number, employee number) already exists in the organization."""


class ProfileAlreadyExistsError(EducationError):
    """Raised when a user already has an active student or teacher profile in the organization."""


class EducationEntityNotFound(EducationError):
    """Raised when a requested education resource is not found in the tenant."""


class EditionUnavailableError(EducationError):
    """Raised when the education edition is not enabled for the tenant organization."""


@dataclass(frozen=True, slots=True)
class Department:
    """An academic department within an educational organization."""

    department_id: UUID
    organization_id: UUID
    code: str
    name: str
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Semester:
    """An academic term with validated start and end dates."""

    semester_id: UUID
    organization_id: UUID
    name: str
    starts_on: date
    ends_on: date
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Course:
    """A course of study optionally belonging to a department."""

    course_id: UUID
    organization_id: UUID
    code: str
    name: str
    department_id: UUID | None
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Class:
    """A specific offering of a course in a given semester."""

    class_id: UUID
    organization_id: UUID
    code: str
    name: str
    department_id: UUID | None
    semester_id: UUID
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Student:
    """A student borrower profile tied to a core user."""

    student_id: UUID
    organization_id: UUID
    user_id: UUID
    student_number: str
    department_id: UUID | None
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Teacher:
    """A teacher/faculty borrower profile tied to a core user."""

    teacher_id: UUID
    organization_id: UUID
    user_id: UUID
    employee_number: str
    department_id: UUID | None
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ClassMembership:
    """An enrollment record associating a student with a class."""

    membership_id: UUID
    organization_id: UUID
    class_id: UUID
    student_id: UUID
    joined_at: datetime
    left_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class BorrowerPolicy:
    """Configured borrowing terms for student or teacher borrower types."""

    policy_id: UUID
    organization_id: UUID
    borrower_type: str
    max_active_loans: int
    duration_days: int
    status: str
    created_at: datetime
    updated_at: datetime
