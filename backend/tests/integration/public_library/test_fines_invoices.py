"""Integration tests for public library fine calculation, invoices, and immutable allocations.

Validates BE-023 requirements:
- Money precision: pure Decimal arithmetic, explicit currency, floating-point money paths rejected.
- Fine assessment: manual and overdue calculation independent of browser/payment providers.
- Invoice immutability: issued invoice lines, unit prices, quantities, and totals cannot be changed.
- Allocation rules: allocation totals cannot exceed related fine amount or payment amount.
- Financial integrity: tenant isolation, transactional audit and outbox persistence.
- Reviewer checklist:
  * Decimal arithmetic is used end to end.
  * No general accounting ledger is added.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest

from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.authorization import AuthorizationPort
from openlibrary.modules.ops.application.persistence import (
    AuditEvent,
    AuditedTransaction,
    OutboxEvent,
)
from openlibrary.modules.public_library.application import (
    PublicLibraryFinanceService,
    PublicLibraryStore,
)
from openlibrary.modules.public_library.domain import (
    CurrencyMismatchError,
    Fine,
    FineNotFoundError,
    FineStatus,
    InvalidAllocationAmountError,
    InvalidMoneyError,
    Invoice,
    InvoiceImmutableError,
    InvoiceLine,
    InvoiceStatus,
    Member,
    MemberStatus,
    Money,
    OverAllocationError,
    Payment,
    PaymentAllocation,
)


class _AllowAllAuthorizer(AuthorizationPort):
    def require(self, actor: Principal, permission: str) -> None:
        pass


class _RecordingAuditedTransaction(AuditedTransaction):
    """Captures audit and outbox events executed in a transaction."""

    def __init__(self) -> None:
        self.recorded_audits: list[AuditEvent] = []
        self.recorded_outboxes: list[OutboxEvent] = []

    def run(
        self,
        connection: Any,
        mutation: Any,
        audit_event: AuditEvent,
        outbox_events: tuple[OutboxEvent, ...] | list[OutboxEvent],
    ) -> Any:
        result = mutation(connection)
        self.recorded_audits.append(audit_event)
        self.recorded_outboxes.extend(outbox_events)
        return result


@dataclass
class _InMemoryPublicLibraryFinanceStore(PublicLibraryStore):
    """In-memory store implementing members, plans, fines, invoices, payments and allocations."""

    edition_enabled_orgs: set[UUID] = field(default_factory=set)
    members: dict[UUID, Member] = field(default_factory=dict)
    fines: dict[UUID, Fine] = field(default_factory=dict)
    invoices: dict[UUID, Invoice] = field(default_factory=dict)
    invoice_lines: dict[UUID, list[InvoiceLine]] = field(default_factory=dict)
    payments: dict[UUID, Payment] = field(default_factory=dict)
    allocations: dict[UUID, PaymentAllocation] = field(default_factory=dict)

    def is_edition_enabled(self, organization_id: UUID) -> bool:
        return organization_id in self.edition_enabled_orgs

    # Members
    def create_member(self, member: Member) -> Member:
        self.members[member.member_id] = member
        return member

    def get_member(self, organization_id: UUID, member_id: UUID) -> Member | None:
        member = self.members.get(member_id)
        if member is not None and member.organization_id == organization_id:
            return member
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

    # Unused membership plan & subscription stubs for protocol completeness
    def create_plan(self, plan: Any) -> Any:
        return plan

    def get_plan(self, organization_id: UUID, plan_id: UUID) -> Any:
        return None

    def get_plan_by_code(self, organization_id: UUID, code: str) -> Any:
        return None

    def list_plans(self, organization_id: UUID, status: str | None = None) -> list[Any]:
        return []

    def update_plan(self, plan: Any) -> Any:
        return plan

    def seed_default_plans(self, organization_id: UUID) -> list[Any]:
        return []

    def create_subscription(self, subscription: Any) -> Any:
        return subscription

    def get_subscription(self, organization_id: UUID, subscription_id: UUID) -> Any:
        return None

    def list_subscriptions(
        self,
        organization_id: UUID,
        member_id: UUID | None = None,
        status: str | None = None,
    ) -> list[Any]:
        return []

    def get_active_subscription_for_member(
        self, organization_id: UUID, member_id: UUID, as_of: datetime
    ) -> Any:
        return None

    def update_subscription(self, subscription: Any) -> Any:
        return subscription

    # Fines
    def create_fine(self, fine: Fine) -> Fine:
        self.fines[fine.fine_id] = fine
        return fine

    def get_fine(self, organization_id: UUID, fine_id: UUID) -> Fine | None:
        fine = self.fines.get(fine_id)
        if fine is not None and fine.organization_id == organization_id:
            return fine
        return None

    def list_fines(
        self,
        organization_id: UUID,
        *,
        member_id: UUID | None = None,
        loan_id: UUID | None = None,
        status: str | None = None,
    ) -> list[Fine]:
        results = [
            f for f in self.fines.values() if f.organization_id == organization_id
        ]
        if member_id is not None:
            results = [f for f in results if f.member_id == member_id]
        if loan_id is not None:
            results = [f for f in results if f.loan_id == loan_id]
        if status is not None:
            results = [f for f in results if f.status == status]
        return sorted(results, key=lambda f: f.created_at, reverse=True)

    def update_fine(self, fine: Fine) -> Fine:
        self.fines[fine.fine_id] = fine
        return fine

    # Invoices
    def create_invoice(self, invoice: Invoice, lines: list[InvoiceLine]) -> Invoice:
        self.invoices[invoice.invoice_id] = invoice
        self.invoice_lines[invoice.invoice_id] = list(lines)
        return invoice

    def get_invoice(self, organization_id: UUID, invoice_id: UUID) -> Invoice | None:
        inv = self.invoices.get(invoice_id)
        if inv is not None and inv.organization_id == organization_id:
            lines = self.invoice_lines.get(invoice_id, [])
            return Invoice(
                invoice_id=inv.invoice_id,
                organization_id=inv.organization_id,
                member_id=inv.member_id,
                invoice_number=inv.invoice_number,
                subtotal=inv.subtotal,
                tax=inv.tax,
                total=inv.total,
                currency=inv.currency,
                status=inv.status,
                issued_at=inv.issued_at,
                due_at=inv.due_at,
                lines=lines,
                created_at=inv.created_at,
                updated_at=inv.updated_at,
            )
        return None

    def list_invoices(
        self,
        organization_id: UUID,
        *,
        member_id: UUID | None = None,
        status: str | None = None,
    ) -> list[Invoice]:
        results = [
            inv
            for inv in self.invoices.values()
            if inv.organization_id == organization_id
        ]
        if member_id is not None:
            results = [inv for inv in results if inv.member_id == member_id]
        if status is not None:
            results = [inv for inv in results if inv.status == status]
        return sorted(results, key=lambda inv: inv.created_at, reverse=True)

    def update_invoice(self, invoice: Invoice) -> Invoice:
        self.invoices[invoice.invoice_id] = invoice
        return invoice

    # Payments
    def create_payment(self, payment: Payment) -> Payment:
        self.payments[payment.payment_id] = payment
        return payment

    def get_payment(self, organization_id: UUID, payment_id: UUID) -> Payment | None:
        pay = self.payments.get(payment_id)
        if pay is not None and pay.organization_id == organization_id:
            return pay
        return None

    def list_payments(
        self,
        organization_id: UUID,
        *,
        member_id: UUID | None = None,
        status: str | None = None,
    ) -> list[Payment]:
        results = [
            p for p in self.payments.values() if p.organization_id == organization_id
        ]
        if member_id is not None:
            results = [p for p in results if p.member_id == member_id]
        if status is not None:
            results = [p for p in results if p.status == status]
        return sorted(results, key=lambda p: p.created_at, reverse=True)

    def update_payment(self, payment: Payment) -> Payment:
        self.payments[payment.payment_id] = payment
        return payment

    # Allocations
    def create_allocation(self, allocation: PaymentAllocation) -> PaymentAllocation:
        self.allocations[allocation.allocation_id] = allocation
        return allocation

    def get_allocation(
        self, organization_id: UUID, allocation_id: UUID
    ) -> PaymentAllocation | None:
        alloc = self.allocations.get(allocation_id)
        if alloc is not None and alloc.organization_id == organization_id:
            return alloc
        return None

    def list_allocations_for_fine(
        self, organization_id: UUID, fine_id: UUID
    ) -> list[PaymentAllocation]:
        return [
            a
            for a in self.allocations.values()
            if a.organization_id == organization_id and a.fine_id == fine_id
        ]

    def list_allocations_for_payment(
        self, organization_id: UUID, payment_id: UUID
    ) -> list[PaymentAllocation]:
        return [
            a
            for a in self.allocations.values()
            if a.organization_id == organization_id and a.payment_id == payment_id
        ]


def _setup_service(
    org_id: UUID,
) -> tuple[
    PublicLibraryFinanceService,
    _InMemoryPublicLibraryFinanceStore,
    _RecordingAuditedTransaction,
]:
    store = _InMemoryPublicLibraryFinanceStore(edition_enabled_orgs={org_id})
    authorizer = _AllowAllAuthorizer()
    tx = _RecordingAuditedTransaction()
    service = PublicLibraryFinanceService(
        store=store,
        authorizer=authorizer,
        transaction=tx,
        clock=lambda: datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc),
    )
    return service, store, tx


def test_money_value_type_enforces_decimal_and_rejects_floating_point() -> None:
    """Evidence Checkpoint: Floating-point money paths are rejected; pure Decimal arithmetic enforced."""
    # 1. Valid decimal instantiation
    m1 = Money(Decimal("15.5000"), "USD")
    assert m1.amount == Decimal("15.5000")
    assert m1.currency == "USD"

    # 2. Strict rejection of float type
    with pytest.raises(
        (TypeError, InvalidMoneyError), match="[Ff]loat.*rejected|[Ff]loating-point"
    ):
        Money(15.5, "USD")  # type: ignore[arg-type]

    # 3. Explicit currency is required
    with pytest.raises(InvalidMoneyError, match="[Cc]urrency"):
        Money(Decimal("10.0000"), "")

    with pytest.raises(InvalidMoneyError, match="[Cc]urrency"):
        Money(Decimal("10.0000"), "US")

    # 4. Negative money amounts rejected for default Money constructor
    with pytest.raises(InvalidMoneyError, match="negative"):
        Money(Decimal("-5.0000"), "USD")

    # 5. Arithmetic operations
    m2 = Money(Decimal("4.5000"), "USD")
    m_sum = m1 + m2
    assert m_sum.amount == Decimal("20.0000")
    assert m_sum.currency == "USD"

    m_diff = m1 - m2
    assert m_diff.amount == Decimal("11.0000")

    # 6. Currency mismatch on arithmetic
    m_eur = Money(Decimal("5.0000"), "EUR")
    with pytest.raises(CurrencyMismatchError):
        _ = m1 + m_eur


def test_assess_fine_with_pure_decimal_and_audited_events() -> None:
    """Fine assessment produces decimal values and transactional audit/outbox events."""
    org_id = uuid4()
    service, store, tx = _setup_service(org_id)
    actor = Principal(user_id=uuid4(), organization_id=org_id, session_id=uuid4())

    # Setup member
    member = store.create_member(
        Member(
            member_id=uuid4(),
            organization_id=org_id,
            user_id=uuid4(),
            member_number="M-1001",
            status=MemberStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )

    fine = service.assess_fine(
        actor=actor,
        member_id=member.member_id,
        amount=Decimal("12.5000"),
        currency="USD",
        reason="overdue_loan",
        loan_id=uuid4(),
    )

    assert fine.organization_id == org_id
    assert fine.member_id == member.member_id
    assert fine.amount == Decimal("12.5000")
    assert fine.currency == "USD"
    assert fine.status == FineStatus.ASSESSED

    # Verify audit and outbox events
    assert len(tx.recorded_audits) == 1
    assert tx.recorded_audits[0].action == "fine.assessed"
    assert tx.recorded_audits[0].entity_id == fine.fine_id
    assert tx.recorded_audits[0].payload["amount"] == "12.5000"
    assert tx.recorded_audits[0].payload["currency"] == "USD"

    assert len(tx.recorded_outboxes) == 1
    assert tx.recorded_outboxes[0].event_type == "public_library.fine_assessed"
    assert tx.recorded_outboxes[0].aggregate_id == fine.fine_id


def test_calculate_overdue_fine_pure_decimal() -> None:
    """Overdue fine calculation calculates days overdue and respects optional max cap."""
    org_id = uuid4()
    service, _, _ = _setup_service(org_id)

    due_at = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)
    returned_at = datetime(
        2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc
    )  # 10 days overdue
    daily_rate = Decimal("0.5000")

    # 10 days * 0.50 = 5.0000 USD
    calc = service.calculate_overdue_fine(
        due_at=due_at,
        effective_return_at=returned_at,
        daily_rate=daily_rate,
        currency="USD",
    )
    assert calc.amount == Decimal("5.0000")
    assert calc.currency == "USD"

    # With max fine cap of 3.0000
    capped = service.calculate_overdue_fine(
        due_at=due_at,
        effective_return_at=returned_at,
        daily_rate=daily_rate,
        currency="USD",
        max_fine=Decimal("3.0000"),
    )
    assert capped.amount == Decimal("3.0000")


def test_issued_invoice_lines_and_totals_are_immutable() -> None:
    """Evidence Checkpoint: Issued invoice lines and totals cannot be changed."""
    org_id = uuid4()
    service, store, tx = _setup_service(org_id)
    actor = Principal(user_id=uuid4(), organization_id=org_id, session_id=uuid4())

    member = store.create_member(
        Member(
            member_id=uuid4(),
            organization_id=org_id,
            user_id=uuid4(),
            member_number="M-1002",
            status=MemberStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )

    line1 = InvoiceLine(
        invoice_line_id=uuid4(),
        organization_id=org_id,
        invoice_id=uuid4(),
        line_number=1,
        description="Overdue loan fine - Clean Code",
        quantity=1,
        unit_price=Decimal("15.0000"),
        amount=Decimal("15.0000"),
        fine_id=None,
        created_at=datetime.now(timezone.utc),
    )
    line2 = InvoiceLine(
        invoice_line_id=uuid4(),
        organization_id=org_id,
        invoice_id=uuid4(),
        line_number=2,
        description="Damaged barcode replacement",
        quantity=2,
        unit_price=Decimal("2.5000"),
        amount=Decimal("5.0000"),
        fine_id=None,
        created_at=datetime.now(timezone.utc),
    )

    invoice = service.issue_invoice(
        actor=actor,
        member_id=member.member_id,
        lines=[line1, line2],
        currency="USD",
        tax=Decimal("2.0000"),
    )

    assert invoice.subtotal == Decimal("20.0000")
    assert invoice.tax == Decimal("2.0000")
    assert invoice.total == Decimal("22.0000")
    assert invoice.status == InvoiceStatus.ISSUED
    assert len(invoice.lines) == 2

    # Attempting to mutate lines or totals on the issued invoice raises InvoiceImmutableError
    with pytest.raises(
        InvoiceImmutableError, match="[Ii]mmutable|cannot be changed|already issued"
    ):
        service.modify_invoice_lines(
            actor=actor,
            invoice_id=invoice.invoice_id,
            new_lines=[line1],
        )

    with pytest.raises(
        InvoiceImmutableError, match="[Ii]mmutable|cannot be changed|already issued"
    ):
        service.update_invoice_total(
            actor=actor,
            invoice_id=invoice.invoice_id,
            new_total=Decimal("10.0000"),
        )


def test_allocation_caps_and_over_allocation_rejection() -> None:
    """Evidence Checkpoint: Over-allocation and floating-point money paths are rejected.

    Allocation totals cannot exceed either the fine amount or the payment amount.
    """
    org_id = uuid4()
    service, store, tx = _setup_service(org_id)
    actor = Principal(user_id=uuid4(), organization_id=org_id, session_id=uuid4())

    member = store.create_member(
        Member(
            member_id=uuid4(),
            organization_id=org_id,
            user_id=uuid4(),
            member_number="M-1003",
            status=MemberStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )

    # 1. Fine of 20.0000 USD
    fine = service.assess_fine(
        actor=actor,
        member_id=member.member_id,
        amount=Decimal("20.0000"),
        currency="USD",
        reason="overdue_book",
    )

    # 2. Payment of 15.0000 USD
    payment = service.record_payment(
        actor=actor,
        member_id=member.member_id,
        amount=Decimal("15.0000"),
        currency="USD",
        provider="cash",
    )

    # 3. Attempt to allocate 16.0000 USD (exceeds payment amount of 15.0000)
    with pytest.raises(OverAllocationError, match="payment"):
        service.allocate_payment(
            actor=actor,
            payment_id=payment.payment_id,
            fine_id=fine.fine_id,
            amount=Decimal("16.0000"),
        )

    # 4. Valid partial allocation of 10.0000 USD
    alloc1 = service.allocate_payment(
        actor=actor,
        payment_id=payment.payment_id,
        fine_id=fine.fine_id,
        amount=Decimal("10.0000"),
    )
    assert alloc1.amount == Decimal("10.0000")

    # Fine should now be partially_paid
    updated_fine = service.get_fine(actor=actor, fine_id=fine.fine_id)
    assert updated_fine.status == FineStatus.PARTIALLY_PAID

    # 5. Attempt second allocation of 6.0000 USD (remaining payment is only 5.0000)
    with pytest.raises(OverAllocationError, match="payment"):
        service.allocate_payment(
            actor=actor,
            payment_id=payment.payment_id,
            fine_id=fine.fine_id,
            amount=Decimal("6.0000"),
        )

    # 6. Allocate remaining 5.0000 USD
    alloc2 = service.allocate_payment(
        actor=actor,
        payment_id=payment.payment_id,
        fine_id=fine.fine_id,
        amount=Decimal("5.0000"),
    )
    assert alloc2.amount == Decimal("5.0000")

    # 7. Record a 2nd payment of 10.0000 USD
    payment2 = service.record_payment(
        actor=actor,
        member_id=member.member_id,
        amount=Decimal("10.0000"),
        currency="USD",
        provider="manual",
    )

    # Fine has 5.0000 unallocated remaining (total 20 - 10 - 5 = 5).
    # Attempting to allocate 6.0000 from payment2 exceeds fine remaining cap!
    with pytest.raises(OverAllocationError, match="fine"):
        service.allocate_payment(
            actor=actor,
            payment_id=payment2.payment_id,
            fine_id=fine.fine_id,
            amount=Decimal("6.0000"),
        )

    # Allocate exact remaining 5.0000 to fully pay fine
    alloc3 = service.allocate_payment(
        actor=actor,
        payment_id=payment2.payment_id,
        fine_id=fine.fine_id,
        amount=Decimal("5.0000"),
    )
    assert alloc3.amount == Decimal("5.0000")

    # Fine is now fully paid
    completed_fine = service.get_fine(actor=actor, fine_id=fine.fine_id)
    assert completed_fine.status == FineStatus.PAID

    # Attempting to allocate to an already fully paid fine raises error
    with pytest.raises(OverAllocationError, match="already fully paid|exceed"):
        service.allocate_payment(
            actor=actor,
            payment_id=payment2.payment_id,
            fine_id=fine.fine_id,
            amount=Decimal("1.0000"),
        )


def test_allocation_rejects_negative_or_zero_amounts() -> None:
    """Allocations must be strictly positive."""
    org_id = uuid4()
    service, store, _ = _setup_service(org_id)
    actor = Principal(user_id=uuid4(), organization_id=org_id, session_id=uuid4())

    member = store.create_member(
        Member(
            member_id=uuid4(),
            organization_id=org_id,
            user_id=uuid4(),
            member_number="M-1004",
            status=MemberStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    fine = service.assess_fine(
        actor=actor,
        member_id=member.member_id,
        amount=Decimal("10.0000"),
        currency="USD",
        reason="fine",
    )
    payment = service.record_payment(
        actor=actor,
        member_id=member.member_id,
        amount=Decimal("10.0000"),
        currency="USD",
        provider="cash",
    )

    with pytest.raises(InvalidAllocationAmountError):
        service.allocate_payment(
            actor=actor,
            payment_id=payment.payment_id,
            fine_id=fine.fine_id,
            amount=Decimal("0.0000"),
        )

    with pytest.raises(InvalidAllocationAmountError):
        service.allocate_payment(
            actor=actor,
            payment_id=payment.payment_id,
            fine_id=fine.fine_id,
            amount=Decimal("-1.0000"),
        )


def test_tenant_boundary_isolation_for_fines_and_invoices() -> None:
    """Ensure operations fail if attempting to access another organization's financial records."""
    org_a = uuid4()
    org_b = uuid4()
    store = _InMemoryPublicLibraryFinanceStore(edition_enabled_orgs={org_a, org_b})
    service = PublicLibraryFinanceService(
        store=store,
        authorizer=_AllowAllAuthorizer(),
        transaction=_RecordingAuditedTransaction(),
    )

    actor_a = Principal(user_id=uuid4(), organization_id=org_a, session_id=uuid4())
    actor_b = Principal(user_id=uuid4(), organization_id=org_b, session_id=uuid4())

    member_a = store.create_member(
        Member(
            member_id=uuid4(),
            organization_id=org_a,
            user_id=uuid4(),
            member_number="M-ORG-A",
            status=MemberStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )

    fine_a = service.assess_fine(
        actor=actor_a,
        member_id=member_a.member_id,
        amount=Decimal("10.0000"),
        currency="USD",
        reason="overdue",
    )

    # Actor B cannot view Fine A
    with pytest.raises(FineNotFoundError):
        service.get_fine(actor=actor_b, fine_id=fine_a.fine_id)

    # Actor B cannot allocate to Fine A
    member_b = store.create_member(
        Member(
            member_id=uuid4(),
            organization_id=org_b,
            user_id=uuid4(),
            member_number="M-ORG-B",
            status=MemberStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    payment_b = service.record_payment(
        actor=actor_b,
        member_id=member_b.member_id,
        amount=Decimal("10.0000"),
        currency="USD",
        provider="cash",
    )
    with pytest.raises(FineNotFoundError):
        service.allocate_payment(
            actor=actor_b,
            payment_id=payment_b.payment_id,
            fine_id=fine_a.fine_id,
            amount=Decimal("5.0000"),
        )
