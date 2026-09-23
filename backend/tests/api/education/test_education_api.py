"""API contract and HTTP tests for education endpoints."""

from __future__ import annotations

from uuid import UUID, uuid4

from flask import Flask

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
)
from openlibrary.modules.education.application import EducationService
from openlibrary.modules.education.api import create_education_blueprint


class _FakeAuthorizer(AuthorizationPort):
    def __init__(self, permissions: set[str]) -> None:
        self.permissions = permissions

    def require(self, actor: Principal, permission: str) -> None:
        from openlibrary.modules.core.application.authorization import (
            AuthorizationDenied,
        )

        if permission not in self.permissions:
            raise AuthorizationDenied(f"Missing {permission}")


class _FakeStore:
    def __init__(self, is_enabled: bool = True) -> None:
        self.is_enabled = is_enabled
        self.departments: list[Department] = []
        self.semesters: list[Semester] = []
        self.courses: list[Course] = []
        self.classes: list[Class] = []
        self.students: list[Student] = []
        self.teachers: list[Teacher] = []
        self.memberships: list[ClassMembership] = []
        self.policies: list[BorrowerPolicy] = []

    def is_edition_enabled(self, organization_id: UUID) -> bool:
        return self.is_enabled

    def create_department(self, d: Department) -> Department:
        self.departments.append(d)
        return d

    def get_department(self, org_id: UUID, dept_id: UUID) -> Department | None:
        for d in self.departments:
            if d.organization_id == org_id and d.department_id == dept_id:
                return d
        return None

    def list_departments(self, org_id: UUID) -> list[Department]:
        return [d for d in self.departments if d.organization_id == org_id]

    def create_semester(self, s: Semester) -> Semester:
        self.semesters.append(s)
        return s

    def get_semester(self, org_id: UUID, sem_id: UUID) -> Semester | None:
        for s in self.semesters:
            if s.organization_id == org_id and s.semester_id == sem_id:
                return s
        return None

    def list_semesters(self, org_id: UUID) -> list[Semester]:
        return [s for s in self.semesters if s.organization_id == org_id]

    def create_course(self, c: Course) -> Course:
        self.courses.append(c)
        return c

    def get_course(self, org_id: UUID, course_id: UUID) -> Course | None:
        for c in self.courses:
            if c.organization_id == org_id and c.course_id == course_id:
                return c
        return None

    def list_courses(self, org_id: UUID) -> list[Course]:
        return [c for c in self.courses if c.organization_id == org_id]

    def create_class(self, c: Class) -> Class:
        self.classes.append(c)
        return c

    def get_class(self, org_id: UUID, class_id: UUID) -> Class | None:
        for c in self.classes:
            if c.organization_id == org_id and c.class_id == class_id:
                return c
        return None

    def list_classes(self, org_id: UUID) -> list[Class]:
        return [c for c in self.classes if c.organization_id == org_id]

    def create_student(self, s: Student) -> Student:
        self.students.append(s)
        return s

    def get_student(self, org_id: UUID, student_id: UUID) -> Student | None:
        for s in self.students:
            if s.organization_id == org_id and s.student_id == student_id:
                return s
        return None

    def list_students(self, org_id: UUID) -> list[Student]:
        return [s for s in self.students if s.organization_id == org_id]

    def create_teacher(self, t: Teacher) -> Teacher:
        self.teachers.append(t)
        return t

    def get_teacher(self, org_id: UUID, teacher_id: UUID) -> Teacher | None:
        for t in self.teachers:
            if t.organization_id == org_id and t.teacher_id == teacher_id:
                return t
        return None

    def list_teachers(self, org_id: UUID) -> list[Teacher]:
        return [t for t in self.teachers if t.organization_id == org_id]

    def create_class_membership(self, m: ClassMembership) -> ClassMembership:
        self.memberships.append(m)
        return m

    def list_class_memberships(
        self, org_id: UUID, class_id: UUID
    ) -> list[ClassMembership]:
        return [
            m
            for m in self.memberships
            if m.organization_id == org_id and m.class_id == class_id
        ]

    def get_student_by_user_id(self, org_id: UUID, user_id: UUID) -> Student | None:
        for s in self.students:
            if s.organization_id == org_id and s.user_id == user_id:
                return s
        return None

    def get_teacher_by_user_id(self, org_id: UUID, user_id: UUID) -> Teacher | None:
        for t in self.teachers:
            if t.organization_id == org_id and t.user_id == user_id:
                return t
        return None

    def get_borrower_policy(
        self, org_id: UUID, borrower_type: str
    ) -> BorrowerPolicy | None:
        for p in self.policies:
            if p.organization_id == org_id and p.borrower_type == borrower_type:
                return p
        return None

    def list_borrower_policies(self, org_id: UUID) -> list[BorrowerPolicy]:
        return [p for p in self.policies if p.organization_id == org_id]

    def upsert_borrower_policy(self, policy: BorrowerPolicy) -> BorrowerPolicy:
        for i, p in enumerate(self.policies):
            if (
                p.organization_id == policy.organization_id
                and p.borrower_type == policy.borrower_type
            ):
                self.policies[i] = policy
                return policy
        self.policies.append(policy)
        return policy


class _StubAccessTokenService:
    def __init__(self, principal: Principal) -> None:
        self.principal = principal

    def verify(self, token: str) -> Principal:
        from openlibrary.modules.core.application.access_tokens import (
            TokenVerificationError,
        )

        if token == "valid-token":
            return self.principal
        raise TokenVerificationError("Invalid token")


def _build_test_app(
    store: _FakeStore,
    permissions: set[str],
) -> tuple[Flask, str, UUID]:
    org_id = uuid4()
    user_id = uuid4()
    principal = Principal(user_id=user_id, organization_id=org_id, session_id=uuid4())
    access_tokens = _StubAccessTokenService(principal)
    authorizer = _FakeAuthorizer(permissions)
    service = EducationService(store, authorizer)

    app = Flask(__name__)
    from openlibrary.app.correlation import install_request_correlation
    from openlibrary.app.errors import install_problem_details_handlers

    install_request_correlation(app)
    install_problem_details_handlers(app)

    app.register_blueprint(
        create_education_blueprint(
            service=service,
            access_tokens=access_tokens,  # type: ignore[arg-type]
            tenant_request_context=None,
            url_prefix="/education",
        )
    )

    token = "valid-token"
    return app, token, org_id


def test_education_endpoints_require_authentication() -> None:
    store = _FakeStore(is_enabled=True)
    app, _, _ = _build_test_app(store, {"education.read", "education.manage"})
    client = app.test_client()

    response = client.get("/education/departments")
    assert response.status_code == 401
    assert response.headers["Content-Type"] == "application/problem+json"


def test_education_endpoints_return_unavailable_when_edition_disabled() -> None:
    store = _FakeStore(is_enabled=False)
    app, token, _ = _build_test_app(store, {"education.read", "education.manage"})
    client = app.test_client()

    response = client.get(
        "/education/departments",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert response.headers["Content-Type"] == "application/problem+json"
    data = response.get_json()
    assert data["type"] == "https://openlibraryos.example/problems/edition-unavailable"
    assert data["title"] == "Edition unavailable"
    assert "not enabled" in data["detail"]


def test_department_crud_flow() -> None:
    store = _FakeStore(is_enabled=True)
    app, token, org_id = _build_test_app(store, {"education.read", "education.manage"})
    client = app.test_client()

    # Create department
    response = client.post(
        "/education/departments",
        headers={"Authorization": f"Bearer {token}"},
        json={"code": "CS", "name": "Computer Science"},
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data["code"] == "CS"
    assert data["name"] == "Computer Science"
    dept_id = data["department_id"]

    # List departments
    list_resp = client.get(
        "/education/departments",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    list_data = list_resp.get_json()
    assert len(list_data["items"]) == 1
    assert list_data["items"][0]["department_id"] == dept_id

    # Get department
    get_resp = client.get(
        f"/education/departments/{dept_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 200
    assert get_resp.get_json()["department_id"] == dept_id


def test_semester_date_validation_via_api() -> None:
    store = _FakeStore(is_enabled=True)
    app, token, _ = _build_test_app(store, {"education.read", "education.manage"})
    client = app.test_client()

    response = client.post(
        "/education/semesters",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Fall 2026",
            "starts_on": "2026-12-31",
            "ends_on": "2026-09-01",
        },
    )
    assert response.status_code == 400
    assert response.headers["Content-Type"] == "application/problem+json"
    data = response.get_json()
    assert (
        data["type"] == "https://openlibraryos.example/problems/invalid-semester-dates"
    )
    assert "starts_on must be before ends_on" in data["detail"]


def test_borrower_policy_api_workflow() -> None:
    store = _FakeStore(is_enabled=True)
    app, token, _ = _build_test_app(store, {"education.read", "education.manage"})
    client = app.test_client()

    # 1. Put student policy
    put_resp = client.put(
        "/education/borrower-policies/student",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "max_active_loans": 7,
            "duration_days": 21,
        },
    )
    assert put_resp.status_code == 200
    data = put_resp.get_json()
    assert data["borrower_type"] == "student"
    assert data["max_active_loans"] == 7
    assert data["duration_days"] == 21

    # 2. Get student policy
    get_resp = client.get(
        "/education/borrower-policies/student",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 200
    assert get_resp.get_json()["max_active_loans"] == 7

    # 3. List policies
    list_resp = client.get(
        "/education/borrower-policies",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    items = list_resp.get_json()["items"]
    assert len(items) == 1
    assert items[0]["borrower_type"] == "student"
