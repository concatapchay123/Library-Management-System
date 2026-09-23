"""Application services and persistence ports for public library edition."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from typing import Any, Protocol, TypeVar
from uuid import UUID, uuid4

from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.authorization import AuthorizationPort
from openlibrary.modules.ops.application.persistence import (
    AuditEvent,
    AuditedTransaction,
    OutboxEvent,
)
from openlibrary.modules.public_library.domain import (
    ActiveSubscriptionExistsError,
    AllocationNotFoundError,
    AllocationType,
    CurrencyMismatchError,
    DuplicateIdentifierError,
    DuplicateProviderReferenceError,
    EditionUnavailableError,
    Fine,
    FineAlreadyClosedError,
    FineNotFoundError,
    FineStatus,
    InvalidAllocationAmountError,
    InvalidMoneyError,
    InvalidPaymentStateTransitionError,
    InvalidPlanError,
    InvalidWebhookSignatureError,
    Invoice,
    InvoiceImmutableError,
    InvoiceLine,
    InvoiceNotFoundError,
    InvoiceStatus,
    Member,
    MemberNotFoundError,
    MemberStatus,
    MembershipPlan,
    MembershipPlanNotFoundError,
    Money,
    OverAllocationError,
    OverRefundError,
    Payment,
    PaymentAllocation,
    PaymentEvent,
    PaymentNotFoundError,
    PaymentStatus,
    PlanStatus,
    ProfileAlreadyExistsError,
    Subscription,
    SubscriptionInactiveError,
    SubscriptionNotFoundError,
    SubscriptionStatus,
    calculate_overdue_fine,
    validate_payment_transition,
    validate_plan_limits,
    validate_subscription_dates,
)
from openlibrary.modules.public_library.webhooks import (
    PaymentProviderPort,
    WebhookSignatureVerifier,
)

T = TypeVar("T")

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

    # --- Fines ---

    def create_fine(self, fine: Fine) -> Fine: ...

    def get_fine(self, organization_id: UUID, fine_id: UUID) -> Fine | None: ...

    def list_fines(
        self,
        organization_id: UUID,
        *,
        member_id: UUID | None = None,
        loan_id: UUID | None = None,
        status: str | None = None,
    ) -> list[Fine]: ...

    def update_fine(self, fine: Fine) -> Fine: ...

    # --- Invoices ---

    def create_invoice(self, invoice: Invoice, lines: list[InvoiceLine]) -> Invoice: ...

    def get_invoice(
        self, organization_id: UUID, invoice_id: UUID
    ) -> Invoice | None: ...

    def list_invoices(
        self,
        organization_id: UUID,
        *,
        member_id: UUID | None = None,
        status: str | None = None,
    ) -> list[Invoice]: ...

    def update_invoice(self, invoice: Invoice) -> Invoice: ...

    # --- Payments ---

    def create_payment(self, payment: Payment) -> Payment: ...

    def get_payment(
        self, organization_id: UUID, payment_id: UUID
    ) -> Payment | None: ...

    def get_payment_by_provider_reference(
        self,
        organization_id: UUID,
        provider: str,
        provider_reference: str,
    ) -> Payment | None: ...

    def list_payments(
        self,
        organization_id: UUID,
        *,
        member_id: UUID | None = None,
        status: str | None = None,
    ) -> list[Payment]: ...

    def update_payment(self, payment: Payment) -> Payment: ...

    def update_payment_status(
        self,
        organization_id: UUID,
        payment_id: UUID,
        status: str,
        updated_at: datetime,
        *,
        paid_at: datetime | None = None,
        provider_event_id: str | None = None,
    ) -> Payment: ...

    def record_payment_event(self, event: PaymentEvent) -> PaymentEvent: ...

    def get_payment_event(
        self,
        organization_id: UUID,
        provider: str,
        provider_event_id: str,
    ) -> PaymentEvent | None: ...

    # --- Allocations ---

    def create_allocation(self, allocation: PaymentAllocation) -> PaymentAllocation: ...

    def get_allocation(
        self, organization_id: UUID, allocation_id: UUID
    ) -> PaymentAllocation | None: ...

    def list_allocations_for_fine(
        self, organization_id: UUID, fine_id: UUID
    ) -> list[PaymentAllocation]: ...

    def list_allocations_for_payment(
        self, organization_id: UUID, payment_id: UUID
    ) -> list[PaymentAllocation]: ...


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


class PublicLibraryFinanceService:
    """Application use cases for assessing fines, issuing immutable invoices, and allocating payments."""

    def __init__(
        self,
        store: PublicLibraryStore,
        authorizer: AuthorizationPort,
        transaction: AuditedTransaction | None = None,
        connection_provider: Callable[[UUID], AbstractContextManager[Any]]
        | None = None,
        clock: Callable[[], datetime] | None = None,
        payment_provider: PaymentProviderPort | None = None,
        webhook_verifier: WebhookSignatureVerifier | None = None,
    ) -> None:
        self._store = store
        self._authorizer = authorizer
        self._transaction = transaction
        self._connection_provider = connection_provider
        self._clock = clock or _system_now
        self._payment_provider = payment_provider
        self._webhook_verifier = webhook_verifier or WebhookSignatureVerifier()

    def _ensure_edition_enabled(self, organization_id: UUID) -> None:
        if not self._store.is_edition_enabled(organization_id):
            raise EditionUnavailableError(
                f"Public library edition is not enabled for organization {organization_id}"
            )

    def _execute_transaction(
        self,
        organization_id: UUID,
        mutation: Callable[[Any], T],
        audit_event: AuditEvent,
        outbox_event: OutboxEvent,
    ) -> T:
        if self._transaction is not None:
            if self._connection_provider is not None:
                with self._connection_provider(organization_id) as conn:
                    return self._transaction.run(
                        conn,
                        mutation,
                        audit_event,
                        (outbox_event,),
                    )
            return self._transaction.run(
                None,  # type: ignore[arg-type]
                mutation,
                audit_event,
                (outbox_event,),
            )
        return mutation(None)

    # --- Fines ---

    def assess_fine(
        self,
        *,
        actor: Principal,
        member_id: UUID,
        amount: Decimal,
        currency: str,
        reason: str,
        loan_id: UUID | None = None,
        correlation_id: UUID | None = None,
    ) -> Fine:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "public_library.manage")

        member = self._store.get_member(actor.organization_id, member_id)
        if member is None:
            raise MemberNotFoundError(
                f"Member {member_id} not found in organization {actor.organization_id}"
            )

        money = Money(amount, currency)
        now = self._clock()
        fine_id = uuid4()
        fine = Fine(
            fine_id=fine_id,
            organization_id=actor.organization_id,
            member_id=member_id,
            amount=money.amount,
            currency=money.currency,
            status=FineStatus.ASSESSED,
            reason=reason,
            assessed_at=now,
            created_at=now,
            updated_at=now,
            loan_id=loan_id,
        )

        audit_corr = correlation_id or uuid4()
        audit_event = AuditEvent(
            action="fine.assessed",
            entity_type="fine",
            entity_id=fine_id,
            payload={
                "fine_id": str(fine_id),
                "organization_id": str(actor.organization_id),
                "member_id": str(member_id),
                "loan_id": str(loan_id) if loan_id else None,
                "amount": str(money.amount),
                "currency": money.currency,
                "reason": reason,
                "status": FineStatus.ASSESSED,
            },
            correlation_id=audit_corr,
            actor_user_id=actor.user_id,
            actor_type="user",
        )
        outbox_event = OutboxEvent(
            event_type="public_library.fine_assessed",
            aggregate_type="fine",
            aggregate_id=fine_id,
            payload_version=1,
            payload={
                "fine_id": str(fine_id),
                "organization_id": str(actor.organization_id),
                "member_id": str(member_id),
                "loan_id": str(loan_id) if loan_id else None,
                "amount": str(money.amount),
                "currency": money.currency,
                "reason": reason,
            },
            correlation_id=audit_corr,
            idempotency_key=f"fine:{fine_id}:assessed",
        )

        return self._execute_transaction(
            actor.organization_id,
            lambda conn: self._store.create_fine(fine),
            audit_event,
            outbox_event,
        )

    def get_fine(self, *, actor: Principal, fine_id: UUID) -> Fine:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "public_library.read")
        fine = self._store.get_fine(actor.organization_id, fine_id)
        if fine is None:
            raise FineNotFoundError(
                f"Fine {fine_id} not found in organization {actor.organization_id}"
            )
        return fine

    def list_fines(
        self,
        *,
        actor: Principal,
        member_id: UUID | None = None,
        loan_id: UUID | None = None,
        status: str | None = None,
    ) -> list[Fine]:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "public_library.read")
        return self._store.list_fines(
            actor.organization_id,
            member_id=member_id,
            loan_id=loan_id,
            status=status,
        )

    def calculate_overdue_fine(
        self,
        *,
        due_at: datetime,
        effective_return_at: datetime,
        daily_rate: Decimal,
        currency: str,
        max_fine: Decimal | None = None,
    ) -> Money:
        return calculate_overdue_fine(
            due_at=due_at,
            effective_return_at=effective_return_at,
            daily_rate=daily_rate,
            currency=currency,
            max_fine=max_fine,
        )

    def waive_fine(
        self,
        *,
        actor: Principal,
        fine_id: UUID,
        reason: str,
        correlation_id: UUID | None = None,
    ) -> Fine:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "public_library.manage")
        fine = self.get_fine(actor=actor, fine_id=fine_id)
        if fine.status in (FineStatus.PAID, FineStatus.WAIVED, FineStatus.CANCELLED):
            raise FineAlreadyClosedError(
                f"Fine {fine_id} is in status '{fine.status}' and cannot be waived"
            )

        now = self._clock()
        updated = Fine(
            fine_id=fine.fine_id,
            organization_id=fine.organization_id,
            member_id=fine.member_id,
            amount=fine.amount,
            currency=fine.currency,
            status=FineStatus.WAIVED,
            reason=f"{fine.reason} | Waived: {reason}",
            assessed_at=fine.assessed_at,
            created_at=fine.created_at,
            updated_at=now,
            loan_id=fine.loan_id,
        )

        audit_corr = correlation_id or uuid4()
        audit_event = AuditEvent(
            action="fine.waived",
            entity_type="fine",
            entity_id=fine_id,
            payload={
                "fine_id": str(fine_id),
                "organization_id": str(actor.organization_id),
                "reason": reason,
                "status": FineStatus.WAIVED,
            },
            correlation_id=audit_corr,
            actor_user_id=actor.user_id,
            actor_type="user",
        )
        outbox_event = OutboxEvent(
            event_type="public_library.fine_waived",
            aggregate_type="fine",
            aggregate_id=fine_id,
            payload_version=1,
            payload={
                "fine_id": str(fine_id),
                "organization_id": str(actor.organization_id),
                "reason": reason,
            },
            correlation_id=audit_corr,
            idempotency_key=f"fine:{fine_id}:waived",
        )

        return self._execute_transaction(
            actor.organization_id,
            lambda conn: self._store.update_fine(updated),
            audit_event,
            outbox_event,
        )

    # --- Invoices ---

    def issue_invoice(
        self,
        *,
        actor: Principal,
        member_id: UUID,
        lines: list[InvoiceLine],
        currency: str,
        tax: Decimal | None = None,
        due_at: datetime | None = None,
        correlation_id: UUID | None = None,
    ) -> Invoice:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "public_library.manage")

        member = self._store.get_member(actor.organization_id, member_id)
        if member is None:
            raise MemberNotFoundError(
                f"Member {member_id} not found in organization {actor.organization_id}"
            )

        if not lines:
            raise ValueError("An invoice must contain at least one line item.")

        effective_tax = tax if tax is not None else Decimal("0.0000")
        if isinstance(effective_tax, float):
            raise TypeError(
                "Floating-point tax amounts are rejected; use Decimal instead."
            )
        if effective_tax < Decimal("0.0000"):
            raise InvalidMoneyError("Tax amount cannot be negative.")

        # Validate line items and compute subtotal
        subtotal = Decimal("0.0000")
        validated_lines: list[InvoiceLine] = []
        inv_id = uuid4()
        now = self._clock()

        for idx, line in enumerate(lines, start=1):
            if isinstance(line.unit_price, float) or isinstance(line.amount, float):
                raise TypeError(
                    "Floating-point line amounts are rejected; use Decimal instead."
                )
            if line.quantity <= 0:
                raise ValueError("Line quantity must be greater than zero.")
            expected_amount = line.quantity * line.unit_price
            if line.amount != expected_amount:
                raise ValueError(
                    f"Line {idx} amount ({line.amount}) does not match quantity * unit_price ({expected_amount})"
                )
            subtotal += line.amount
            validated_lines.append(
                InvoiceLine(
                    invoice_line_id=uuid4(),
                    organization_id=actor.organization_id,
                    invoice_id=inv_id,
                    line_number=idx,
                    description=line.description,
                    quantity=line.quantity,
                    unit_price=line.unit_price,
                    amount=line.amount,
                    created_at=now,
                    fine_id=line.fine_id,
                )
            )

        total = subtotal + effective_tax
        invoice_number = f"INV-{now.strftime('%Y%m%d')}-{str(inv_id)[:8].upper()}"

        invoice = Invoice(
            invoice_id=inv_id,
            organization_id=actor.organization_id,
            member_id=member_id,
            invoice_number=invoice_number,
            subtotal=subtotal,
            tax=effective_tax,
            total=total,
            currency=currency,
            status=InvoiceStatus.ISSUED,
            issued_at=now,
            created_at=now,
            updated_at=now,
            lines=validated_lines,
            due_at=due_at,
        )

        audit_corr = correlation_id or uuid4()
        audit_event = AuditEvent(
            action="invoice.issued",
            entity_type="invoice",
            entity_id=inv_id,
            payload={
                "invoice_id": str(inv_id),
                "organization_id": str(actor.organization_id),
                "member_id": str(member_id),
                "invoice_number": invoice_number,
                "subtotal": str(subtotal),
                "tax": str(effective_tax),
                "total": str(total),
                "currency": currency,
                "lines_count": len(validated_lines),
                "status": InvoiceStatus.ISSUED,
            },
            correlation_id=audit_corr,
            actor_user_id=actor.user_id,
            actor_type="user",
        )
        outbox_event = OutboxEvent(
            event_type="public_library.invoice_issued",
            aggregate_type="invoice",
            aggregate_id=inv_id,
            payload_version=1,
            payload={
                "invoice_id": str(inv_id),
                "organization_id": str(actor.organization_id),
                "member_id": str(member_id),
                "invoice_number": invoice_number,
                "total": str(total),
                "currency": currency,
            },
            correlation_id=audit_corr,
            idempotency_key=f"invoice:{inv_id}:issued",
        )

        def _mutation(conn: Any) -> Invoice:
            # If any line links to a fine, mark fine as invoiced
            for line in validated_lines:
                if line.fine_id is not None:
                    fine = self._store.get_fine(actor.organization_id, line.fine_id)
                    if fine is not None and fine.status == FineStatus.ASSESSED:
                        updated_fine = Fine(
                            fine_id=fine.fine_id,
                            organization_id=fine.organization_id,
                            member_id=fine.member_id,
                            amount=fine.amount,
                            currency=fine.currency,
                            status=FineStatus.INVOICED,
                            reason=fine.reason,
                            assessed_at=fine.assessed_at,
                            created_at=fine.created_at,
                            updated_at=now,
                            loan_id=fine.loan_id,
                        )
                        self._store.update_fine(updated_fine)
            return self._store.create_invoice(invoice, validated_lines)

        return self._execute_transaction(
            actor.organization_id,
            _mutation,
            audit_event,
            outbox_event,
        )

    def get_invoice(self, *, actor: Principal, invoice_id: UUID) -> Invoice:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "public_library.read")
        invoice = self._store.get_invoice(actor.organization_id, invoice_id)
        if invoice is None:
            raise InvoiceNotFoundError(
                f"Invoice {invoice_id} not found in organization {actor.organization_id}"
            )
        return invoice

    def list_invoices(
        self,
        *,
        actor: Principal,
        member_id: UUID | None = None,
        status: str | None = None,
    ) -> list[Invoice]:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "public_library.read")
        return self._store.list_invoices(
            actor.organization_id,
            member_id=member_id,
            status=status,
        )

    def modify_invoice_lines(
        self,
        *,
        actor: Principal,
        invoice_id: UUID,
        new_lines: list[InvoiceLine],
    ) -> Invoice:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "public_library.manage")
        raise InvoiceImmutableError(
            f"Issued invoice {invoice_id} is immutable; lines and totals cannot be changed."
        )

    def update_invoice_total(
        self,
        *,
        actor: Principal,
        invoice_id: UUID,
        new_total: Decimal,
    ) -> Invoice:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "public_library.manage")
        raise InvoiceImmutableError(
            f"Issued invoice {invoice_id} is immutable; totals cannot be changed."
        )

    def void_invoice(
        self,
        *,
        actor: Principal,
        invoice_id: UUID,
        reason: str,
        correlation_id: UUID | None = None,
    ) -> Invoice:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "public_library.manage")
        invoice = self.get_invoice(actor=actor, invoice_id=invoice_id)
        if invoice.status in (
            InvoiceStatus.PAID,
            InvoiceStatus.VOID,
            InvoiceStatus.CANCELLED,
        ):
            raise InvoiceImmutableError(
                f"Invoice {invoice_id} is in status '{invoice.status}' and cannot be voided"
            )

        now = self._clock()
        updated = Invoice(
            invoice_id=invoice.invoice_id,
            organization_id=invoice.organization_id,
            member_id=invoice.member_id,
            invoice_number=invoice.invoice_number,
            subtotal=invoice.subtotal,
            tax=invoice.tax,
            total=invoice.total,
            currency=invoice.currency,
            status=InvoiceStatus.VOID,
            issued_at=invoice.issued_at,
            created_at=invoice.created_at,
            updated_at=now,
            lines=invoice.lines,
            due_at=invoice.due_at,
        )

        audit_corr = correlation_id or uuid4()
        audit_event = AuditEvent(
            action="invoice.voided",
            entity_type="invoice",
            entity_id=invoice_id,
            payload={
                "invoice_id": str(invoice_id),
                "organization_id": str(actor.organization_id),
                "reason": reason,
                "status": InvoiceStatus.VOID,
            },
            correlation_id=audit_corr,
            actor_user_id=actor.user_id,
            actor_type="user",
        )
        outbox_event = OutboxEvent(
            event_type="public_library.invoice_voided",
            aggregate_type="invoice",
            aggregate_id=invoice_id,
            payload_version=1,
            payload={
                "invoice_id": str(invoice_id),
                "organization_id": str(actor.organization_id),
                "reason": reason,
            },
            correlation_id=audit_corr,
            idempotency_key=f"invoice:{invoice_id}:voided",
        )

        return self._execute_transaction(
            actor.organization_id,
            lambda conn: self._store.update_invoice(updated),
            audit_event,
            outbox_event,
        )

    # --- Payments ---

    def record_payment(
        self,
        *,
        actor: Principal,
        member_id: UUID,
        amount: Decimal,
        currency: str,
        provider: str = "manual",
        provider_reference: str | None = None,
        provider_event_id: str | None = None,
        initial_status: str = PaymentStatus.SUCCEEDED,
        correlation_id: UUID | None = None,
    ) -> Payment:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "public_library.manage")

        if initial_status not in PaymentStatus.ALL:
            raise InvalidPaymentStateTransitionError(
                f"Invalid payment status: {initial_status}"
            )

        if provider_reference is not None:
            existing_ref = self._store.get_payment_by_provider_reference(
                actor.organization_id, provider, provider_reference
            )
            if existing_ref is not None:
                raise DuplicateProviderReferenceError(
                    f"Payment with provider '{provider}' and reference '{provider_reference}' already exists for organization {actor.organization_id}"
                )

        member = self._store.get_member(actor.organization_id, member_id)
        if member is None:
            raise MemberNotFoundError(
                f"Member {member_id} not found in organization {actor.organization_id}"
            )

        money = Money(amount, currency)
        now = self._clock()
        pay_id = uuid4()
        paid_at = now if initial_status == PaymentStatus.SUCCEEDED else None
        payment = Payment(
            payment_id=pay_id,
            organization_id=actor.organization_id,
            member_id=member_id,
            amount=money.amount,
            currency=money.currency,
            provider=provider,
            status=initial_status,
            created_at=now,
            updated_at=now,
            provider_reference=provider_reference,
            provider_event_id=provider_event_id,
            paid_at=paid_at,
        )

        audit_corr = correlation_id or uuid4()
        audit_event = AuditEvent(
            action="payment.recorded",
            entity_type="payment",
            entity_id=pay_id,
            payload={
                "payment_id": str(pay_id),
                "organization_id": str(actor.organization_id),
                "member_id": str(member_id),
                "amount": str(money.amount),
                "currency": money.currency,
                "provider": provider,
                "status": initial_status,
            },
            correlation_id=audit_corr,
            actor_user_id=actor.user_id,
            actor_type="user",
        )
        outbox_event = OutboxEvent(
            event_type="public_library.payment_recorded",
            aggregate_type="payment",
            aggregate_id=pay_id,
            payload_version=1,
            payload={
                "payment_id": str(pay_id),
                "organization_id": str(actor.organization_id),
                "member_id": str(member_id),
                "amount": str(money.amount),
                "currency": money.currency,
                "provider": provider,
                "status": initial_status,
            },
            correlation_id=audit_corr,
            idempotency_key=f"payment:{pay_id}:recorded",
        )

        return self._execute_transaction(
            actor.organization_id,
            lambda conn: self._store.create_payment(payment),
            audit_event,
            outbox_event,
        )

    def transition_payment_status(
        self,
        *,
        actor: Principal,
        payment_id: UUID,
        new_status: str,
        provider_event_id: str | None = None,
        correlation_id: UUID | None = None,
    ) -> Payment:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "public_library.manage")

        payment = self.get_payment(actor=actor, payment_id=payment_id)
        if payment.status == new_status:
            return payment

        validate_payment_transition(payment.status, new_status)
        now = self._clock()
        paid_at = payment.paid_at
        if new_status == PaymentStatus.SUCCEEDED and paid_at is None:
            paid_at = now

        audit_corr = correlation_id or uuid4()
        audit_event = AuditEvent(
            action="payment.status_changed",
            entity_type="payment",
            entity_id=payment_id,
            payload={
                "payment_id": str(payment_id),
                "organization_id": str(actor.organization_id),
                "previous_status": payment.status,
                "new_status": new_status,
            },
            correlation_id=audit_corr,
            actor_user_id=actor.user_id,
            actor_type="user",
        )
        outbox_event = OutboxEvent(
            event_type="public_library.payment_status_changed",
            aggregate_type="payment",
            aggregate_id=payment_id,
            payload_version=1,
            payload={
                "payment_id": str(payment_id),
                "organization_id": str(actor.organization_id),
                "previous_status": payment.status,
                "new_status": new_status,
            },
            correlation_id=audit_corr,
            idempotency_key=f"payment:{payment_id}:status:{new_status}",
        )

        return self._execute_transaction(
            actor.organization_id,
            lambda conn: self._store.update_payment_status(
                actor.organization_id,
                payment_id,
                new_status,
                now,
                paid_at=paid_at,
                provider_event_id=provider_event_id,
            ),
            audit_event,
            outbox_event,
        )

    def handle_payment_webhook(
        self,
        *,
        organization_id: UUID,
        provider: str,
        raw_body: bytes,
        headers: Mapping[str, str],
        secret: str | None = None,
        correlation_id: UUID | None = None,
    ) -> Payment:
        """Verify provider signature on raw body, deduplicate events, and update payment state."""
        self._ensure_edition_enabled(organization_id)

        if secret is None:
            if self._payment_provider is not None:
                if hasattr(self._payment_provider, "get_webhook_secret"):
                    secret = self._payment_provider.get_webhook_secret(
                        organization_id=organization_id, provider=provider
                    )
                elif hasattr(self._payment_provider, "secret"):
                    secret = getattr(self._payment_provider, "secret")
            if not secret:
                import os

                secret = os.environ.get(
                    f"PAYMENT_WEBHOOK_SECRET_{provider.upper()}",
                    os.environ.get("PAYMENT_WEBHOOK_SECRET", ""),
                )
            if not secret:
                raise InvalidWebhookSignatureError(
                    f"No webhook secret configured for payment provider '{provider}'"
                )

        # 1. Verify signature on raw request body BEFORE payload parsing
        self._webhook_verifier.verify(
            provider=provider,
            raw_body=raw_body,
            headers=headers,
            secret=secret,
            current_time=self._clock(),
        )

        # 2. Parse payload ONLY after signature verification succeeds
        try:
            body = json.loads(raw_body.decode("utf-8"))
        except Exception as exc:
            raise ValueError("Malformed JSON payload in webhook body") from exc

        if not isinstance(body, dict):
            raise ValueError("Webhook body must be a JSON object")

        event_id = str(body.get("event_id") or body.get("id") or "").strip()
        if not event_id:
            raise ValueError("Webhook payload missing event identifier")

        event_type = str(
            body.get("event_type") or body.get("type") or "payment.succeeded"
        ).strip()
        data_raw = body.get("data")
        data: dict[str, Any] = data_raw if isinstance(data_raw, dict) else body
        provider_ref = (
            str(data.get("provider_reference") or data.get("id") or "").strip() or None
        )

        # 3. Check duplicate provider event: (organization_id, provider, provider_event_id)
        existing_event = self._store.get_payment_event(
            organization_id, provider, event_id
        )
        if existing_event is not None:
            if existing_event.payment_id is not None:
                existing_payment = self._store.get_payment(
                    organization_id, existing_event.payment_id
                )
                if existing_payment is not None:
                    return existing_payment
            if provider_ref is not None:
                existing_payment = self._store.get_payment_by_provider_reference(
                    organization_id, provider, provider_ref
                )
                if existing_payment is not None:
                    return existing_payment

        now = self._clock()
        payload_hash = hashlib.sha256(raw_body).hexdigest()

        # 4. Map event_type to target payment status
        if event_type in (
            "payment.succeeded",
            "charge.succeeded",
            "payment_intent.succeeded",
        ):
            target_status = PaymentStatus.SUCCEEDED
        elif event_type in (
            "payment.failed",
            "charge.failed",
            "payment_intent.payment_failed",
        ):
            target_status = PaymentStatus.FAILED
        elif event_type in ("payment.refunded", "charge.refunded"):
            target_status = PaymentStatus.REFUNDED
        elif event_type in ("payment.disputed", "charge.dispute.created"):
            target_status = PaymentStatus.DISPUTED
        elif event_type in (
            "payment.authorized",
            "payment_intent.amount_capturable_updated",
        ):
            target_status = PaymentStatus.AUTHORIZED
        else:
            target_status = PaymentStatus.PENDING

        # 5. Resolve target payment
        target_payment: Payment | None = None
        if provider_ref:
            target_payment = self._store.get_payment_by_provider_reference(
                organization_id, provider, provider_ref
            )

        paid_at = now if target_status == PaymentStatus.SUCCEEDED else None

        if target_payment is not None:
            if target_status != target_payment.status:
                validate_payment_transition(target_payment.status, target_status)
                if target_payment.paid_at is not None:
                    paid_at = target_payment.paid_at

                target_payment = self._store.update_payment_status(
                    organization_id,
                    target_payment.payment_id,
                    target_status,
                    now,
                    paid_at=paid_at,
                    provider_event_id=event_id,
                )
        else:
            raw_member_id = data.get("member_id")
            if not raw_member_id:
                raise PaymentNotFoundError(
                    f"No existing payment found for provider reference '{provider_ref}' and member_id not provided"
                )
            amount_val = Decimal(str(data.get("amount", "0")))
            currency_val = str(data.get("currency", "USD"))
            money = Money(amount_val, currency_val)
            pay_id = uuid4()
            created_payment = Payment(
                payment_id=pay_id,
                organization_id=organization_id,
                member_id=UUID(str(raw_member_id)),
                amount=money.amount,
                currency=money.currency,
                provider=provider,
                status=target_status,
                created_at=now,
                updated_at=now,
                provider_reference=provider_ref,
                provider_event_id=event_id,
                paid_at=paid_at,
            )
            target_payment = self._store.create_payment(created_payment)

        # 6. Record PaymentEvent for deduplication
        event_record = PaymentEvent(
            event_id=uuid4(),
            organization_id=organization_id,
            provider=provider,
            provider_event_id=event_id,
            event_type=event_type,
            payload_hash=payload_hash,
            status="processed",
            created_at=now,
            payment_id=target_payment.payment_id,
        )
        self._store.record_payment_event(event_record)

        # 7. Audit & Outbox: sanitized fields only! NEVER raw body, secrets, card data
        audit_corr = correlation_id or uuid4()
        audit_event = AuditEvent(
            action="payment.webhook_processed",
            entity_type="payment",
            entity_id=target_payment.payment_id,
            payload={
                "payment_id": str(target_payment.payment_id),
                "organization_id": str(organization_id),
                "provider": provider,
                "provider_event_id": event_id,
                "event_type": event_type,
                "status": target_payment.status,
                "amount": str(target_payment.amount),
                "currency": target_payment.currency,
            },
            correlation_id=audit_corr,
            actor_type="system",
        )
        outbox_event = OutboxEvent(
            event_type="public_library.payment_webhook_processed",
            aggregate_type="payment",
            aggregate_id=target_payment.payment_id,
            payload_version=1,
            payload={
                "payment_id": str(target_payment.payment_id),
                "organization_id": str(organization_id),
                "provider": provider,
                "provider_event_id": event_id,
                "event_type": event_type,
                "status": target_payment.status,
            },
            correlation_id=audit_corr,
            idempotency_key=f"payment_event:{organization_id}:{provider}:{event_id}",
        )

        return self._execute_transaction(
            organization_id,
            lambda conn: target_payment,
            audit_event,
            outbox_event,
        )

    def reconcile_pending_payment(
        self,
        *,
        organization_id: UUID,
        payment_id: UUID,
        correlation_id: UUID | None = None,
    ) -> Payment:
        """Query provider out-of-band to reconcile pending payment without failing on timeout."""
        self._ensure_edition_enabled(organization_id)
        payment = self._store.get_payment(organization_id, payment_id)
        if payment is None:
            raise PaymentNotFoundError(
                f"Payment {payment_id} not found in organization {organization_id}"
            )

        if payment.status != PaymentStatus.PENDING:
            return payment

        if payment.provider_reference is None or self._payment_provider is None:
            return payment

        try:
            status_res = self._payment_provider.get_payment_status(
                provider=payment.provider,
                provider_reference=payment.provider_reference,
            )
        except Exception:
            # Remote timeout or error: payment remains pending
            return payment

        if status_res.status == PaymentStatus.PENDING:
            # Provider indicates still pending: remain pending
            return payment

        now = self._clock()
        paid_at = status_res.paid_at or (
            now if status_res.status == PaymentStatus.SUCCEEDED else None
        )

        validate_payment_transition(payment.status, status_res.status)

        audit_corr = correlation_id or uuid4()
        audit_event = AuditEvent(
            action="payment.reconciled",
            entity_type="payment",
            entity_id=payment_id,
            payload={
                "payment_id": str(payment_id),
                "organization_id": str(organization_id),
                "provider": payment.provider,
                "provider_reference": payment.provider_reference,
                "status": status_res.status,
            },
            correlation_id=audit_corr,
            actor_type="system",
        )
        outbox_event = OutboxEvent(
            event_type="public_library.payment_reconciled",
            aggregate_type="payment",
            aggregate_id=payment_id,
            payload_version=1,
            payload={
                "payment_id": str(payment_id),
                "organization_id": str(organization_id),
                "provider": payment.provider,
                "provider_reference": payment.provider_reference,
                "status": status_res.status,
            },
            correlation_id=audit_corr,
            idempotency_key=f"payment:{payment_id}:reconciled:{status_res.status}",
        )

        return self._execute_transaction(
            organization_id,
            lambda conn: self._store.update_payment_status(
                organization_id,
                payment_id,
                status_res.status,
                now,
                paid_at=paid_at,
            ),
            audit_event,
            outbox_event,
        )

    def get_payment(self, *, actor: Principal, payment_id: UUID) -> Payment:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "public_library.read")
        payment = self._store.get_payment(actor.organization_id, payment_id)
        if payment is None:
            raise PaymentNotFoundError(
                f"Payment {payment_id} not found in organization {actor.organization_id}"
            )
        return payment

    def list_payments(
        self,
        *,
        actor: Principal,
        member_id: UUID | None = None,
        status: str | None = None,
    ) -> list[Payment]:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "public_library.read")
        return self._store.list_payments(
            actor.organization_id,
            member_id=member_id,
            status=status,
        )

    # --- Allocations ---

    def allocate_payment(
        self,
        *,
        actor: Principal,
        payment_id: UUID,
        fine_id: UUID,
        amount: Decimal,
        invoice_id: UUID | None = None,
        allocation_type: str = AllocationType.PAYMENT,
        correlation_id: UUID | None = None,
    ) -> PaymentAllocation:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "public_library.manage")

        if isinstance(amount, float):
            raise TypeError(
                "Floating-point money amounts are rejected; use Decimal instead."
            )
        if not isinstance(amount, Decimal):
            raise InvalidMoneyError(
                f"Allocation amount must be Decimal, got {type(amount).__name__}"
            )
        if amount <= Decimal("0.0000"):
            raise InvalidAllocationAmountError(
                f"Allocation amount must be strictly positive, got {amount}"
            )

        payment = self.get_payment(actor=actor, payment_id=payment_id)
        fine = self.get_fine(actor=actor, fine_id=fine_id)

        if payment.currency != fine.currency:
            raise CurrencyMismatchError(
                f"Payment currency '{payment.currency}' does not match fine currency '{fine.currency}'"
            )

        if fine.status in (FineStatus.PAID, FineStatus.WAIVED, FineStatus.CANCELLED):
            raise OverAllocationError(
                f"Fine {fine_id} is already fully paid or closed in status '{fine.status}' and cannot receive allocations"
            )

        # 1. Enforce fine allocation cap
        existing_fine_allocs = self._store.list_allocations_for_fine(
            actor.organization_id, fine_id
        )
        current_fine_allocated = sum(
            (a.amount for a in existing_fine_allocs), Decimal("0.0000")
        )
        remaining_fine = fine.amount - current_fine_allocated
        if current_fine_allocated + amount > fine.amount:
            raise OverAllocationError(
                f"Allocation of {amount} {fine.currency} exceeds remaining fine unallocated balance of {remaining_fine} {fine.currency}"
            )

        # 2. Enforce payment allocation cap
        existing_pay_allocs = self._store.list_allocations_for_payment(
            actor.organization_id, payment_id
        )
        current_pay_allocated = sum(
            (a.amount for a in existing_pay_allocs), Decimal("0.0000")
        )
        remaining_pay = payment.amount - current_pay_allocated
        if current_pay_allocated + amount > payment.amount:
            raise OverAllocationError(
                f"Allocation of {amount} {payment.currency} exceeds remaining payment unallocated balance of {remaining_pay} {payment.currency}"
            )

        alloc_id = uuid4()
        now = self._clock()
        allocation = PaymentAllocation(
            allocation_id=alloc_id,
            organization_id=actor.organization_id,
            payment_id=payment_id,
            fine_id=fine_id,
            amount=amount,
            allocation_type=allocation_type,
            created_at=now,
            invoice_id=invoice_id,
        )

        # New fine status
        new_fine_allocated = current_fine_allocated + amount
        new_fine_status = (
            FineStatus.PAID
            if new_fine_allocated == fine.amount
            else FineStatus.PARTIALLY_PAID
        )
        updated_fine = Fine(
            fine_id=fine.fine_id,
            organization_id=fine.organization_id,
            member_id=fine.member_id,
            amount=fine.amount,
            currency=fine.currency,
            status=new_fine_status,
            reason=fine.reason,
            assessed_at=fine.assessed_at,
            created_at=fine.created_at,
            updated_at=now,
            loan_id=fine.loan_id,
        )

        audit_corr = correlation_id or uuid4()
        audit_event = AuditEvent(
            action="payment.allocated",
            entity_type="payment_allocation",
            entity_id=alloc_id,
            payload={
                "allocation_id": str(alloc_id),
                "organization_id": str(actor.organization_id),
                "payment_id": str(payment_id),
                "fine_id": str(fine_id),
                "invoice_id": str(invoice_id) if invoice_id else None,
                "amount": str(amount),
                "allocation_type": allocation_type,
                "fine_status_after": new_fine_status,
            },
            correlation_id=audit_corr,
            actor_user_id=actor.user_id,
            actor_type="user",
        )
        outbox_event = OutboxEvent(
            event_type="public_library.payment_allocated",
            aggregate_type="payment_allocation",
            aggregate_id=alloc_id,
            payload_version=1,
            payload={
                "allocation_id": str(alloc_id),
                "organization_id": str(actor.organization_id),
                "payment_id": str(payment_id),
                "fine_id": str(fine_id),
                "amount": str(amount),
            },
            correlation_id=audit_corr,
            idempotency_key=f"allocation:{alloc_id}:created",
        )

        def _mutation(conn: Any) -> PaymentAllocation:
            self._store.update_fine(updated_fine)
            created_alloc = self._store.create_allocation(allocation)
            if invoice_id is not None:
                inv = self._store.get_invoice(actor.organization_id, invoice_id)
                if inv is not None:
                    # Check if all fines linked to this invoice lines are fully paid
                    all_paid = True
                    for line in inv.lines:
                        if line.fine_id is not None:
                            f = self._store.get_fine(
                                actor.organization_id, line.fine_id
                            )
                            if f is None or f.status != FineStatus.PAID:
                                all_paid = False
                                break
                    inv_status = (
                        InvoiceStatus.PAID if all_paid else InvoiceStatus.PARTIALLY_PAID
                    )
                    if inv.status != inv_status:
                        updated_inv = Invoice(
                            invoice_id=inv.invoice_id,
                            organization_id=inv.organization_id,
                            member_id=inv.member_id,
                            invoice_number=inv.invoice_number,
                            subtotal=inv.subtotal,
                            tax=inv.tax,
                            total=inv.total,
                            currency=inv.currency,
                            status=inv_status,
                            issued_at=inv.issued_at,
                            created_at=inv.created_at,
                            updated_at=now,
                            lines=inv.lines,
                            due_at=inv.due_at,
                        )
                        self._store.update_invoice(updated_inv)
            return created_alloc

        return self._execute_transaction(
            actor.organization_id,
            _mutation,
            audit_event,
            outbox_event,
        )

    def get_allocation(
        self, *, actor: Principal, allocation_id: UUID
    ) -> PaymentAllocation:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "public_library.read")
        alloc = self._store.get_allocation(actor.organization_id, allocation_id)
        if alloc is None:
            raise AllocationNotFoundError(
                f"Allocation {allocation_id} not found in organization {actor.organization_id}"
            )
        return alloc

    def list_allocations_for_fine(
        self, *, actor: Principal, fine_id: UUID
    ) -> list[PaymentAllocation]:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "public_library.read")
        return self._store.list_allocations_for_fine(actor.organization_id, fine_id)

    def list_allocations_for_payment(
        self, *, actor: Principal, payment_id: UUID
    ) -> list[PaymentAllocation]:
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "public_library.read")
        return self._store.list_allocations_for_payment(
            actor.organization_id, payment_id
        )

    def refund_payment(
        self,
        *,
        actor: Principal,
        payment_id: UUID,
        amount: Decimal,
        fine_id: UUID | None = None,
        reason: str | None = None,
        correlation_id: UUID | None = None,
    ) -> PaymentAllocation:
        """Record an immutable refund allocation against a payment and optional fine balance."""
        self._ensure_edition_enabled(actor.organization_id)
        self._authorizer.require(actor, "public_library.manage")

        if isinstance(amount, float):
            raise TypeError(
                "Floating-point money amounts are rejected; use Decimal instead."
            )
        if not isinstance(amount, Decimal):
            raise InvalidMoneyError(
                f"Refund amount must be Decimal, got {type(amount).__name__}"
            )
        if amount <= Decimal("0.0000"):
            raise InvalidAllocationAmountError(
                f"Refund amount must be strictly positive, got {amount}"
            )

        payment = self.get_payment(actor=actor, payment_id=payment_id)
        if payment.status not in (
            PaymentStatus.SUCCEEDED,
            PaymentStatus.PARTIALLY_REFUNDED,
        ):
            raise InvalidPaymentStateTransitionError(
                f"Cannot refund payment in status '{payment.status}'; must be succeeded or partially_refunded"
            )

        existing_allocs = self._store.list_allocations_for_payment(
            actor.organization_id, payment_id
        )
        existing_refunds = [
            a for a in existing_allocs if a.allocation_type == AllocationType.REFUND
        ]
        total_refunded = sum((a.amount for a in existing_refunds), Decimal("0.0000"))
        remaining_refundable = payment.amount - total_refunded
        if amount > remaining_refundable:
            raise OverRefundError(
                f"Refund amount {amount} {payment.currency} exceeds remaining refundable balance of {remaining_refundable} {payment.currency}"
            )

        now = self._clock()
        if fine_id is not None:
            fine = self.get_fine(actor=actor, fine_id=fine_id)
            if payment.currency != fine.currency:
                raise CurrencyMismatchError(
                    f"Payment currency '{payment.currency}' does not match fine currency '{fine.currency}'"
                )
            fine_allocs = self._store.list_allocations_for_fine(
                actor.organization_id, fine_id
            )
            net_allocated = sum(
                (
                    a.amount
                    if a.allocation_type != AllocationType.REFUND
                    else -a.amount
                    for a in fine_allocs
                ),
                Decimal("0.0000"),
            )
            if amount > net_allocated:
                raise OverRefundError(
                    f"Refund amount {amount} {fine.currency} exceeds fine net allocated amount of {net_allocated} {fine.currency}"
                )
            net_after = net_allocated - amount
            if net_after <= Decimal("0.0000"):
                new_fine_status = FineStatus.ASSESSED
            elif net_after < fine.amount:
                new_fine_status = FineStatus.PARTIALLY_PAID
            else:
                new_fine_status = fine.status

            if new_fine_status != fine.status:
                updated_fine = Fine(
                    fine_id=fine.fine_id,
                    organization_id=fine.organization_id,
                    member_id=fine.member_id,
                    amount=fine.amount,
                    currency=fine.currency,
                    status=new_fine_status,
                    reason=fine.reason,
                    assessed_at=fine.assessed_at,
                    created_at=fine.created_at,
                    updated_at=now,
                    loan_id=fine.loan_id,
                )
                self._store.update_fine(updated_fine)

        new_total_refunded = total_refunded + amount
        new_pay_status = (
            PaymentStatus.REFUNDED
            if new_total_refunded >= payment.amount
            else PaymentStatus.PARTIALLY_REFUNDED
        )
        self._store.update_payment_status(
            actor.organization_id,
            payment_id,
            new_pay_status,
            now,
            paid_at=payment.paid_at,
        )

        alloc_id = uuid4()
        allocation = PaymentAllocation(
            allocation_id=alloc_id,
            organization_id=actor.organization_id,
            payment_id=payment_id,
            fine_id=fine_id or uuid4(),
            amount=amount,
            allocation_type=AllocationType.REFUND,
            created_at=now,
        )

        audit_corr = correlation_id or uuid4()
        audit_event = AuditEvent(
            action="payment.refunded",
            entity_type="payment",
            entity_id=payment_id,
            payload={
                "payment_id": str(payment_id),
                "allocation_id": str(alloc_id),
                "organization_id": str(actor.organization_id),
                "fine_id": str(fine_id) if fine_id else None,
                "amount": str(amount),
                "currency": payment.currency,
                "new_status": new_pay_status,
                "reason": reason,
            },
            correlation_id=audit_corr,
            actor_user_id=actor.user_id,
            actor_type="user",
        )
        outbox_event = OutboxEvent(
            event_type="public_library.payment_refunded",
            aggregate_type="payment",
            aggregate_id=payment_id,
            payload_version=1,
            payload={
                "payment_id": str(payment_id),
                "allocation_id": str(alloc_id),
                "organization_id": str(actor.organization_id),
                "amount": str(amount),
                "currency": payment.currency,
                "new_status": new_pay_status,
            },
            correlation_id=audit_corr,
            idempotency_key=f"refund:{alloc_id}:recorded",
        )

        return self._execute_transaction(
            actor.organization_id,
            lambda conn: self._store.create_allocation(allocation),
            audit_event,
            outbox_event,
        )
