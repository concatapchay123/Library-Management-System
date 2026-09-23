"""Borrowing policy adapter for the public library edition.

Implements the BorrowingPolicyResolver protocol consumed by core circulation.
Zero core loan entities or core domain logic know about member/subscription concepts.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID

from openlibrary.modules.core.application.loans import (
    BorrowingPolicy,
    BorrowingPolicyResolver,
)
from openlibrary.modules.core.domain.loans import BorrowerNotEligibleError
from openlibrary.modules.public_library.application import PublicLibraryStore
from openlibrary.modules.public_library.domain import MemberStatus, PlanStatus


def _system_now() -> datetime:
    return datetime.now(timezone.utc)


class PublicLibraryBorrowingPolicyAdapter(BorrowingPolicyResolver):
    """Resolves member borrowing policies from active public library subscriptions and configured plan data."""

    def __init__(
        self,
        store: PublicLibraryStore,
        fallback_resolver: BorrowingPolicyResolver | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._fallback = fallback_resolver
        self._clock = clock or _system_now

    def resolve_policy(
        self, organization_id: UUID, borrower_user_id: UUID
    ) -> BorrowingPolicy:
        """Resolve tenant-scoped policy rules and snapshot facts for a borrower."""
        # 1. Verify edition is enabled
        if not self._store.is_edition_enabled(organization_id):
            if self._fallback is not None:
                return self._fallback.resolve_policy(organization_id, borrower_user_id)
            raise BorrowerNotEligibleError(
                f"Public library edition is not enabled for organization {organization_id}"
            )

        # 2. Check for member profile
        member = self._store.get_member_by_user_id(organization_id, borrower_user_id)
        if member is None:
            if self._fallback is not None:
                return self._fallback.resolve_policy(organization_id, borrower_user_id)
            raise BorrowerNotEligibleError(
                f"User {borrower_user_id} has no active member profile in organization {organization_id}"
            )

        if member.status != MemberStatus.ACTIVE:
            raise BorrowerNotEligibleError(
                f"Member profile for user {borrower_user_id} is {member.status}"
            )

        # 3. Check for active subscription
        now = self._clock()
        subscription = self._store.get_active_subscription_for_member(
            organization_id, member.member_id, now
        )
        if subscription is None:
            raise BorrowerNotEligibleError(
                f"Member {member.member_id} does not have an active subscription"
            )

        # 4. Resolve plan
        plan = self._store.get_plan(organization_id, subscription.plan_id)
        if plan is None or plan.status != PlanStatus.ACTIVE:
            raise BorrowerNotEligibleError(
                f"Plan {subscription.plan_id} is not active for member {member.member_id}"
            )

        # 5. Build snapshot facts
        facts: dict[str, object] = {
            "borrower_type": "member",
            "source": "public_library",
            "member_id": str(member.member_id),
            "member_number": member.member_number,
            "plan_id": str(plan.plan_id),
            "plan_code": plan.code,
            "subscription_id": str(subscription.subscription_id),
            "max_active_loans": plan.max_active_loans,
            "duration_days": plan.duration_days,
            "starts_at": subscription.starts_at.isoformat(),
            "ends_at": subscription.ends_at.isoformat(),
        }

        return BorrowingPolicy(
            borrower_type="member",
            max_active_loans=plan.max_active_loans,
            duration_days=plan.duration_days,
            policy_snapshot=facts,
        )
