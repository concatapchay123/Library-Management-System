"""Integration tests for public library members, membership plans, and subscription policy.

Validates BE-022 requirements:
- Manage public-library members, configurable plans and subscription validity as a borrowing-policy provider.
- Subscription validity: active, expired, cancelled, and future subscriptions.
- Plan selection: Basic 5 books/30 days and Premium 20 books/90 days as configurable seed data.
- Tenant isolation: member and subscription relationships remain tenant-scoped.
- Loan checkout snapshots: policy facts are captured at checkout and immutable after plan changes.
- Core circulation independence: zero public_library imports in core domain.
- Evidence checkpoints:
  * An inactive subscription cannot provide a borrowing policy.
  * Plan defaults are tenant-scoped seed data, not controller constants.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.authorization import AuthorizationPort
from openlibrary.modules.core.application.copy_status import (
    CopyStatusHistory,
    CopyStatusStore,
)
from openlibrary.modules.core.application.inventory import BookCopy
from openlibrary.modules.core.application.loans import (
    Loan,
    LoanService,
    LoanStore,
)
from openlibrary.modules.core.domain.copy_status import CopyStatus
from openlibrary.modules.core.domain.loans import (
    BorrowerNotEligibleError,
    LoanStatus,
)
from openlibrary.modules.public_library.application import (
    DEFAULT_BASIC_DURATION_DAYS,
    DEFAULT_BASIC_MAX_ACTIVE_LOANS,
    DEFAULT_PREMIUM_DURATION_DAYS,
    DEFAULT_PREMIUM_MAX_ACTIVE_LOANS,
    PublicLibraryStore,
)
from openlibrary.modules.public_library.domain import (
    Member,
    MembershipPlan,
    Subscription,
)
from openlibrary.modules.public_library.policy import (
    PublicLibraryBorrowingPolicyAdapter,
)


class _AllowAllAuthorizer(AuthorizationPort):
    def require(self, actor: Principal, permission: str) -> None:
        pass


@dataclass
class _InMemoryCopyStore(CopyStatusStore):
    copies: dict[UUID, BookCopy] = field(default_factory=dict)
    history: list[CopyStatusHistory] = field(default_factory=list)

    def get_copy(self, organization_id: UUID, copy_id: UUID) -> BookCopy:
        copy = self.copies.get(copy_id)
        if copy is None or copy.organization_id != organization_id:
            raise KeyError(copy_id)
        return copy

    def update_copy_status(
        self, organization_id: UUID, copy_id: UUID, status: str
    ) -> None:
        copy = self.get_copy(organization_id, copy_id)
        self.copies[copy_id] = BookCopy(
            copy_id=copy.copy_id,
            organization_id=copy.organization_id,
            book_id=copy.book_id,
            barcode=copy.barcode,
            status=status,
            location_id=copy.location_id,
            condition_code=copy.condition_code,
            acquired_at=copy.acquired_at,
            created_at=copy.created_at,
            updated_at=datetime.now(timezone.utc),
        )

    def append_history(self, record: CopyStatusHistory) -> None:
        self.history.append(record)

    def list_history(
        self, organization_id: UUID, copy_id: UUID
    ) -> list[CopyStatusHistory]:
        return [h for h in self.history if h.copy_id == copy_id]


@dataclass
class _InMemoryLoanStore(LoanStore):
    loans: dict[UUID, Loan] = field(default_factory=dict)

    def create_loan(self, loan: Loan) -> Loan:
        self.loans[loan.loan_id] = loan
        return loan

    def get_loan(self, organization_id: UUID, loan_id: UUID) -> Loan:
        loan = self.loans.get(loan_id)
        if loan is None or loan.organization_id != organization_id:
            raise KeyError(loan_id)
        return loan

    def update_loan(self, loan: Loan) -> Loan:
        if (
            loan.loan_id not in self.loans
            or self.loans[loan.loan_id].organization_id != loan.organization_id
        ):
            raise KeyError(loan.loan_id)
        self.loans[loan.loan_id] = loan
        return loan

    def list_loans(
        self,
        organization_id: UUID,
        *,
        borrower_user_id: UUID | None = None,
        copy_id: UUID | None = None,
        status: str | None = None,
    ) -> list[Loan]:
        results = [
            loan
            for loan in self.loans.values()
            if loan.organization_id == organization_id
        ]
        if borrower_user_id is not None:
            results = [
                loan for loan in results if loan.borrower_user_id == borrower_user_id
            ]
        if copy_id is not None:
            results = [loan for loan in results if loan.copy_id == copy_id]
        if status is not None:
            results = [loan for loan in results if loan.status == status]
        return sorted(results, key=lambda loan: loan.created_at, reverse=True)

    def count_active_loans_for_borrower(
        self, organization_id: UUID, borrower_user_id: UUID
    ) -> int:
        return sum(
            1
            for loan in self.loans.values()
            if loan.organization_id == organization_id
            and loan.borrower_user_id == borrower_user_id
            and loan.status == LoanStatus.CHECKED_OUT
        )

    def get_active_loan_for_copy(
        self, organization_id: UUID, copy_id: UUID
    ) -> Loan | None:
        for loan in self.loans.values():
            if (
                loan.organization_id == organization_id
                and loan.copy_id == copy_id
                and loan.status == LoanStatus.CHECKED_OUT
            ):
                return loan
        return None

    def find_overdue_loans(self, organization_id: UUID, as_of: datetime) -> list[Loan]:
        return [
            loan
            for loan in self.loans.values()
            if loan.organization_id == organization_id
            and loan.status == LoanStatus.CHECKED_OUT
            and loan.due_at is not None
            and loan.due_at < as_of
        ]


@dataclass
class _InMemoryPublicLibraryStore(PublicLibraryStore):
    enabled_orgs: set[UUID] = field(default_factory=set)
    members: dict[tuple[UUID, UUID], Member] = field(default_factory=dict)
    members_by_user: dict[tuple[UUID, UUID], Member] = field(default_factory=dict)
    plans: dict[tuple[UUID, UUID], MembershipPlan] = field(default_factory=dict)
    plans_by_code: dict[tuple[UUID, str], MembershipPlan] = field(default_factory=dict)
    subscriptions: dict[tuple[UUID, UUID], Subscription] = field(default_factory=dict)

    def is_edition_enabled(self, organization_id: UUID) -> bool:
        return organization_id in self.enabled_orgs

    def create_member(self, member: Member) -> Member:
        self.members[(member.organization_id, member.member_id)] = member
        self.members_by_user[(member.organization_id, member.user_id)] = member
        return member

    def get_member(self, organization_id: UUID, member_id: UUID) -> Member | None:
        return self.members.get((organization_id, member_id))

    def get_member_by_user_id(
        self, organization_id: UUID, user_id: UUID
    ) -> Member | None:
        return self.members_by_user.get((organization_id, user_id))

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
        self.members[(member.organization_id, member.member_id)] = member
        self.members_by_user[(member.organization_id, member.user_id)] = member
        return member

    def create_plan(self, plan: MembershipPlan) -> MembershipPlan:
        self.plans[(plan.organization_id, plan.plan_id)] = plan
        self.plans_by_code[(plan.organization_id, plan.code)] = plan
        return plan

    def get_plan(self, organization_id: UUID, plan_id: UUID) -> MembershipPlan | None:
        return self.plans.get((organization_id, plan_id))

    def get_plan_by_code(
        self, organization_id: UUID, code: str
    ) -> MembershipPlan | None:
        return self.plans_by_code.get((organization_id, code))

    def list_plans(
        self, organization_id: UUID, status: str | None = None
    ) -> list[MembershipPlan]:
        plans = [p for p in self.plans.values() if p.organization_id == organization_id]
        if status is not None:
            plans = [p for p in plans if p.status == status]
        return sorted(plans, key=lambda p: p.created_at)

    def update_plan(self, plan: MembershipPlan) -> MembershipPlan:
        self.plans[(plan.organization_id, plan.plan_id)] = plan
        self.plans_by_code[(plan.organization_id, plan.code)] = plan
        return plan

    def seed_default_plans(self, organization_id: UUID) -> list[MembershipPlan]:
        now = datetime.now(timezone.utc)
        seeded: list[MembershipPlan] = []
        if (organization_id, "basic") not in self.plans_by_code:
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
        else:
            seeded.append(self.plans_by_code[(organization_id, "basic")])

        if (organization_id, "premium") not in self.plans_by_code:
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
        else:
            seeded.append(self.plans_by_code[(organization_id, "premium")])

        return seeded

    def create_subscription(self, subscription: Subscription) -> Subscription:
        self.subscriptions[
            (subscription.organization_id, subscription.subscription_id)
        ] = subscription
        return subscription

    def get_subscription(
        self, organization_id: UUID, subscription_id: UUID
    ) -> Subscription | None:
        return self.subscriptions.get((organization_id, subscription_id))

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
        self.subscriptions[
            (subscription.organization_id, subscription.subscription_id)
        ] = subscription
        return subscription


def _setup_fixture(now: datetime | None = None):
    if now is None:
        now = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
    org_id = uuid4()
    user_id = uuid4()
    store = _InMemoryPublicLibraryStore(enabled_orgs={org_id})

    # Seed plans
    plans = store.seed_default_plans(org_id)
    basic_plan = next(p for p in plans if p.code == "basic")
    premium_plan = next(p for p in plans if p.code == "premium")

    # Create member
    member = Member(
        member_id=uuid4(),
        organization_id=org_id,
        user_id=user_id,
        member_number="MEM-001",
        status="active",
        created_at=now,
        updated_at=now,
    )
    store.create_member(member)

    # Create active subscription for basic plan
    sub = Subscription(
        subscription_id=uuid4(),
        organization_id=org_id,
        member_id=member.member_id,
        plan_id=basic_plan.plan_id,
        starts_at=now - timedelta(days=1),
        ends_at=now + timedelta(days=29),
        status="active",
        created_at=now - timedelta(days=1),
        updated_at=now - timedelta(days=1),
    )
    store.create_subscription(sub)

    adapter = PublicLibraryBorrowingPolicyAdapter(
        store=store,
        clock=lambda: now,
    )

    return {
        "org_id": org_id,
        "user_id": user_id,
        "store": store,
        "member": member,
        "basic_plan": basic_plan,
        "premium_plan": premium_plan,
        "subscription": sub,
        "adapter": adapter,
        "now": now,
    }


def test_active_subscription_resolves_borrowing_policy() -> None:
    f = _setup_fixture()
    policy = f["adapter"].resolve_policy(f["org_id"], f["user_id"])

    assert policy.borrower_type == "member"
    assert policy.max_active_loans == DEFAULT_BASIC_MAX_ACTIVE_LOANS  # 5
    assert policy.duration_days == DEFAULT_BASIC_DURATION_DAYS  # 30
    assert policy.policy_snapshot["borrower_type"] == "member"
    assert policy.policy_snapshot["source"] == "public_library"
    assert policy.policy_snapshot["member_id"] == str(f["member"].member_id)
    assert policy.policy_snapshot["member_number"] == "MEM-001"
    assert policy.policy_snapshot["plan_code"] == "basic"
    assert policy.policy_snapshot["max_active_loans"] == 5
    assert policy.policy_snapshot["duration_days"] == 30


def test_inactive_subscription_cannot_provide_borrowing_policy() -> None:
    """Evidence Checkpoint: An inactive subscription cannot provide a borrowing policy."""
    f = _setup_fixture()
    store: _InMemoryPublicLibraryStore = f["store"]
    sub: Subscription = f["subscription"]

    # Mark subscription inactive/cancelled
    cancelled = Subscription(
        subscription_id=sub.subscription_id,
        organization_id=sub.organization_id,
        member_id=sub.member_id,
        plan_id=sub.plan_id,
        starts_at=sub.starts_at,
        ends_at=sub.ends_at,
        status="cancelled",
        created_at=sub.created_at,
        updated_at=f["now"],
    )
    store.update_subscription(cancelled)

    with pytest.raises(BorrowerNotEligibleError, match="active subscription"):
        f["adapter"].resolve_policy(f["org_id"], f["user_id"])


def test_expired_subscription_cannot_provide_borrowing_policy() -> None:
    """An expired subscription (ends_at <= now) cannot provide a borrowing policy."""
    now = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
    f = _setup_fixture(now=now)
    store: _InMemoryPublicLibraryStore = f["store"]
    sub: Subscription = f["subscription"]

    # Subscription ended yesterday
    expired = Subscription(
        subscription_id=sub.subscription_id,
        organization_id=sub.organization_id,
        member_id=sub.member_id,
        plan_id=sub.plan_id,
        starts_at=now - timedelta(days=30),
        ends_at=now - timedelta(days=1),
        status="active",
        created_at=now - timedelta(days=30),
        updated_at=now - timedelta(days=30),
    )
    store.update_subscription(expired)

    with pytest.raises(BorrowerNotEligibleError, match="active subscription"):
        f["adapter"].resolve_policy(f["org_id"], f["user_id"])


def test_future_subscription_cannot_provide_borrowing_policy() -> None:
    """A future subscription (starts_at > now) cannot provide a borrowing policy."""
    now = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
    f = _setup_fixture(now=now)
    store: _InMemoryPublicLibraryStore = f["store"]
    sub: Subscription = f["subscription"]

    # Starts tomorrow
    future = Subscription(
        subscription_id=sub.subscription_id,
        organization_id=sub.organization_id,
        member_id=sub.member_id,
        plan_id=sub.plan_id,
        starts_at=now + timedelta(days=1),
        ends_at=now + timedelta(days=31),
        status="active",
        created_at=now,
        updated_at=now,
    )
    store.update_subscription(future)

    with pytest.raises(BorrowerNotEligibleError, match="active subscription"):
        f["adapter"].resolve_policy(f["org_id"], f["user_id"])


def test_inactive_member_cannot_provide_borrowing_policy() -> None:
    """A member with status != active cannot borrow even if subscription is active."""
    f = _setup_fixture()
    store: _InMemoryPublicLibraryStore = f["store"]
    member: Member = f["member"]

    suspended = Member(
        member_id=member.member_id,
        organization_id=member.organization_id,
        user_id=member.user_id,
        member_number=member.member_number,
        status="suspended",
        created_at=member.created_at,
        updated_at=f["now"],
    )
    store.update_member(suspended)

    with pytest.raises(BorrowerNotEligibleError, match="suspended"):
        f["adapter"].resolve_policy(f["org_id"], f["user_id"])


def test_non_member_cannot_provide_borrowing_policy() -> None:
    """User without a member profile in the organization cannot borrow."""
    f = _setup_fixture()
    other_user_id = uuid4()

    with pytest.raises(BorrowerNotEligibleError, match="no active member profile"):
        f["adapter"].resolve_policy(f["org_id"], other_user_id)


def test_plan_defaults_are_tenant_scoped_seed_data() -> None:
    """Evidence Checkpoint: Plan defaults are tenant-scoped seed data, not controller constants."""
    f = _setup_fixture()
    store: _InMemoryPublicLibraryStore = f["store"]
    org_id = f["org_id"]

    plans = store.list_plans(org_id)
    plan_codes = {p.code for p in plans}
    assert "basic" in plan_codes
    assert "premium" in plan_codes

    basic = next(p for p in plans if p.code == "basic")
    premium = next(p for p in plans if p.code == "premium")
    assert basic.max_active_loans == 5
    assert basic.duration_days == 30
    assert premium.max_active_loans == 20
    assert premium.duration_days == 90

    # Updating plan in DB immediately affects policy resolution
    updated_basic = MembershipPlan(
        plan_id=basic.plan_id,
        organization_id=org_id,
        code=basic.code,
        name=basic.name,
        description=basic.description,
        max_active_loans=8,
        duration_days=45,
        price=basic.price,
        currency=basic.currency,
        status=basic.status,
        created_at=basic.created_at,
        updated_at=f["now"],
    )
    store.update_plan(updated_basic)

    policy = f["adapter"].resolve_policy(org_id, f["user_id"])
    assert policy.max_active_loans == 8
    assert policy.duration_days == 45
    assert policy.policy_snapshot["max_active_loans"] == 8
    assert policy.policy_snapshot["duration_days"] == 45


def test_premium_plan_selection() -> None:
    f = _setup_fixture()
    store: _InMemoryPublicLibraryStore = f["store"]
    premium_plan: MembershipPlan = f["premium_plan"]
    sub: Subscription = f["subscription"]

    # Switch subscription to premium plan
    premium_sub = Subscription(
        subscription_id=sub.subscription_id,
        organization_id=sub.organization_id,
        member_id=sub.member_id,
        plan_id=premium_plan.plan_id,
        starts_at=sub.starts_at,
        ends_at=sub.ends_at,
        status="active",
        created_at=sub.created_at,
        updated_at=f["now"],
    )
    store.update_subscription(premium_sub)

    policy = f["adapter"].resolve_policy(f["org_id"], f["user_id"])
    assert policy.max_active_loans == DEFAULT_PREMIUM_MAX_ACTIVE_LOANS  # 20
    assert policy.duration_days == DEFAULT_PREMIUM_DURATION_DAYS  # 90
    assert policy.policy_snapshot["plan_code"] == "premium"


def test_tenant_isolation_for_membership_and_policy() -> None:
    """Members, plans, and subscriptions from one tenant cannot resolve in another tenant."""
    f = _setup_fixture()
    other_org_id = uuid4()
    store: _InMemoryPublicLibraryStore = f["store"]
    store.enabled_orgs.add(other_org_id)

    # User has profile in org_id, but query in other_org_id fails
    with pytest.raises(BorrowerNotEligibleError, match="no active member profile"):
        f["adapter"].resolve_policy(other_org_id, f["user_id"])


def test_edition_disabled_cannot_provide_borrowing_policy() -> None:
    """Edition-disabled organizations cannot access public-library borrowing policy."""
    f = _setup_fixture()
    store: _InMemoryPublicLibraryStore = f["store"]
    # Disable edition for this org
    store.enabled_orgs.remove(f["org_id"])

    with pytest.raises(BorrowerNotEligibleError, match="not enabled"):
        f["adapter"].resolve_policy(f["org_id"], f["user_id"])


def test_plan_changes_do_not_mutate_loan_policy_snapshot() -> None:
    """Reviewer Checklist: Plan changes do not mutate a loan policy snapshot."""
    now = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
    f = _setup_fixture(now=now)
    store: _InMemoryPublicLibraryStore = f["store"]
    org_id = f["org_id"]
    user_id = f["user_id"]
    adapter = f["adapter"]

    loan_store = _InMemoryLoanStore()
    copy_store = _InMemoryCopyStore()
    authorizer = _AllowAllAuthorizer()

    loan_service = LoanService(
        loan_store=loan_store,
        copy_store=copy_store,
        authorizer=authorizer,
        policy_resolver=adapter,
    )

    copy_id = uuid4()
    copy_store.copies[copy_id] = BookCopy(
        copy_id=copy_id,
        organization_id=org_id,
        book_id=uuid4(),
        barcode="BC-001",
        status=CopyStatus.AVAILABLE,
        location_id=uuid4(),
        condition_code="good",
        acquired_at=now,
        created_at=now,
        updated_at=now,
    )

    librarian_actor = Principal(
        user_id=uuid4(), organization_id=org_id, session_id=uuid4()
    )

    # 1. Checkout loan directly via desk_checkout
    checked_out = loan_service.desk_checkout(
        actor=librarian_actor,
        copy_id=copy_id,
        borrower_user_id=user_id,
    )
    assert checked_out.status == LoanStatus.CHECKED_OUT
    assert checked_out.due_at is not None
    assert checked_out.policy_snapshot["duration_days"] == 30
    assert checked_out.policy_snapshot["max_active_loans"] == 5

    # 2. Modify plan to 10 books / 60 days
    basic = f["basic_plan"]
    updated_plan = MembershipPlan(
        plan_id=basic.plan_id,
        organization_id=org_id,
        code=basic.code,
        name=basic.name,
        description=basic.description,
        max_active_loans=10,
        duration_days=60,
        price=basic.price,
        currency=basic.currency,
        status=basic.status,
        created_at=basic.created_at,
        updated_at=now,
    )
    store.update_plan(updated_plan)

    # 3. Verify loan policy snapshot and due_at on existing loan remain unchanged
    persisted_loan = loan_store.get_loan(org_id, checked_out.loan_id)
    assert persisted_loan.due_at == checked_out.due_at
    assert persisted_loan.policy_snapshot["max_active_loans"] == 5
    assert persisted_loan.policy_snapshot["duration_days"] == 30

    # 4. But future loan requests will use the new policy
    new_policy = adapter.resolve_policy(org_id, user_id)
    assert new_policy.max_active_loans == 10
    assert new_policy.duration_days == 60


def test_zero_public_library_imports_in_core() -> None:
    """Acceptance criteria: Core circulation remains independent from public_library."""
    core_root = (
        Path(__file__).resolve().parents[3] / "src" / "openlibrary" / "modules" / "core"
    )
    for py_file in core_root.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "public_library" not in alias.name, (
                        f"{py_file} contains forbidden import: {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert "public_library" not in module, (
                    f"{py_file} contains forbidden from-import: {module}"
                )
