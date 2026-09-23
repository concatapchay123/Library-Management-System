"""Domain entities, value types, and domain rules for public library edition."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID


class MemberStatus:
    """Allowed lifecycle states for public library members."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"

    ALL = {ACTIVE, INACTIVE, SUSPENDED}


class PlanStatus:
    """Allowed states for membership plans."""

    ACTIVE = "active"
    ARCHIVED = "archived"

    ALL = {ACTIVE, ARCHIVED}


class SubscriptionStatus:
    """Allowed lifecycle states for member subscriptions."""

    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    PENDING = "pending"

    ALL = {ACTIVE, EXPIRED, CANCELLED, PENDING}


# Domain Exceptions


class PublicLibraryError(Exception):
    """Base exception for all public library domain failures."""


class EditionUnavailableError(PublicLibraryError):
    """Raised when public library edition is not enabled for the tenant organization."""


class MemberNotFoundError(PublicLibraryError):
    """Raised when a public library member is not found."""


class MembershipPlanNotFoundError(PublicLibraryError):
    """Raised when a membership plan is not found."""


class SubscriptionNotFoundError(PublicLibraryError):
    """Raised when a subscription is not found."""


class DuplicateIdentifierError(PublicLibraryError):
    """Raised when a unique identifier or business code conflicts within the organization."""


class ProfileAlreadyExistsError(PublicLibraryError):
    """Raised when a user already has an active member profile in the organization."""


class InvalidSubscriptionDatesError(PublicLibraryError):
    """Raised when subscription start and end dates violate chronological constraints."""


class ActiveSubscriptionExistsError(PublicLibraryError):
    """Raised when creating a subscription for a member who already has an active subscription."""


class SubscriptionInactiveError(PublicLibraryError):
    """Raised when trying to use or operate on an inactive subscription."""


class InvalidPlanError(PublicLibraryError):
    """Raised when membership plan attributes are invalid."""


# Domain Entities


@dataclass(frozen=True, slots=True)
class Member:
    """A registered public library member in an organization."""

    member_id: UUID
    organization_id: UUID
    user_id: UUID
    member_number: str
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class MembershipPlan:
    """A configurable membership plan defining borrowing limits and checkout duration."""

    plan_id: UUID
    organization_id: UUID
    code: str
    name: str
    description: str | None
    max_active_loans: int
    duration_days: int
    price: Decimal
    currency: str
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Subscription:
    """A time-bound subscription linking a member to a membership plan."""

    subscription_id: UUID
    organization_id: UUID
    member_id: UUID
    plan_id: UUID
    starts_at: datetime
    ends_at: datetime
    status: str
    created_at: datetime
    updated_at: datetime


def validate_subscription_dates(starts_at: datetime, ends_at: datetime) -> None:
    """Ensure subscription ends_at is strictly after starts_at."""
    if starts_at >= ends_at:
        raise InvalidSubscriptionDatesError(
            f"Subscription ends_at ({ends_at.isoformat()}) must be after starts_at ({starts_at.isoformat()})"
        )


def validate_plan_limits(max_active_loans: int, duration_days: int) -> None:
    """Validate borrowing limits on a membership plan."""
    if max_active_loans <= 0:
        raise InvalidPlanError("max_active_loans must be greater than zero")
    if duration_days <= 0:
        raise InvalidPlanError("duration_days must be greater than zero")
