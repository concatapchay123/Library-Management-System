"""Domain entities, value types, and domain rules for public library edition."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import re
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


_CURRENCY_REGEX = re.compile(r"^[A-Z]{3}$")
_DECIMAL_PLACES = Decimal("0.0001")


@dataclass(frozen=True, slots=True)
class Money:
    """Immutable money value object with explicit currency and Decimal precision.

    Floating-point representations are strictly rejected.
    """

    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if isinstance(self.amount, float):
            raise TypeError(
                "Floating-point money amounts are rejected; use Decimal instead."
            )
        if not isinstance(self.amount, Decimal):
            raise InvalidMoneyError(
                f"Money amount must be Decimal, got {type(self.amount).__name__}"
            )
        if self.amount < Decimal("0.0000"):
            raise InvalidMoneyError(
                f"Money amount cannot be negative, got {self.amount}"
            )
        if not isinstance(self.currency, str) or not _CURRENCY_REGEX.match(
            self.currency
        ):
            raise InvalidMoneyError(
                f"Currency must be 3-character uppercase ISO code, got '{self.currency}'"
            )

    def __add__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise CurrencyMismatchError(
                f"Cannot add different currencies: {self.currency} and {other.currency}"
            )
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise CurrencyMismatchError(
                f"Cannot subtract different currencies: {self.currency} and {other.currency}"
            )
        diff = self.amount - other.amount
        if diff < Decimal("0.0000"):
            raise InvalidMoneyError(
                f"Resulting money amount cannot be negative: {diff}"
            )
        return Money(diff, self.currency)

    def __lt__(self, other: Money) -> bool:
        if not isinstance(other, Money) or self.currency != other.currency:
            raise CurrencyMismatchError(
                f"Cannot compare different currencies: {self.currency} and {getattr(other, 'currency', None)}"
            )
        return self.amount < other.amount

    def __le__(self, other: Money) -> bool:
        if not isinstance(other, Money) or self.currency != other.currency:
            raise CurrencyMismatchError(
                f"Cannot compare different currencies: {self.currency} and {getattr(other, 'currency', None)}"
            )
        return self.amount <= other.amount

    def __gt__(self, other: Money) -> bool:
        if not isinstance(other, Money) or self.currency != other.currency:
            raise CurrencyMismatchError(
                f"Cannot compare different currencies: {self.currency} and {getattr(other, 'currency', None)}"
            )
        return self.amount > other.amount

    def __ge__(self, other: Money) -> bool:
        if not isinstance(other, Money) or self.currency != other.currency:
            raise CurrencyMismatchError(
                f"Cannot compare different currencies: {self.currency} and {getattr(other, 'currency', None)}"
            )
        return self.amount >= other.amount


class FineStatus:
    """Allowed lifecycle states for assessed fines."""

    ASSESSED = "assessed"
    INVOICED = "invoiced"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    WAIVED = "waived"
    CANCELLED = "cancelled"

    ALL = {ASSESSED, INVOICED, PARTIALLY_PAID, PAID, WAIVED, CANCELLED}


class InvoiceStatus:
    """Allowed lifecycle states for public library invoices."""

    ISSUED = "issued"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    CANCELLED = "cancelled"
    VOID = "void"

    ALL = {ISSUED, PARTIALLY_PAID, PAID, CANCELLED, VOID}


class PaymentStatus:
    """Allowed states for payment records."""

    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"

    ALL = {PENDING, SUCCEEDED, FAILED, REFUNDED, PARTIALLY_REFUNDED}


class AllocationType:
    """Allowed allocation types."""

    PAYMENT = "payment"
    REFUND = "refund"
    CREDIT = "credit"

    ALL = {PAYMENT, REFUND, CREDIT}


# Domain Exceptions


class PublicLibraryError(Exception):
    """Base exception for all public library domain failures."""


class InvalidMoneyError(PublicLibraryError):
    """Raised when a money amount or currency is invalid."""


class CurrencyMismatchError(PublicLibraryError):
    """Raised when an operation is attempted across different currencies."""


class FineNotFoundError(PublicLibraryError):
    """Raised when a fine is not found."""


class InvoiceNotFoundError(PublicLibraryError):
    """Raised when an invoice is not found."""


class PaymentNotFoundError(PublicLibraryError):
    """Raised when a payment is not found."""


class AllocationNotFoundError(PublicLibraryError):
    """Raised when a payment allocation is not found."""


class InvoiceImmutableError(PublicLibraryError):
    """Raised when attempting to modify lines or totals of an already issued invoice."""


class OverAllocationError(PublicLibraryError):
    """Raised when an allocation exceeds the available unallocated fine or payment amount."""


class InvalidAllocationAmountError(PublicLibraryError):
    """Raised when an allocation amount is zero or negative."""


class FineAlreadyClosedError(PublicLibraryError):
    """Raised when attempting to operate on an already paid or waived fine."""


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


@dataclass(frozen=True, slots=True)
class Fine:
    """A financial penalty assessed against a library member."""

    fine_id: UUID
    organization_id: UUID
    member_id: UUID
    amount: Decimal
    currency: str
    status: str
    reason: str
    assessed_at: datetime
    created_at: datetime
    updated_at: datetime
    loan_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class InvoiceLine:
    """One immutable line item belonging to an issued invoice."""

    invoice_line_id: UUID
    organization_id: UUID
    invoice_id: UUID
    line_number: int
    description: str
    quantity: int
    unit_price: Decimal
    amount: Decimal
    created_at: datetime
    fine_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class Invoice:
    """An issued billing record with immutable lines and totals."""

    invoice_id: UUID
    organization_id: UUID
    member_id: UUID
    invoice_number: str
    subtotal: Decimal
    tax: Decimal
    total: Decimal
    currency: str
    status: str
    issued_at: datetime
    created_at: datetime
    updated_at: datetime
    lines: list[InvoiceLine]
    due_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Payment:
    """A financial payment transaction recorded for library charges."""

    payment_id: UUID
    organization_id: UUID
    member_id: UUID
    amount: Decimal
    currency: str
    provider: str
    status: str
    created_at: datetime
    updated_at: datetime
    provider_reference: str | None = None
    provider_event_id: str | None = None
    paid_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class PaymentAllocation:
    """An immutable allocation of a payment amount against an assessed fine and optional invoice."""

    allocation_id: UUID
    organization_id: UUID
    payment_id: UUID
    fine_id: UUID
    amount: Decimal
    allocation_type: str
    created_at: datetime
    invoice_id: UUID | None = None


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


def calculate_overdue_fine(
    *,
    due_at: datetime,
    effective_return_at: datetime,
    daily_rate: Decimal,
    currency: str,
    max_fine: Decimal | None = None,
) -> Money:
    """Calculate overdue fine using pure Decimal arithmetic."""
    if isinstance(daily_rate, float) or (
        max_fine is not None and isinstance(max_fine, float)
    ):
        raise TypeError(
            "Floating-point money amounts are rejected; use Decimal instead."
        )
    if effective_return_at <= due_at:
        return Money(Decimal("0.0000"), currency)
    delta_seconds = Decimal(str((effective_return_at - due_at).total_seconds()))
    seconds_in_day = Decimal("86400")
    overdue_days = int(delta_seconds / seconds_in_day)
    if delta_seconds % seconds_in_day > 0:
        overdue_days += 1
    overdue_days_dec = Decimal(str(overdue_days))
    raw_amount = (overdue_days_dec * daily_rate).quantize(Decimal("0.0001"))
    if max_fine is not None:
        capped_amount = min(raw_amount, max_fine.quantize(Decimal("0.0001")))
        return Money(capped_amount, currency)
    return Money(raw_amount, currency)
