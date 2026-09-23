"""HTTP API adapter for education endpoints."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from flask import Blueprint, Response, jsonify, request

from openlibrary.app.correlation import request_id
from openlibrary.modules.core.api.auth import (
    _principal_from_request,
    _require_principal,
)
from openlibrary.modules.core.application.access_tokens import AccessTokenService
from openlibrary.modules.core.application.authorization import AuthorizationDenied
from openlibrary.modules.core.infrastructure.tenancy import TenantRequestContext
from openlibrary.modules.education.application import EducationService
from openlibrary.modules.education.domain import (
    Department,
    Semester,
    Course,
    Class,
    Student,
    Teacher,
    ClassMembership,
    EducationEntityNotFound,
    EditionUnavailableError,
    InvalidSemesterDates,
    InvalidMembershipDates,
    DuplicateIdentifierError,
    ProfileAlreadyExistsError,
)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def _date_str(d: date | None) -> str | None:
    return d.isoformat() if d is not None else None


def _department_dict(d: Department) -> dict[str, Any]:
    return {
        "department_id": str(d.department_id),
        "organization_id": str(d.organization_id),
        "code": d.code,
        "name": d.name,
        "status": d.status,
        "created_at": _iso(d.created_at),
        "updated_at": _iso(d.updated_at),
    }


def _semester_dict(s: Semester) -> dict[str, Any]:
    return {
        "semester_id": str(s.semester_id),
        "organization_id": str(s.organization_id),
        "name": s.name,
        "starts_on": _date_str(s.starts_on),
        "ends_on": _date_str(s.ends_on),
        "status": s.status,
        "created_at": _iso(s.created_at),
        "updated_at": _iso(s.updated_at),
    }


def _course_dict(c: Course) -> dict[str, Any]:
    return {
        "course_id": str(c.course_id),
        "organization_id": str(c.organization_id),
        "code": c.code,
        "name": c.name,
        "department_id": str(c.department_id) if c.department_id else None,
        "status": c.status,
        "created_at": _iso(c.created_at),
        "updated_at": _iso(c.updated_at),
    }


def _class_dict(c: Class) -> dict[str, Any]:
    return {
        "class_id": str(c.class_id),
        "organization_id": str(c.organization_id),
        "code": c.code,
        "name": c.name,
        "department_id": str(c.department_id) if c.department_id else None,
        "semester_id": str(c.semester_id),
        "status": c.status,
        "created_at": _iso(c.created_at),
        "updated_at": _iso(c.updated_at),
    }


def _student_dict(s: Student) -> dict[str, Any]:
    return {
        "student_id": str(s.student_id),
        "organization_id": str(s.organization_id),
        "user_id": str(s.user_id),
        "student_number": s.student_number,
        "department_id": str(s.department_id) if s.department_id else None,
        "status": s.status,
        "created_at": _iso(s.created_at),
        "updated_at": _iso(s.updated_at),
    }


def _teacher_dict(t: Teacher) -> dict[str, Any]:
    return {
        "teacher_id": str(t.teacher_id),
        "organization_id": str(t.organization_id),
        "user_id": str(t.user_id),
        "employee_number": t.employee_number,
        "department_id": str(t.department_id) if t.department_id else None,
        "status": t.status,
        "created_at": _iso(t.created_at),
        "updated_at": _iso(t.updated_at),
    }


def _membership_dict(m: ClassMembership) -> dict[str, Any]:
    return {
        "membership_id": str(m.membership_id),
        "organization_id": str(m.organization_id),
        "class_id": str(m.class_id),
        "student_id": str(m.student_id),
        "joined_at": _iso(m.joined_at),
        "left_at": _iso(m.left_at),
        "created_at": _iso(m.created_at),
        "updated_at": _iso(m.updated_at),
    }


def _problem(status: int, title: str, detail: str, type_suffix: str) -> Response:
    response = jsonify(
        {
            "type": f"https://openlibraryos.example/problems/{type_suffix}",
            "title": title,
            "status": status,
            "detail": detail,
            "instance": request.path,
            "request_id": request_id(),
        }
    )
    response.status_code = status
    response.mimetype = "application/problem+json"
    return response


def _handle_education_error(err: Exception) -> Response:
    if isinstance(err, EditionUnavailableError):
        return _problem(
            403,
            "Edition unavailable",
            "The education edition is not enabled for this organization.",
            "edition-unavailable",
        )
    if isinstance(err, InvalidSemesterDates):
        return _problem(
            400, "Invalid semester dates", str(err), "invalid-semester-dates"
        )
    if isinstance(err, InvalidMembershipDates):
        return _problem(
            400, "Invalid membership dates", str(err), "invalid-membership-dates"
        )
    if isinstance(err, DuplicateIdentifierError):
        return _problem(409, "Duplicate identifier", str(err), "duplicate-identifier")
    if isinstance(err, ProfileAlreadyExistsError):
        return _problem(
            409, "Profile already exists", str(err), "profile-already-exists"
        )
    if isinstance(err, EducationEntityNotFound):
        return _problem(404, "Not Found", str(err), "not-found")
    if isinstance(err, AuthorizationDenied):
        return _problem(403, "Forbidden", "Authorization denied.", "forbidden")
    if isinstance(err, ValueError):
        return _problem(400, "Bad Request", str(err), "bad-request")
    raise err


def create_education_blueprint(
    service: EducationService,
    access_tokens: AccessTokenService,
    tenant_request_context: TenantRequestContext | None = None,
    url_prefix: str = "/api/v1/education",
) -> Blueprint:
    """Create blueprint for education endpoints."""
    bp_name = f"education_{url_prefix.replace('/', '_').strip('_')}"
    bp = Blueprint(bp_name, __name__, url_prefix=url_prefix)

    # --- Departments ---

    @bp.get("/departments")
    @_require_principal(access_tokens, tenant_request_context)
    def list_departments() -> Response:
        try:
            items = service.list_departments(actor=_principal_from_request())
            return jsonify({"items": [_department_dict(d) for d in items]})
        except Exception as err:
            return _handle_education_error(err)

    @bp.get("/departments/<uuid:department_id>")
    @_require_principal(access_tokens, tenant_request_context)
    def get_department(department_id: UUID) -> Response:
        try:
            d = service.get_department(
                actor=_principal_from_request(), department_id=department_id
            )
            return jsonify(_department_dict(d))
        except Exception as err:
            return _handle_education_error(err)

    @bp.post("/departments")
    @_require_principal(access_tokens, tenant_request_context)
    def create_department() -> Response:
        payload = request.get_json(silent=True) or {}
        try:
            d = service.create_department(
                actor=_principal_from_request(),
                code=str(payload.get("code", "")),
                name=str(payload.get("name", "")),
                status=str(payload.get("status", "active")),
            )
            response = jsonify(_department_dict(d))
            response.status_code = 201
            return response
        except Exception as err:
            return _handle_education_error(err)

    # --- Semesters ---

    @bp.get("/semesters")
    @_require_principal(access_tokens, tenant_request_context)
    def list_semesters() -> Response:
        try:
            items = service.list_semesters(actor=_principal_from_request())
            return jsonify({"items": [_semester_dict(s) for s in items]})
        except Exception as err:
            return _handle_education_error(err)

    @bp.get("/semesters/<uuid:semester_id>")
    @_require_principal(access_tokens, tenant_request_context)
    def get_semester(semester_id: UUID) -> Response:
        try:
            s = service.get_semester(
                actor=_principal_from_request(), semester_id=semester_id
            )
            return jsonify(_semester_dict(s))
        except Exception as err:
            return _handle_education_error(err)

    @bp.post("/semesters")
    @_require_principal(access_tokens, tenant_request_context)
    def create_semester() -> Response:
        payload = request.get_json(silent=True) or {}
        try:
            starts_on_str = payload.get("starts_on")
            ends_on_str = payload.get("ends_on")
            if not starts_on_str or not ends_on_str:
                return _problem(
                    400,
                    "Bad Request",
                    "starts_on and ends_on are required",
                    "bad-request",
                )
            starts_on = date.fromisoformat(str(starts_on_str))
            ends_on = date.fromisoformat(str(ends_on_str))
            s = service.create_semester(
                actor=_principal_from_request(),
                name=str(payload.get("name", "")),
                starts_on=starts_on,
                ends_on=ends_on,
                status=str(payload.get("status", "active")),
            )
            response = jsonify(_semester_dict(s))
            response.status_code = 201
            return response
        except Exception as err:
            return _handle_education_error(err)

    # --- Courses ---

    @bp.get("/courses")
    @_require_principal(access_tokens, tenant_request_context)
    def list_courses() -> Response:
        try:
            items = service.list_courses(actor=_principal_from_request())
            return jsonify({"items": [_course_dict(c) for c in items]})
        except Exception as err:
            return _handle_education_error(err)

    @bp.get("/courses/<uuid:course_id>")
    @_require_principal(access_tokens, tenant_request_context)
    def get_course(course_id: UUID) -> Response:
        try:
            c = service.get_course(actor=_principal_from_request(), course_id=course_id)
            return jsonify(_course_dict(c))
        except Exception as err:
            return _handle_education_error(err)

    @bp.post("/courses")
    @_require_principal(access_tokens, tenant_request_context)
    def create_course() -> Response:
        payload = request.get_json(silent=True) or {}
        try:
            dept_id_str = payload.get("department_id")
            dept_id = UUID(str(dept_id_str)) if dept_id_str else None
            c = service.create_course(
                actor=_principal_from_request(),
                code=str(payload.get("code", "")),
                name=str(payload.get("name", "")),
                department_id=dept_id,
                status=str(payload.get("status", "active")),
            )
            response = jsonify(_course_dict(c))
            response.status_code = 201
            return response
        except Exception as err:
            return _handle_education_error(err)

    # --- Classes ---

    @bp.get("/classes")
    @_require_principal(access_tokens, tenant_request_context)
    def list_classes() -> Response:
        try:
            items = service.list_classes(actor=_principal_from_request())
            return jsonify({"items": [_class_dict(c) for c in items]})
        except Exception as err:
            return _handle_education_error(err)

    @bp.get("/classes/<uuid:class_id>")
    @_require_principal(access_tokens, tenant_request_context)
    def get_class(class_id: UUID) -> Response:
        try:
            c = service.get_class(actor=_principal_from_request(), class_id=class_id)
            return jsonify(_class_dict(c))
        except Exception as err:
            return _handle_education_error(err)

    @bp.post("/classes")
    @_require_principal(access_tokens, tenant_request_context)
    def create_class() -> Response:
        payload = request.get_json(silent=True) or {}
        try:
            dept_id_str = payload.get("department_id")
            dept_id = UUID(str(dept_id_str)) if dept_id_str else None
            sem_id_str = payload.get("semester_id")
            if not sem_id_str:
                return _problem(
                    400, "Bad Request", "semester_id is required", "bad-request"
                )
            c = service.create_class(
                actor=_principal_from_request(),
                code=str(payload.get("code", "")),
                name=str(payload.get("name", "")),
                semester_id=UUID(str(sem_id_str)),
                department_id=dept_id,
                status=str(payload.get("status", "active")),
            )
            response = jsonify(_class_dict(c))
            response.status_code = 201
            return response
        except Exception as err:
            return _handle_education_error(err)

    # --- Class Memberships ---

    @bp.get("/classes/<uuid:class_id>/memberships")
    @_require_principal(access_tokens, tenant_request_context)
    def list_class_memberships(class_id: UUID) -> Response:
        try:
            items = service.list_class_memberships(
                actor=_principal_from_request(), class_id=class_id
            )
            return jsonify({"items": [_membership_dict(m) for m in items]})
        except Exception as err:
            return _handle_education_error(err)

    @bp.post("/classes/<uuid:class_id>/memberships")
    @_require_principal(access_tokens, tenant_request_context)
    def create_class_membership(class_id: UUID) -> Response:
        payload = request.get_json(silent=True) or {}
        try:
            student_id_str = payload.get("student_id")
            if not student_id_str:
                return _problem(
                    400, "Bad Request", "student_id is required", "bad-request"
                )
            joined_str = payload.get("joined_at")
            left_str = payload.get("left_at")
            joined_at = datetime.fromisoformat(str(joined_str)) if joined_str else None
            left_at = datetime.fromisoformat(str(left_str)) if left_str else None
            m = service.create_class_membership(
                actor=_principal_from_request(),
                class_id=class_id,
                student_id=UUID(str(student_id_str)),
                joined_at=joined_at,
                left_at=left_at,
            )
            response = jsonify(_membership_dict(m))
            response.status_code = 201
            return response
        except Exception as err:
            return _handle_education_error(err)

    # --- Students ---

    @bp.get("/students")
    @_require_principal(access_tokens, tenant_request_context)
    def list_students() -> Response:
        try:
            items = service.list_students(actor=_principal_from_request())
            return jsonify({"items": [_student_dict(s) for s in items]})
        except Exception as err:
            return _handle_education_error(err)

    @bp.get("/students/<uuid:student_id>")
    @_require_principal(access_tokens, tenant_request_context)
    def get_student(student_id: UUID) -> Response:
        try:
            s = service.get_student(
                actor=_principal_from_request(), student_id=student_id
            )
            return jsonify(_student_dict(s))
        except Exception as err:
            return _handle_education_error(err)

    @bp.post("/students")
    @_require_principal(access_tokens, tenant_request_context)
    def create_student() -> Response:
        payload = request.get_json(silent=True) or {}
        try:
            user_id_str = payload.get("user_id")
            if not user_id_str:
                return _problem(
                    400, "Bad Request", "user_id is required", "bad-request"
                )
            dept_id_str = payload.get("department_id")
            dept_id = UUID(str(dept_id_str)) if dept_id_str else None
            s = service.create_student(
                actor=_principal_from_request(),
                user_id=UUID(str(user_id_str)),
                student_number=str(payload.get("student_number", "")),
                department_id=dept_id,
                status=str(payload.get("status", "active")),
            )
            response = jsonify(_student_dict(s))
            response.status_code = 201
            return response
        except Exception as err:
            return _handle_education_error(err)

    # --- Teachers ---

    @bp.get("/teachers")
    @_require_principal(access_tokens, tenant_request_context)
    def list_teachers() -> Response:
        try:
            items = service.list_teachers(actor=_principal_from_request())
            return jsonify({"items": [_teacher_dict(t) for t in items]})
        except Exception as err:
            return _handle_education_error(err)

    @bp.get("/teachers/<uuid:teacher_id>")
    @_require_principal(access_tokens, tenant_request_context)
    def get_teacher(teacher_id: UUID) -> Response:
        try:
            t = service.get_teacher(
                actor=_principal_from_request(), teacher_id=teacher_id
            )
            return jsonify(_teacher_dict(t))
        except Exception as err:
            return _handle_education_error(err)

    @bp.post("/teachers")
    @_require_principal(access_tokens, tenant_request_context)
    def create_teacher() -> Response:
        payload = request.get_json(silent=True) or {}
        try:
            user_id_str = payload.get("user_id")
            if not user_id_str:
                return _problem(
                    400, "Bad Request", "user_id is required", "bad-request"
                )
            dept_id_str = payload.get("department_id")
            dept_id = UUID(str(dept_id_str)) if dept_id_str else None
            t = service.create_teacher(
                actor=_principal_from_request(),
                user_id=UUID(str(user_id_str)),
                employee_number=str(payload.get("employee_number", "")),
                department_id=dept_id,
                status=str(payload.get("status", "active")),
            )
            response = jsonify(_teacher_dict(t))
            response.status_code = 201
            return response
        except Exception as err:
            return _handle_education_error(err)

    return bp
