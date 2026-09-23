"""Application services and persistence ports for public library edition."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from typing import Protocol
from uuid import UUID, uuid4

from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.authorization import AuthorizationPort
from openlibrary.modules.public_library.domain import (
    ActiveSubscriptionExistsError,
    DuplicateIdentifierError,
    EditionUnavailableError,
    InvalidPlanError,
    Member,
    MemberNotFoundError,
    MemberStatus,
    MembershipPlan,
    MembershipPlanNotFoundError,
    PlanStatus,
    ProfileAlreadyExistsError,
    Subscription,
    SubscriptionInactiveError,
    SubscriptionNotFoundError,
    SubscriptionStatus,
    validate_plan_limits,
    validate_subscription_dates,
)

# Seed defaults for public library membership plans
DEFAULT_BASIC_MAX_ACTIVE_LOANS: int = 5
DEFAULT_BASIC_DURATION_DAYS: int = 30
DEFAULT_PREMIUM_MAX_ACTIVE_LOANS: int = 20
DEFAULT_PREMIUM_DURATION_DAYS: int = 90


class PublicLibraryStore(Protocol):
    """Persistence port for tenant-isolated public library entities."""

    def is_edition_enabled(self, organization_id: UUID) -> bool: ...

    # --- Members ---

    def create_member(self, member: Member) -> Member: ...

    def get_member(self, organization_id: UUID, member_id: UUID) -> Member | None: ...

    def get_member_by_user_id(
        self, organization_id: UUID, user_id: UUID
    ) -> Member | None: ...

    def get_member_by_number(
        self, organization_id: UUID, member_number: str
    ) -> Member | None: ...

    def list_members(self, organization_id: UUID) -> list[Member]: ...

    def update_member(self, member: Member) -> Member: ...

    # --- Membership Plans ---

    def create_plan(self, plan: MembershipPlan) -> MembershipPlan: ...

    def get_plan(
        self, organization_id: UUID, plan_id: UUID
    ) -> MembershipPlan | None: ...

    def get_plan_by_code(
        self, organization_id: UUID, code: str
    ) -> MembershipPlan | None: ...

    def list_plans(
        self, organization_id: UUID, status: str | None = None
    ) -> list[MembershipPlan]: ...

    def update_plan(self, plan: MembershipPlan) -> MembershipPlan: ...

    def seed_default_plans(self, organization_id: UUID) -> list[MembershipPlan]: ...

    # --- Subscriptions ---

    def create_subscription(self, subscription: Subscription) -> Subscription: ...

    def get_subscription(
        self, organization_id: UUID, subscription_id: UUID
    ) -> Subscription | None: ...

    def list_subscriptions(
        self,
        organization_id: UUID,
        member_id: UUID | None = None,
        status: str | None = None,
    ) -> list[Subscription]: ...

    def get_active_subscription_for_member(
        self, organization_id: UUID, member_id: UUID, as_of: datetime
    ) -> Subscription | None: ...

    def update_subscription(self, subscription: Subscription) -> Subscription: ...


def _system_now() -> datetime:
    return datetime.now(timezone.utc)


class PublicLibraryService:
    """Application use cases for managing public library members, plans, and subscriptions."""

    def __init__(
        self,
        store: PublicLibraryStore,
        authorizer: AuthorizationPort,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._authorizer = authorizer
        self._clock = clock or _system_now

    def _ensure_edition_enabled(self, organization_id: UUID) -> None:
        if not self._store.is_edition_enabled(organization_id):
            raise EditionUnavailableError(
                f"Public library edition is not enabled for organization {organization_id}"
            )

    # --- Members ---

    def list_members(self, *, actor: Principal) -> list[Member]:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "public_library.read")
        return self._store.list_members(actor.organization_id)

    def get_member(self, *, actor: Principal, member_id: UUID) -> Member:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "public_library.read")
        member = self._store.get_member(actor.organization_id, member_id)
        if member is None:
            raise MemberNotFoundError(f"Member {member_id} not found")
        return member

    def get_member_by_user_id(self, *, actor: Principal, user_id: UUID) -> Member:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "public_library.read")
        member = self._store.get_member_by_user_id(actor.organization_id, user_id)
        if member is None:
            raise MemberNotFoundError(f"Member for user {user_id} not found")
        return member

    def create_member(
        self,
        *,
        actor: Principal,
        user_id: UUID,
        member_number: str,
        status: str = MemberStatus.ACTIVE,
    ) -> Member:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "public_library.manage")
        clean_number = member_number.strip()
        if not clean_number or len(clean_number) > 64:
            raise ValueError("Member number must be between 1 and 64 characters")
        if status not in MemberStatus.ALL:
            raise ValueError(f"Invalid member status: {status}")

        existing_user_member = self._store.get_member_by_user_id(
            actor.organization_id, user_id
        )
        if existing_user_member is not None:
            raise ProfileAlreadyExistsError(
                f"User {user_id} already has a member profile in this organization"
            )

        existing_number = self._store.get_member_by_number(
            actor.organization_id, clean_number
        )
        if existing_number is not None:
            raise DuplicateIdentifierError(
                f"Member number '{clean_number}' is already registered in this organization"
            )

        now = self._clock()
        member = Member(
            member_id=uuid4(),
            organization_id=actor.organization_id,
            user_id=user_id,
            member_number=clean_number,
            status=status,
            created_at=now,
            updated_at=now,
        )
        return self._store.create_member(member)

    def update_member_status(
        self,
        *,
        actor: Principal,
        member_id: UUID,
        status: str,
    ) -> Member:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "public_library.manage")
        if status not in MemberStatus.ALL:
            raise ValueError(f"Invalid member status: {status}")
        member = self.get_member(actor=actor, member_id=member_id)
        updated = Member(
            member_id=member.member_id,
            organization_id=member.organization_id,
            user_id=member.user_id,
            member_number=member.member_number,
            status=status,
            created_at=member.created_at,
            updated_at=self._clock(),
        )
        return self._store.update_member(updated)

    # --- Membership Plans ---

    def list_plans(
        self, *, actor: Principal, status: str | None = None
    ) -> list[MembershipPlan]:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "public_library.read")
        return self._store.list_plans(actor.organization_id, status=status)

    def get_plan(self, *, actor: Principal, plan_id: UUID) -> MembershipPlan:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "public_library.read")
        plan = self._store.get_plan(actor.organization_id, plan_id)
        if plan is None:
            raise MembershipPlanNotFoundError(f"Membership plan {plan_id} not found")
        return plan

    def create_plan(
        self,
        *,
        actor: Principal,
        code: str,
        name: str,
        max_active_loans: int,
        duration_days: int,
        description: str | None = None,
        price: Decimal = Decimal("0.0000"),
        currency: str = "USD",
        status: str = PlanStatus.ACTIVE,
    ) -> MembershipPlan:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "public_library.manage")
        clean_code = code.strip().lower()
        clean_name = name.strip()
        if not clean_code or len(clean_code) > 64:
            raise ValueError("Plan code must be between 1 and 64 characters")
        if not clean_name or len(clean_name) > 255:
            raise ValueError("Plan name must be between 1 and 255 characters")
        if status not in PlanStatus.ALL:
            raise ValueError(f"Invalid plan status: {status}")
        validate_plan_limits(max_active_loans, duration_days)

        existing = self._store.get_plan_by_code(actor.organization_id, clean_code)
        if existing is not None:
            raise DuplicateIdentifierError(
                f"Plan code '{clean_code}' is already registered in this organization"
            )

        now = self._clock()
        plan = MembershipPlan(
            plan_id=uuid4(),
            organization_id=actor.organization_id,
            code=clean_code,
            name=clean_name,
            description=description.strip() if description else None,
            max_active_loans=max_active_loans,
            duration_days=duration_days,
            price=price,
            currency=currency.strip().upper(),
            status=status,
            created_at=now,
            updated_at=now,
        )
        return self._store.create_plan(plan)

    def update_plan(
        self,
        *,
        actor: Principal,
        plan_id: UUID,
        name: str | None = None,
        description: str | None = None,
        max_active_loans: int | None = None,
        duration_days: int | None = None,
        price: Decimal | None = None,
        currency: str | None = None,
        status: str | None = None,
    ) -> MembershipPlan:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "public_library.manage")
        existing = self.get_plan(actor=actor, plan_id=plan_id)

        new_max_loans = (
            max_active_loans
            if max_active_loans is not None
            else existing.max_active_loans
        )
        new_duration = (
            duration_days if duration_days is not None else existing.duration_days
        )
        validate_plan_limits(new_max_loans, new_duration)

        if status is not None and status not in PlanStatus.ALL:
            raise ValueError(f"Invalid plan status: {status}")

        updated = MembershipPlan(
            plan_id=existing.plan_id,
            organization_id=existing.organization_id,
            code=existing.code,
            name=name.strip() if name is not None else existing.name,
            description=description.strip()
            if description is not None
            else existing.description,
            max_active_loans=new_max_loans,
            duration_days=new_duration,
            price=price if price is not None else existing.price,
            currency=currency.strip().upper()
            if currency is not None
            else existing.currency,
            status=status if status is not None else existing.status,
            created_at=existing.created_at,
            updated_at=self._clock(),
        )
        return self._store.update_plan(updated)

    def seed_default_plans(self, *, actor: Principal) -> list[MembershipPlan]:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "public_library.manage")
        return self._store.seed_default_plans(actor.organization_id)

    # --- Subscriptions ---

    def list_subscriptions(
        self,
        *,
        actor: Principal,
        member_id: UUID | None = None,
        status: str | None = None,
    ) -> list[Subscription]:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "public_library.read")
        return self._store.list_subscriptions(
            actor.organization_id, member_id=member_id, status=status
        )

    def get_subscription(
        self, *, actor: Principal, subscription_id: UUID
    ) -> Subscription:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "public_library.read")
        sub = self._store.get_subscription(actor.organization_id, subscription_id)
        if sub is None:
            raise SubscriptionNotFoundError(f"Subscription {subscription_id} not found")
        return sub

    def create_subscription(
        self,
        *,
        actor: Principal,
        member_id: UUID,
        plan_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
        status: str = SubscriptionStatus.ACTIVE,
    ) -> Subscription:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "public_library.manage")
        if status not in SubscriptionStatus.ALL:
            raise ValueError(f"Invalid subscription status: {status}")

        validate_subscription_dates(starts_at, ends_at)

        # Verify member exists and is active
        member = self._store.get_member(actor.organization_id, member_id)
        if member is None:
            raise MemberNotFoundError(f"Member {member_id} not found")
        if member.status != MemberStatus.ACTIVE:
            raise SubscriptionInactiveError(
                f"Cannot create subscription for member with status '{member.status}'"
            )

        # Verify plan exists and is active
        plan = self._store.get_plan(actor.organization_id, plan_id)
        if plan is None:
            raise MembershipPlanNotFoundError(f"Membership plan {plan_id} not found")
        if plan.status != PlanStatus.ACTIVE:
            raise InvalidPlanError(f"Membership plan {plan_id} is {plan.status}")

        # Check for existing active overlapping subscription
        if status == SubscriptionStatus.ACTIVE:
            existing_subs = self._store.list_subscriptions(
                actor.organization_id,
                member_id=member_id,
                status=SubscriptionStatus.ACTIVE,
            )
            for existing_sub in existing_subs:
                if max(existing_sub.starts_at, starts_at) < min(
                    existing_sub.ends_at, ends_at
                ):
                    raise ActiveSubscriptionExistsError(
                        f"Member {member_id} already has an active overlapping subscription {existing_sub.subscription_id}"
                    )

        now = self._clock()
        sub = Subscription(
            subscription_id=uuid4(),
            organization_id=actor.organization_id,
            member_id=member_id,
            plan_id=plan_id,
            starts_at=starts_at,
            ends_at=ends_at,
            status=status,
            created_at=now,
            updated_at=now,
        )
        return self._store.create_subscription(sub)

    def cancel_subscription(
        self, *, actor: Principal, subscription_id: UUID
    ) -> Subscription:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "public_library.manage")
        sub = self.get_subscription(actor=actor, subscription_id=subscription_id)
        if sub.status == SubscriptionStatus.CANCELLED:
            return sub

        now = self._clock()
        updated = Subscription(
            subscription_id=sub.subscription_id,
            organization_id=sub.organization_id,
            member_id=sub.member_id,
            plan_id=sub.plan_id,
            starts_at=sub.starts_at,
            ends_at=sub.ends_at,
            status=SubscriptionStatus.CANCELLED,
            created_at=sub.created_at,
            updated_at=now,
        )
        return self._store.update_subscription(updated)
