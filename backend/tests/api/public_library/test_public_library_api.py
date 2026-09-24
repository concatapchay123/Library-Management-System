"""API contract and HTTP tests for public library endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from flask import Flask

from openlibrary.app.correlation import install_request_correlation
from openlibrary.app.errors import install_problem_details_handlers
from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.authorization import AuthorizationPort
from openlibrary.modules.public_library.api import create_public_library_blueprint
from openlibrary.modules.public_library.application import (
    DEFAULT_BASIC_DURATION_DAYS,
    DEFAULT_BASIC_MAX_ACTIVE_LOANS,
    DEFAULT_PREMIUM_DURATION_DAYS,
    DEFAULT_PREMIUM_MAX_ACTIVE_LOANS,
    PublicLibraryService,
)
from openlibrary.modules.public_library.domain import (
    Member,
    MembershipPlan,
    Subscription,
)


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
        self.members: list[Member] = []
        self.plans: list[MembershipPlan] = []
        self.subscriptions: list[Subscription] = []

    def is_edition_enabled(self, organization_id: UUID) -> bool:
        return self.is_enabled

    def create_member(self, member: Member) -> Member:
        self.members.append(member)
        return member

    def get_member(self, org_id: UUID, member_id: UUID) -> Member | None:
        for m in self.members:
            if m.organization_id == org_id and m.member_id == member_id:
                return m
        return None

    def get_member_by_user_id(self, org_id: UUID, user_id: UUID) -> Member | None:
        for m in self.members:
            if m.organization_id == org_id and m.user_id == user_id:
                return m
        return None

    def get_member_by_number(self, org_id: UUID, member_number: str) -> Member | None:
        for m in self.members:
            if m.organization_id == org_id and m.member_number == member_number:
                return m
        return None

    def list_members(self, org_id: UUID) -> list[Member]:
        return [m for m in self.members if m.organization_id == org_id]

    def update_member(self, member: Member) -> Member:
        for i, m in enumerate(self.members):
            if (
                m.organization_id == member.organization_id
                and m.member_id == member.member_id
            ):
                self.members[i] = member
                return member
        self.members.append(member)
        return member

    def create_plan(self, plan: MembershipPlan) -> MembershipPlan:
        self.plans.append(plan)
        return plan

    def get_plan(self, org_id: UUID, plan_id: UUID) -> MembershipPlan | None:
        for p in self.plans:
            if p.organization_id == org_id and p.plan_id == plan_id:
                return p
        return None

    def get_plan_by_code(self, org_id: UUID, code: str) -> MembershipPlan | None:
        for p in self.plans:
            if p.organization_id == org_id and p.code == code:
                return p
        return None

    def list_plans(
        self, org_id: UUID, status: str | None = None
    ) -> list[MembershipPlan]:
        plans = [p for p in self.plans if p.organization_id == org_id]
        if status is not None:
            plans = [p for p in plans if p.status == status]
        return plans

    def update_plan(self, plan: MembershipPlan) -> MembershipPlan:
        for i, p in enumerate(self.plans):
            if p.organization_id == plan.organization_id and p.plan_id == plan.plan_id:
                self.plans[i] = plan
                return plan
        self.plans.append(plan)
        return plan

    def seed_default_plans(self, organization_id: UUID) -> list[MembershipPlan]:
        now = datetime.now(timezone.utc)
        seeded: list[MembershipPlan] = []
        basic = self.get_plan_by_code(organization_id, "basic")
        if basic is None:
            basic = MembershipPlan(
                plan_id=uuid4(),
                organization_id=organization_id,
                code="basic",
                name="Basic Membership",
                description="Default basic membership plan",
                max_active_loans=DEFAULT_BASIC_MAX_ACTIVE_LOANS,
                duration_days=DEFAULT_BASIC_DURATION_DAYS,
                price=Decimal("0.0000"),
                currency="USD",
                status="active",
                created_at=now,
                updated_at=now,
            )
            self.create_plan(basic)
        seeded.append(basic)

        premium = self.get_plan_by_code(organization_id, "premium")
        if premium is None:
            premium = MembershipPlan(
                plan_id=uuid4(),
                organization_id=organization_id,
                code="premium",
                name="Premium Membership",
                description="Default premium membership plan",
                max_active_loans=DEFAULT_PREMIUM_MAX_ACTIVE_LOANS,
                duration_days=DEFAULT_PREMIUM_DURATION_DAYS,
                price=Decimal("0.0000"),
                currency="USD",
                status="active",
                created_at=now,
                updated_at=now,
            )
            self.create_plan(premium)
        seeded.append(premium)
        return seeded

    def create_subscription(self, subscription: Subscription) -> Subscription:
        self.subscriptions.append(subscription)
        return subscription

    def get_subscription(
        self, org_id: UUID, subscription_id: UUID
    ) -> Subscription | None:
        for s in self.subscriptions:
            if s.organization_id == org_id and s.subscription_id == subscription_id:
                return s
        return None

    def list_subscriptions(
        self,
        org_id: UUID,
        member_id: UUID | None = None,
        status: str | None = None,
    ) -> list[Subscription]:
        subs = [s for s in self.subscriptions if s.organization_id == org_id]
        if member_id is not None:
            subs = [s for s in subs if s.member_id == member_id]
        if status is not None:
            subs = [s for s in subs if s.status == status]
        return subs

    def get_active_subscription_for_member(
        self, org_id: UUID, member_id: UUID, as_of: datetime
    ) -> Subscription | None:
        active = [
            s
            for s in self.subscriptions
            if s.organization_id == org_id
            and s.member_id == member_id
            and s.status == "active"
            and s.starts_at <= as_of < s.ends_at
        ]
        if not active:
            return None
        return sorted(active, key=lambda s: s.ends_at, reverse=True)[0]

    def update_subscription(self, subscription: Subscription) -> Subscription:
        for i, s in enumerate(self.subscriptions):
            if (
                s.organization_id == subscription.organization_id
                and s.subscription_id == subscription.subscription_id
            ):
                self.subscriptions[i] = subscription
                return subscription
        self.subscriptions.append(subscription)
        return subscription


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
    service = PublicLibraryService(store, authorizer)

    app = Flask(__name__)
    install_request_correlation(app)
    install_problem_details_handlers(app)

    app.register_blueprint(
        create_public_library_blueprint(
            service=service,
            access_tokens=access_tokens,  # type: ignore[arg-type]
            tenant_request_context=None,
            url_prefix="/api/v1/public-library",
        )
    )

    token = "valid-token"
    return app, token, org_id


def test_endpoints_require_authentication() -> None:
    store = _FakeStore(is_enabled=True)
    app, _, _ = _build_test_app(store, {"public_library.read", "public_library.manage"})
    client = app.test_client()

    resp = client.get("/api/v1/public-library/members")
    assert resp.status_code == 401


def test_edition_unavailable_returns_403() -> None:
    """Acceptance criteria: Edition-disabled organizations cannot access public-library APIs."""
    store = _FakeStore(is_enabled=False)
    app, token, _ = _build_test_app(
        store, {"public_library.read", "public_library.manage"}
    )
    client = app.test_client()
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get("/api/v1/public-library/members", headers=headers)
    assert resp.status_code == 403
    data = resp.get_json()
    assert data["type"] == "https://openlibraryos.example/problems/edition-unavailable"
    assert "not enabled" in data["detail"]


def test_member_lifecycle_api() -> None:
    store = _FakeStore(is_enabled=True)
    app, token, _ = _build_test_app(
        store, {"public_library.read", "public_library.manage"}
    )
    client = app.test_client()
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create member
    user_id = str(uuid4())
    resp = client.post(
        "/api/v1/public-library/members",
        headers=headers,
        json={"user_id": user_id, "member_number": "MEM-101"},
    )
    assert resp.status_code == 201
    created = resp.get_json()
    assert created["member_number"] == "MEM-101"
    assert created["status"] == "active"
    member_id = created["member_id"]

    # 2. Get member by ID
    resp = client.get(f"/api/v1/public-library/members/{member_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["member_number"] == "MEM-101"

    # 3. Get member by user ID
    resp = client.get(
        f"/api/v1/public-library/members/by-user/{user_id}", headers=headers
    )
    assert resp.status_code == 200
    assert resp.get_json()["member_id"] == member_id

    # 4. List members
    resp = client.get("/api/v1/public-library/members", headers=headers)
    assert resp.status_code == 200
    assert len(resp.get_json()["items"]) == 1

    # 5. Update status
    resp = client.patch(
        f"/api/v1/public-library/members/{member_id}/status",
        headers=headers,
        json={"status": "suspended"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "suspended"


def test_membership_plans_api() -> None:
    store = _FakeStore(is_enabled=True)
    app, token, _ = _build_test_app(
        store, {"public_library.read", "public_library.manage"}
    )
    client = app.test_client()
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Seed default plans
    resp = client.post("/api/v1/public-library/membership-plans/seed", headers=headers)
    assert resp.status_code == 200
    items = resp.get_json()["items"]
    assert len(items) == 2
    codes = {p["code"] for p in items}
    assert codes == {"basic", "premium"}

    # 2. List plans via /membership-plans and alias /plans
    resp = client.get("/api/v1/public-library/membership-plans", headers=headers)
    assert resp.status_code == 200
    assert len(resp.get_json()["items"]) == 2

    resp_alias = client.get("/api/v1/public-library/plans", headers=headers)
    assert resp_alias.status_code == 200
    assert len(resp_alias.get_json()["items"]) == 2

    # 3. Create custom plan
    resp = client.post(
        "/api/v1/public-library/membership-plans",
        headers=headers,
        json={
            "code": "student",
            "name": "Student Plan",
            "max_active_loans": 8,
            "duration_days": 28,
        },
    )
    assert resp.status_code == 201
    plan = resp.get_json()
    assert plan["code"] == "student"
    assert plan["max_active_loans"] == 8
    plan_id = plan["plan_id"]

    # 4. Get plan
    resp = client.get(
        f"/api/v1/public-library/membership-plans/{plan_id}", headers=headers
    )
    assert resp.status_code == 200
    assert resp.get_json()["name"] == "Student Plan"

    # 5. Update plan
    resp = client.put(
        f"/api/v1/public-library/membership-plans/{plan_id}",
        headers=headers,
        json={"name": "Discounted Student Plan", "max_active_loans": 10},
    )
    assert resp.status_code == 200
    assert resp.get_json()["name"] == "Discounted Student Plan"
    assert resp.get_json()["max_active_loans"] == 10


def test_subscriptions_api() -> None:
    store = _FakeStore(is_enabled=True)
    app, token, org_id = _build_test_app(
        store, {"public_library.read", "public_library.manage"}
    )
    client = app.test_client()
    headers = {"Authorization": f"Bearer {token}"}

    # Setup member and plan
    seed_resp = client.post(
        "/api/v1/public-library/membership-plans/seed", headers=headers
    )
    basic_plan = next(p for p in seed_resp.get_json()["items"] if p["code"] == "basic")

    member_resp = client.post(
        "/api/v1/public-library/members",
        headers=headers,
        json={"user_id": str(uuid4()), "member_number": "MEM-SUB"},
    )
    member = member_resp.get_json()

    now = datetime.now(timezone.utc)
    starts_at = now.isoformat()
    ends_at = (now + timedelta(days=30)).isoformat()

    # 1. Create subscription
    resp = client.post(
        "/api/v1/public-library/subscriptions",
        headers=headers,
        json={
            "member_id": member["member_id"],
            "plan_id": basic_plan["plan_id"],
            "starts_at": starts_at,
            "ends_at": ends_at,
        },
    )
    assert resp.status_code == 201
    sub = resp.get_json()
    assert sub["status"] == "active"
    sub_id = sub["subscription_id"]

    # 2. Get subscription
    resp = client.get(f"/api/v1/public-library/subscriptions/{sub_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["subscription_id"] == sub_id

    # 3. List subscriptions
    resp = client.get(
        f"/api/v1/public-library/subscriptions?member_id={member['member_id']}",
        headers=headers,
    )
    assert resp.status_code == 200
    assert len(resp.get_json()["items"]) == 1

    # 4. Cancel subscription
    resp = client.post(
        f"/api/v1/public-library/subscriptions/{sub_id}/cancel",
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "cancelled"
