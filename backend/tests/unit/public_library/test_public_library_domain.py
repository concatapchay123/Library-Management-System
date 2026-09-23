"""Unit tests for public library domain entities, business rules, and application service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.authorization import AuthorizationDenied
from openlibrary.modules.public_library.application import (
    DEFAULT_BASIC_DURATION_DAYS,
    DEFAULT_BASIC_MAX_ACTIVE_LOANS,
    DEFAULT_PREMIUM_DURATION_DAYS,
    DEFAULT_PREMIUM_MAX_ACTIVE_LOANS,
    PublicLibraryService,
)
from openlibrary.modules.public_library.domain import (
    ActiveSubscriptionExistsError,
    DuplicateIdentifierError,
    EditionUnavailableError,
    InvalidPlanError,
    InvalidSubscriptionDatesError,
    Member,
    MemberStatus,
    MembershipPlan,
    PlanStatus,
    ProfileAlreadyExistsError,
    Subscription,
    SubscriptionInactiveError,
    SubscriptionStatus,
    validate_plan_limits,
    validate_subscription_dates,
)


class _MockAuthorizer:
    def __init__(self, permissions: set[str]) -> None:
        self.permissions = permissions

    def require(self, actor: Principal, permission: str) -> None:
        if permission not in self.permissions:
            raise AuthorizationDenied(f"Missing permission: {permission}")


class _InMemoryPublicLibraryStore:
    def __init__(self, enabled_editions: dict[UUID, bool] | None = None) -> None:
        self.enabled_editions = enabled_editions or {}
        self.members: dict[UUID, Member] = {}
        self.plans: dict[UUID, MembershipPlan] = {}
        self.subscriptions: dict[UUID, Subscription] = {}

    def is_edition_enabled(self, organization_id: UUID) -> bool:
        return self.enabled_editions.get(organization_id, True)

    def create_member(self, member: Member) -> Member:
        self.members[member.member_id] = member
        return member

    def get_member(self, organization_id: UUID, member_id: UUID) -> Member | None:
        m = self.members.get(member_id)
        if m and m.organization_id == organization_id:
            return m
        return None

    def get_member_by_user_id(
        self, organization_id: UUID, user_id: UUID
    ) -> Member | None:
        for m in self.members.values():
            if m.organization_id == organization_id and m.user_id == user_id:
                return m
        return None

    def get_member_by_number(
        self, organization_id: UUID, member_number: str
    ) -> Member | None:
        for m in self.members.values():
            if (
                m.organization_id == organization_id
                and m.member_number == member_number
            ):
                return m
        return None

    def list_members(self, organization_id: UUID) -> list[Member]:
        return [
            m for m in self.members.values() if m.organization_id == organization_id
        ]

    def update_member(self, member: Member) -> Member:
        self.members[member.member_id] = member
        return member

    def create_plan(self, plan: MembershipPlan) -> MembershipPlan:
        self.plans[plan.plan_id] = plan
        return plan

    def get_plan(self, organization_id: UUID, plan_id: UUID) -> MembershipPlan | None:
        p = self.plans.get(plan_id)
        if p and p.organization_id == organization_id:
            return p
        return None

    def get_plan_by_code(
        self, organization_id: UUID, code: str
    ) -> MembershipPlan | None:
        for p in self.plans.values():
            if p.organization_id == organization_id and p.code == code:
                return p
        return None

    def list_plans(
        self, organization_id: UUID, status: str | None = None
    ) -> list[MembershipPlan]:
        plans = [p for p in self.plans.values() if p.organization_id == organization_id]
        if status is not None:
            plans = [p for p in plans if p.status == status]
        return sorted(plans, key=lambda p: p.created_at)

    def update_plan(self, plan: MembershipPlan) -> MembershipPlan:
        self.plans[plan.plan_id] = plan
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
        self.subscriptions[subscription.subscription_id] = subscription
        return subscription

    def get_subscription(
        self, organization_id: UUID, subscription_id: UUID
    ) -> Subscription | None:
        s = self.subscriptions.get(subscription_id)
        if s and s.organization_id == organization_id:
            return s
        return None

    def list_subscriptions(
        self,
        organization_id: UUID,
        member_id: UUID | None = None,
        status: str | None = None,
    ) -> list[Subscription]:
        subs = [
            s
            for s in self.subscriptions.values()
            if s.organization_id == organization_id
        ]
        if member_id is not None:
            subs = [s for s in subs if s.member_id == member_id]
        if status is not None:
            subs = [s for s in subs if s.status == status]
        return sorted(subs, key=lambda s: s.created_at, reverse=True)

    def get_active_subscription_for_member(
        self, organization_id: UUID, member_id: UUID, as_of: datetime
    ) -> Subscription | None:
        active = [
            s
            for s in self.subscriptions.values()
            if s.organization_id == organization_id
            and s.member_id == member_id
            and s.status == "active"
            and s.starts_at <= as_of < s.ends_at
        ]
        if not active:
            return None
        return sorted(active, key=lambda s: s.ends_at, reverse=True)[0]

    def update_subscription(self, subscription: Subscription) -> Subscription:
        self.subscriptions[subscription.subscription_id] = subscription
        return subscription


def _build_service(
    permissions: set[str] | None = None,
    enabled_editions: dict[UUID, bool] | None = None,
    clock: datetime | None = None,
) -> tuple[PublicLibraryService, _InMemoryPublicLibraryStore]:
    store = _InMemoryPublicLibraryStore(enabled_editions=enabled_editions)
    perms = (
        permissions
        if permissions is not None
        else {"public_library.read", "public_library.manage"}
    )
    authorizer = _MockAuthorizer(perms)
    now = clock or datetime.now(timezone.utc)
    service = PublicLibraryService(store, authorizer, clock=lambda: now)
    return service, store


def test_validation_helpers() -> None:
    now = datetime.now(timezone.utc)
    # Valid dates
    validate_subscription_dates(now, now + timedelta(days=30))

    # Invalid dates
    with pytest.raises(InvalidSubscriptionDatesError):
        validate_subscription_dates(now, now)
    with pytest.raises(InvalidSubscriptionDatesError):
        validate_subscription_dates(now + timedelta(days=1), now)

    # Valid plan limits
    validate_plan_limits(5, 30)

    # Invalid plan limits
    with pytest.raises(InvalidPlanError):
        validate_plan_limits(0, 30)
    with pytest.raises(InvalidPlanError):
        validate_plan_limits(5, -1)


def test_member_crud_and_validation() -> None:
    org_id = uuid4()
    actor = Principal(user_id=uuid4(), organization_id=org_id, session_id=uuid4())
    service, store = _build_service()

    # Create member
    user_id = uuid4()
    member = service.create_member(
        actor=actor,
        user_id=user_id,
        member_number="MEM-100",
    )
    assert member.member_number == "MEM-100"
    assert member.status == MemberStatus.ACTIVE

    # Duplicate user member
    with pytest.raises(ProfileAlreadyExistsError):
        service.create_member(actor=actor, user_id=user_id, member_number="MEM-101")

    # Duplicate member number
    with pytest.raises(DuplicateIdentifierError):
        service.create_member(actor=actor, user_id=uuid4(), member_number="MEM-100")

    # Invalid member number
    with pytest.raises(ValueError, match="1 and 64 characters"):
        service.create_member(actor=actor, user_id=uuid4(), member_number="")

    # Invalid status
    with pytest.raises(ValueError, match="Invalid member status"):
        service.create_member(
            actor=actor,
            user_id=uuid4(),
            member_number="MEM-102",
            status="unknown",
        )

    # List & get member
    members = service.list_members(actor=actor)
    assert len(members) == 1

    fetched = service.get_member(actor=actor, member_id=member.member_id)
    assert fetched.member_id == member.member_id

    fetched_by_user = service.get_member_by_user_id(actor=actor, user_id=user_id)
    assert fetched_by_user.member_id == member.member_id

    # Update member status
    updated = service.update_member_status(
        actor=actor, member_id=member.member_id, status=MemberStatus.SUSPENDED
    )
    assert updated.status == MemberStatus.SUSPENDED


def test_membership_plan_crud_and_seed() -> None:
    org_id = uuid4()
    actor = Principal(user_id=uuid4(), organization_id=org_id, session_id=uuid4())
    service, store = _build_service()

    # Seed default plans
    seeded = service.seed_default_plans(actor=actor)
    assert len(seeded) == 2
    codes = {p.code for p in seeded}
    assert codes == {"basic", "premium"}

    # Create custom plan
    plan = service.create_plan(
        actor=actor,
        code="student-discount",
        name="Student Plan",
        max_active_loans=7,
        duration_days=21,
    )
    assert plan.code == "student-discount"
    assert plan.max_active_loans == 7

    # Duplicate plan code
    with pytest.raises(DuplicateIdentifierError):
        service.create_plan(
            actor=actor,
            code="student-discount",
            name="Another Student Plan",
            max_active_loans=7,
            duration_days=21,
        )

    # Update plan
    updated = service.update_plan(
        actor=actor,
        plan_id=plan.plan_id,
        name="Updated Student Plan",
        max_active_loans=10,
    )
    assert updated.name == "Updated Student Plan"
    assert updated.max_active_loans == 10

    # List plans
    all_plans = service.list_plans(actor=actor)
    assert len(all_plans) == 3


def test_subscription_lifecycle_and_validation() -> None:
    org_id = uuid4()
    actor = Principal(user_id=uuid4(), organization_id=org_id, session_id=uuid4())
    now = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
    service, store = _build_service(clock=now)

    # Seed plans & create member
    plans = service.seed_default_plans(actor=actor)
    basic = next(p for p in plans if p.code == "basic")
    member = service.create_member(
        actor=actor,
        user_id=uuid4(),
        member_number="MEM-200",
    )

    # Create active subscription
    sub = service.create_subscription(
        actor=actor,
        member_id=member.member_id,
        plan_id=basic.plan_id,
        starts_at=now,
        ends_at=now + timedelta(days=30),
    )
    assert sub.status == SubscriptionStatus.ACTIVE

    # Overlapping active subscription raises error
    with pytest.raises(ActiveSubscriptionExistsError):
        service.create_subscription(
            actor=actor,
            member_id=member.member_id,
            plan_id=basic.plan_id,
            starts_at=now + timedelta(days=1),
            ends_at=now + timedelta(days=31),
        )

    # Cancel subscription
    cancelled = service.cancel_subscription(
        actor=actor, subscription_id=sub.subscription_id
    )
    assert cancelled.status == SubscriptionStatus.CANCELLED

    # Now a new active subscription can be created
    new_sub = service.create_subscription(
        actor=actor,
        member_id=member.member_id,
        plan_id=basic.plan_id,
        starts_at=now,
        ends_at=now + timedelta(days=30),
    )
    assert new_sub.status == SubscriptionStatus.ACTIVE


def test_subscription_creation_requires_active_member_and_plan() -> None:
    org_id = uuid4()
    actor = Principal(user_id=uuid4(), organization_id=org_id, session_id=uuid4())
    now = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
    service, store = _build_service(clock=now)

    plans = service.seed_default_plans(actor=actor)
    basic = next(p for p in plans if p.code == "basic")
    member = service.create_member(
        actor=actor,
        user_id=uuid4(),
        member_number="MEM-300",
        status=MemberStatus.INACTIVE,
    )

    # Cannot subscribe inactive member
    with pytest.raises(SubscriptionInactiveError, match="status 'inactive'"):
        service.create_subscription(
            actor=actor,
            member_id=member.member_id,
            plan_id=basic.plan_id,
            starts_at=now,
            ends_at=now + timedelta(days=30),
        )

    # Archive plan
    service.update_plan(actor=actor, plan_id=basic.plan_id, status=PlanStatus.ARCHIVED)
    service.update_member_status(
        actor=actor, member_id=member.member_id, status=MemberStatus.ACTIVE
    )

    with pytest.raises(InvalidPlanError, match="is archived"):
        service.create_subscription(
            actor=actor,
            member_id=member.member_id,
            plan_id=basic.plan_id,
            starts_at=now,
            ends_at=now + timedelta(days=30),
        )


def test_edition_unavailable_blocks_all_service_operations() -> None:
    org_id = uuid4()
    actor = Principal(user_id=uuid4(), organization_id=org_id, session_id=uuid4())
    service, _ = _build_service(enabled_editions={org_id: False})

    with pytest.raises(EditionUnavailableError):
        service.list_members(actor=actor)

    with pytest.raises(EditionUnavailableError):
        service.list_plans(actor=actor)

    with pytest.raises(EditionUnavailableError):
        service.create_member(actor=actor, user_id=uuid4(), member_number="MEM-ERR")


def test_rbac_permissions_enforced() -> None:
    org_id = uuid4()
    actor = Principal(user_id=uuid4(), organization_id=org_id, session_id=uuid4())

    # Read-only actor
    service, _ = _build_service(permissions={"public_library.read"})
    service.list_members(actor=actor)  # OK

    with pytest.raises(AuthorizationDenied, match="public_library.manage"):
        service.create_member(actor=actor, user_id=uuid4(), member_number="MEM-RO")

    # Manage-only actor
    service_write_only, _ = _build_service(permissions={"public_library.manage"})
    with pytest.raises(AuthorizationDenied, match="public_library.read"):
        service_write_only.list_members(actor=actor)
