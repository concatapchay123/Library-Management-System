"""Integration tests for signed payment webhook, reconciliation, and payment idempotency.

Validates BE-024 requirements:
- Raw-body signature verification and replay protection (max 5 min replay window).
- Rejection of invalid signatures and stale timestamps before payload parsing.
- Payment state machine (pending, authorized, succeeded, failed, refunded, partially_refunded, disputed).
- Provider event deduplication: duplicate provider events cannot settle payment twice.
- Provider reference uniqueness enforced at tenant and provider boundary.
- Provider timeout remains pending until reconciliation decides it.
- Outbox reconciliation consumer handles provider settlement and failure idempotently.
- Partial and refund allocations obey documented caps and state transitions.
- Raw body, signature secret, credential, and card data are never persisted.
- Webhook endpoint has no browser access-token dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import hmac
import json
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
    AllocationType,
    DuplicateProviderEventError,
    DuplicateProviderReferenceError,
    Fine,
    FineStatus,
    InvalidPaymentStateTransitionError,
    InvalidWebhookSignatureError,
    Member,
    MemberStatus,
    OverRefundError,
    Payment,
    PaymentAllocation,
    PaymentEvent,
    PaymentNotFoundError,
    PaymentStatus,
    StaleWebhookTimestampError,
)
from openlibrary.modules.public_library.webhooks import (
    PaymentProviderPort,
    ProviderPaymentStatusResult,
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
class _InMemoryPaymentsStore(PublicLibraryStore):
    """In-memory store supporting payments, provider events, fines, and allocations."""

    edition_enabled_orgs: set[UUID] = field(default_factory=set)
    members: dict[UUID, Member] = field(default_factory=dict)
    fines: dict[UUID, Fine] = field(default_factory=dict)
    payments: dict[UUID, Payment] = field(default_factory=dict)
    allocations: dict[UUID, PaymentAllocation] = field(default_factory=dict)
    payment_events: dict[tuple[UUID, str, str], PaymentEvent] = field(
        default_factory=dict
    )

    def is_edition_enabled(self, organization_id: UUID) -> bool:
        return organization_id in self.edition_enabled_orgs

    def create_member(self, member: Member) -> Member:
        self.members[member.member_id] = member
        return member

    def get_member(self, organization_id: UUID, member_id: UUID) -> Member | None:
        m = self.members.get(member_id)
        if m and m.organization_id == organization_id:
            return m
        return None

    def create_fine(self, fine: Fine) -> Fine:
        self.fines[fine.fine_id] = fine
        return fine

    def get_fine(self, organization_id: UUID, fine_id: UUID) -> Fine | None:
        f = self.fines.get(fine_id)
        if f and f.organization_id == organization_id:
            return f
        return None

    def update_fine(self, fine: Fine) -> Fine:
        self.fines[fine.fine_id] = fine
        return fine

    def update_fine_status(
        self,
        organization_id: UUID,
        fine_id: UUID,
        status: str,
        updated_at: datetime,
    ) -> Fine:
        existing = self.get_fine(organization_id, fine_id)
        if existing is None:
            raise ValueError(f"Fine {fine_id} not found")
        updated = Fine(
            fine_id=existing.fine_id,
            organization_id=existing.organization_id,
            member_id=existing.member_id,
            amount=existing.amount,
            currency=existing.currency,
            status=status,
            reason=existing.reason,
            assessed_at=existing.assessed_at,
            created_at=existing.created_at,
            updated_at=updated_at,
            loan_id=existing.loan_id,
        )
        self.fines[fine_id] = updated
        return updated

    def create_payment(self, payment: Payment) -> Payment:
        # Enforce provider reference uniqueness at (organization_id, provider, provider_reference) boundary
        if payment.provider_reference is not None:
            for p in self.payments.values():
                if (
                    p.organization_id == payment.organization_id
                    and p.provider == payment.provider
                    and p.provider_reference == payment.provider_reference
                    and p.payment_id != payment.payment_id
                ):
                    raise DuplicateProviderReferenceError(
                        f"Payment with provider '{payment.provider}' and reference '{payment.provider_reference}' already exists for organization {payment.organization_id}"
                    )
        self.payments[payment.payment_id] = payment
        return payment

    def get_payment(self, organization_id: UUID, payment_id: UUID) -> Payment | None:
        p = self.payments.get(payment_id)
        if p and p.organization_id == organization_id:
            return p
        return None

    def get_payment_by_provider_reference(
        self,
        organization_id: UUID,
        provider: str,
        provider_reference: str,
    ) -> Payment | None:
        for p in self.payments.values():
            if (
                p.organization_id == organization_id
                and p.provider == provider
                and p.provider_reference == provider_reference
            ):
                return p
        return None

    def update_payment_status(
        self,
        organization_id: UUID,
        payment_id: UUID,
        status: str,
        updated_at: datetime,
        paid_at: datetime | None = None,
        provider_event_id: str | None = None,
    ) -> Payment:
        existing = self.get_payment(organization_id, payment_id)
        if existing is None:
            raise PaymentNotFoundError(f"Payment {payment_id} not found")
        updated = Payment(
            payment_id=existing.payment_id,
            organization_id=existing.organization_id,
            member_id=existing.member_id,
            amount=existing.amount,
            currency=existing.currency,
            provider=existing.provider,
            status=status,
            created_at=existing.created_at,
            updated_at=updated_at,
            provider_reference=existing.provider_reference,
            provider_event_id=provider_event_id or existing.provider_event_id,
            paid_at=paid_at or existing.paid_at,
        )
        self.payments[payment_id] = updated
        return updated

    def list_payments(
        self,
        organization_id: UUID,
        member_id: UUID | None = None,
        status: str | None = None,
    ) -> list[Payment]:
        result = [
            p for p in self.payments.values() if p.organization_id == organization_id
        ]
        if member_id is not None:
            result = [p for p in result if p.member_id == member_id]
        if status is not None:
            result = [p for p in result if p.status == status]
        return result

    def create_allocation(self, allocation: PaymentAllocation) -> PaymentAllocation:
        self.allocations[allocation.allocation_id] = allocation
        return allocation

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

    def record_payment_event(self, event: PaymentEvent) -> PaymentEvent:
        key = (event.organization_id, event.provider, event.provider_event_id)
        if key in self.payment_events:
            raise DuplicateProviderEventError(
                f"Provider event '{event.provider_event_id}' from provider '{event.provider}' already exists for organization {event.organization_id}"
            )
        self.payment_events[key] = event
        return event

    def get_payment_event(
        self,
        organization_id: UUID,
        provider: str,
        provider_event_id: str,
    ) -> PaymentEvent | None:
        return self.payment_events.get((organization_id, provider, provider_event_id))


class _StubPaymentProvider(PaymentProviderPort):
    """Stub implementation for provider queries and webhook signing."""

    def __init__(self, secret: str = "whsec_test_secret_key_12345") -> None:
        self.secret = secret
        self.status_responses: dict[tuple[str, str], ProviderPaymentStatusResult] = {}

    def get_payment_status(
        self,
        *,
        provider: str,
        provider_reference: str,
    ) -> ProviderPaymentStatusResult:
        if (provider, provider_reference) in self.status_responses:
            return self.status_responses[(provider, provider_reference)]
        return ProviderPaymentStatusResult(
            provider_reference=provider_reference,
            status=PaymentStatus.PENDING,
            amount=Decimal("25.0000"),
            currency="USD",
        )

    def get_webhook_secret(
        self,
        *,
        organization_id: UUID,
        provider: str,
    ) -> str:
        return self.secret

    def generate_signature(
        self,
        raw_body: bytes,
        timestamp: int,
    ) -> str:
        payload = f"{timestamp}.".encode("utf-8") + raw_body
        return hmac.new(
            self.secret.encode("utf-8"), payload, hashlib.sha256
        ).hexdigest()


def _build_test_setup() -> tuple[
    PublicLibraryFinanceService,
    _InMemoryPaymentsStore,
    _RecordingAuditedTransaction,
    _StubPaymentProvider,
    UUID,
    UUID,
    Principal,
]:
    org_id = uuid4()
    user_id = uuid4()
    principal = Principal(user_id=user_id, organization_id=org_id, session_id=uuid4())

    store = _InMemoryPaymentsStore()
    store.edition_enabled_orgs.add(org_id)

    member = Member(
        member_id=uuid4(),
        organization_id=org_id,
        user_id=user_id,
        member_number="MEM-001",
        status=MemberStatus.ACTIVE,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    store.create_member(member)

    audited_tx = _RecordingAuditedTransaction()
    authorizer = _AllowAllAuthorizer()
    provider = _StubPaymentProvider()

    service = PublicLibraryFinanceService(
        store=store,
        authorizer=authorizer,
        transaction=audited_tx,
        clock=lambda: datetime.now(timezone.utc),
        payment_provider=provider,
    )
    return service, store, audited_tx, provider, org_id, member.member_id, principal


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------


def test_invalid_webhook_signature_rejected_before_payload_parsing() -> None:
    """Invalid webhook signatures must be rejected without parsing raw body."""
    service, store, _, provider, org_id, _, _ = _build_test_setup()

    malformed_json_raw_body = b"NOT_VALID_JSON{foo:"
    now = int(datetime.now(timezone.utc).timestamp())
    invalid_signature = "bad_hex_signature_abcdef123456"

    headers = {
        "X-Webhook-Signature": invalid_signature,
        "X-Webhook-Timestamp": str(now),
    }

    # Must raise InvalidWebhookSignatureError, NOT json.JSONDecodeError!
    with pytest.raises(InvalidWebhookSignatureError, match="signature"):
        service.handle_payment_webhook(
            organization_id=org_id,
            provider="mock_provider",
            raw_body=malformed_json_raw_body,
            headers=headers,
            secret=provider.secret,
        )


def test_stale_replay_timestamp_rejected() -> None:
    """Timestamps older than 5 minutes (300s) must be rejected before mutation."""
    service, store, _, provider, org_id, _, _ = _build_test_setup()

    payload_dict = {
        "event_id": "evt_stale_1",
        "event_type": "payment.succeeded",
        "provider_reference": "ch_stale_123",
        "amount": "25.0000",
        "currency": "USD",
    }
    raw_body = json.dumps(payload_dict).encode("utf-8")
    stale_timestamp = int(
        (datetime.now(timezone.utc) - timedelta(seconds=301)).timestamp()
    )
    valid_signature_for_stale_ts = provider.generate_signature(
        raw_body, stale_timestamp
    )

    headers = {
        "X-Webhook-Signature": valid_signature_for_stale_ts,
        "X-Webhook-Timestamp": str(stale_timestamp),
    }

    with pytest.raises(StaleWebhookTimestampError, match="replay"):
        service.handle_payment_webhook(
            organization_id=org_id,
            provider="mock_provider",
            raw_body=raw_body,
            headers=headers,
            secret=provider.secret,
        )


def test_duplicate_provider_event_cannot_settle_payment_twice() -> None:
    """Duplicate provider event must return idempotent result and not settle twice."""
    service, store, audited_tx, provider, org_id, member_id, actor = _build_test_setup()

    # Pre-create payment in pending status
    payment = service.record_payment(
        actor=actor,
        member_id=member_id,
        amount=Decimal("35.0000"),
        currency="USD",
        provider="mock_provider",
        provider_reference="ch_dup_test_123",
        initial_status=PaymentStatus.PENDING,
    )
    assert payment.status == PaymentStatus.PENDING

    event_payload = {
        "event_id": "evt_unique_100",
        "event_type": "payment.succeeded",
        "provider_reference": "ch_dup_test_123",
        "amount": "35.0000",
        "currency": "USD",
    }
    raw_body = json.dumps(event_payload).encode("utf-8")
    now_ts = int(datetime.now(timezone.utc).timestamp())
    sig = provider.generate_signature(raw_body, now_ts)
    headers = {
        "X-Webhook-Signature": sig,
        "X-Webhook-Timestamp": str(now_ts),
    }

    # First event settlement
    first_res = service.handle_payment_webhook(
        organization_id=org_id,
        provider="mock_provider",
        raw_body=raw_body,
        headers=headers,
        secret=provider.secret,
    )
    assert first_res.status == PaymentStatus.SUCCEEDED
    assert first_res.paid_at is not None

    settled_payment = store.get_payment(org_id, payment.payment_id)
    assert settled_payment is not None
    assert settled_payment.status == PaymentStatus.SUCCEEDED

    initial_audit_count = len(audited_tx.recorded_audits)
    initial_outbox_count = len(audited_tx.recorded_outboxes)

    # Replay identical provider event
    second_res = service.handle_payment_webhook(
        organization_id=org_id,
        provider="mock_provider",
        raw_body=raw_body,
        headers=headers,
        secret=provider.secret,
    )
    # Must be idempotent
    assert second_res.status == PaymentStatus.SUCCEEDED
    assert second_res.payment_id == payment.payment_id

    # No duplicate settlement mutations or events emitted
    assert len(audited_tx.recorded_audits) == initial_audit_count
    assert len(audited_tx.recorded_outboxes) == initial_outbox_count


def test_provider_reference_uniqueness_enforced_at_tenant_and_provider_boundary() -> (
    None
):
    """Enforce (organization_id, provider, provider_reference) uniqueness across tenants."""
    service, store, _, _, org_a, member_a, actor_a = _build_test_setup()
    org_b = uuid4()
    store.edition_enabled_orgs.add(org_b)
    member_b = uuid4()
    store.create_member(
        Member(
            member_id=member_b,
            organization_id=org_b,
            user_id=uuid4(),
            member_number="MEM-B",
            status=MemberStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    actor_b = Principal(user_id=uuid4(), organization_id=org_b, session_id=uuid4())

    ref = "ref_shared_across_tenants_ok"

    # Payment in Org A with ref
    pay_a = service.record_payment(
        actor=actor_a,
        member_id=member_a,
        amount=Decimal("10.0000"),
        currency="USD",
        provider="stripe",
        provider_reference=ref,
        initial_status=PaymentStatus.PENDING,
    )
    assert pay_a.provider_reference == ref

    # Attempt duplicate in Org A -> fails
    with pytest.raises(DuplicateProviderReferenceError):
        service.record_payment(
            actor=actor_a,
            member_id=member_a,
            amount=Decimal("20.0000"),
            currency="USD",
            provider="stripe",
            provider_reference=ref,
            initial_status=PaymentStatus.PENDING,
        )

    # Same reference in Org B -> succeeds (tenant isolated)
    pay_b = service.record_payment(
        actor=actor_b,
        member_id=member_b,
        amount=Decimal("15.0000"),
        currency="USD",
        provider="stripe",
        provider_reference=ref,
        initial_status=PaymentStatus.PENDING,
    )
    assert pay_b.organization_id == org_b
    assert pay_b.provider_reference == ref


def test_provider_timeout_remains_pending_until_reconciliation() -> None:
    """A payment pending at the provider remains pending during reconciliation timeout."""
    service, store, audited_tx, provider, org_id, member_id, actor = _build_test_setup()

    ref = "ref_timeout_reconcile"
    payment = service.record_payment(
        actor=actor,
        member_id=member_id,
        amount=Decimal("40.0000"),
        currency="USD",
        provider="mock_provider",
        provider_reference=ref,
        initial_status=PaymentStatus.PENDING,
    )
    assert payment.status == PaymentStatus.PENDING

    # Provider indicates still pending or timeout
    provider.status_responses[("mock_provider", ref)] = ProviderPaymentStatusResult(
        provider_reference=ref,
        status=PaymentStatus.PENDING,
        amount=Decimal("40.0000"),
        currency="USD",
    )

    reconciled = service.reconcile_pending_payment(
        organization_id=org_id,
        payment_id=payment.payment_id,
    )
    # Must remain pending!
    assert reconciled.status == PaymentStatus.PENDING
    persisted = store.get_payment(org_id, payment.payment_id)
    assert persisted is not None
    assert persisted.status == PaymentStatus.PENDING


def test_reconciliation_consumer_handles_settlement_and_failure() -> None:
    """Reconciliation consumer handles provider transition to succeeded and failed."""
    service, store, audited_tx, provider, org_id, member_id, actor = _build_test_setup()

    # Case 1: Reconcile to succeeded
    ref_succ = "ref_reconcile_succ"
    pay_1 = service.record_payment(
        actor=actor,
        member_id=member_id,
        amount=Decimal("50.0000"),
        currency="USD",
        provider="mock_provider",
        provider_reference=ref_succ,
        initial_status=PaymentStatus.PENDING,
    )
    provider.status_responses[("mock_provider", ref_succ)] = (
        ProviderPaymentStatusResult(
            provider_reference=ref_succ,
            status=PaymentStatus.SUCCEEDED,
            amount=Decimal("50.0000"),
            currency="USD",
            paid_at=datetime.now(timezone.utc),
        )
    )

    res_1 = service.reconcile_pending_payment(
        organization_id=org_id,
        payment_id=pay_1.payment_id,
    )
    assert res_1.status == PaymentStatus.SUCCEEDED
    assert res_1.paid_at is not None

    # Case 2: Reconcile to failed
    ref_fail = "ref_reconcile_fail"
    pay_2 = service.record_payment(
        actor=actor,
        member_id=member_id,
        amount=Decimal("20.0000"),
        currency="USD",
        provider="mock_provider",
        provider_reference=ref_fail,
        initial_status=PaymentStatus.PENDING,
    )
    provider.status_responses[("mock_provider", ref_fail)] = (
        ProviderPaymentStatusResult(
            provider_reference=ref_fail,
            status=PaymentStatus.FAILED,
            amount=Decimal("20.0000"),
            currency="USD",
            failure_reason="insufficient_funds",
        )
    )

    res_2 = service.reconcile_pending_payment(
        organization_id=org_id,
        payment_id=pay_2.payment_id,
    )
    assert res_2.status == PaymentStatus.FAILED


def test_reconciliation_consumer_replay_does_not_execute_side_effects_twice() -> None:
    """Replaying reconciliation for an already settled payment is a no-op."""
    service, store, audited_tx, provider, org_id, member_id, actor = _build_test_setup()

    ref = "ref_reconcile_replay"
    payment = service.record_payment(
        actor=actor,
        member_id=member_id,
        amount=Decimal("25.0000"),
        currency="USD",
        provider="mock_provider",
        provider_reference=ref,
        initial_status=PaymentStatus.PENDING,
    )
    provider.status_responses[("mock_provider", ref)] = ProviderPaymentStatusResult(
        provider_reference=ref,
        status=PaymentStatus.SUCCEEDED,
        amount=Decimal("25.0000"),
        currency="USD",
        paid_at=datetime.now(timezone.utc),
    )

    # First reconciliation
    service.reconcile_pending_payment(
        organization_id=org_id,
        payment_id=payment.payment_id,
    )
    audit_count_after_first = len(audited_tx.recorded_audits)

    # Second reconciliation (replayed)
    res_second = service.reconcile_pending_payment(
        organization_id=org_id,
        payment_id=payment.payment_id,
    )
    assert res_second.status == PaymentStatus.SUCCEEDED
    assert len(audited_tx.recorded_audits) == audit_count_after_first


def test_partial_refund_and_refund_allocation_caps_and_states() -> None:
    """Partial and full refund allocations obey documented caps and state transitions."""
    service, store, _, _, org_id, member_id, actor = _build_test_setup()

    # 1. Create fine of $50 and payment of $50
    fine = service.assess_fine(
        actor=actor,
        member_id=member_id,
        amount=Decimal("50.0000"),
        currency="USD",
        reason="Damaged book spine",
    )
    payment = service.record_payment(
        actor=actor,
        member_id=member_id,
        amount=Decimal("50.0000"),
        currency="USD",
        provider="manual",
        initial_status=PaymentStatus.SUCCEEDED,
    )

    # 2. Allocate payment fully to fine
    service.allocate_payment(
        actor=actor,
        payment_id=payment.payment_id,
        fine_id=fine.fine_id,
        amount=Decimal("50.0000"),
    )
    assert store.get_fine(org_id, fine.fine_id).status == FineStatus.PAID

    # 3. Partial refund of $20
    refund_alloc_1 = service.refund_payment(
        actor=actor,
        payment_id=payment.payment_id,
        amount=Decimal("20.0000"),
        fine_id=fine.fine_id,
        reason="Goodwill partial waiver",
    )
    assert refund_alloc_1.allocation_type == AllocationType.REFUND
    assert refund_alloc_1.amount == Decimal("20.0000")

    # Payment transitions to partially_refunded
    updated_payment = store.get_payment(org_id, payment.payment_id)
    assert updated_payment.status == PaymentStatus.PARTIALLY_REFUNDED

    # Fine net allocation is now $30 / $50 -> transitions back to partially_paid
    updated_fine = store.get_fine(org_id, fine.fine_id)
    assert updated_fine.status == FineStatus.PARTIALLY_PAID

    # 4. Over-refund attempt: $31 exceeds remaining $30
    with pytest.raises(OverRefundError):
        service.refund_payment(
            actor=actor,
            payment_id=payment.payment_id,
            amount=Decimal("31.0000"),
            fine_id=fine.fine_id,
            reason="Exceeding refund cap",
        )

    # 5. Full refund of remaining $30
    refund_alloc_2 = service.refund_payment(
        actor=actor,
        payment_id=payment.payment_id,
        amount=Decimal("30.0000"),
        fine_id=fine.fine_id,
        reason="Full resolution",
    )
    assert refund_alloc_2.amount == Decimal("30.0000")

    # Payment transitions to refunded
    fully_refunded_payment = store.get_payment(org_id, payment.payment_id)
    assert fully_refunded_payment.status == PaymentStatus.REFUNDED

    # Fine net allocation is now $0 / $50 -> transitions back to assessed
    fully_unpaid_fine = store.get_fine(org_id, fine.fine_id)
    assert fully_unpaid_fine.status == FineStatus.ASSESSED


def test_payment_state_machine_valid_and_invalid_transitions() -> None:
    """Verify all allowed and forbidden payment state machine transitions."""
    service, store, _, _, org_id, member_id, actor = _build_test_setup()

    # Allowed: pending -> authorized -> succeeded -> partially_refunded -> refunded
    p1 = service.record_payment(
        actor=actor,
        member_id=member_id,
        amount=Decimal("100.0000"),
        currency="USD",
        initial_status=PaymentStatus.PENDING,
    )
    assert p1.status == PaymentStatus.PENDING

    p1 = service.transition_payment_status(
        actor=actor, payment_id=p1.payment_id, new_status=PaymentStatus.AUTHORIZED
    )
    assert p1.status == PaymentStatus.AUTHORIZED

    p1 = service.transition_payment_status(
        actor=actor, payment_id=p1.payment_id, new_status=PaymentStatus.SUCCEEDED
    )
    assert p1.status == PaymentStatus.SUCCEEDED

    p1 = service.transition_payment_status(
        actor=actor,
        payment_id=p1.payment_id,
        new_status=PaymentStatus.PARTIALLY_REFUNDED,
    )
    assert p1.status == PaymentStatus.PARTIALLY_REFUNDED

    p1 = service.transition_payment_status(
        actor=actor, payment_id=p1.payment_id, new_status=PaymentStatus.REFUNDED
    )
    assert p1.status == PaymentStatus.REFUNDED

    # Forbidden: refunded -> succeeded
    with pytest.raises(InvalidPaymentStateTransitionError):
        service.transition_payment_status(
            actor=actor, payment_id=p1.payment_id, new_status=PaymentStatus.SUCCEEDED
        )

    # Disputed flow: succeeded -> disputed -> succeeded
    p2 = service.record_payment(
        actor=actor,
        member_id=member_id,
        amount=Decimal("50.0000"),
        currency="USD",
        initial_status=PaymentStatus.SUCCEEDED,
    )
    p2 = service.transition_payment_status(
        actor=actor, payment_id=p2.payment_id, new_status=PaymentStatus.DISPUTED
    )
    assert p2.status == PaymentStatus.DISPUTED

    p2 = service.transition_payment_status(
        actor=actor, payment_id=p2.payment_id, new_status=PaymentStatus.SUCCEEDED
    )
    assert p2.status == PaymentStatus.SUCCEEDED


def test_sensitive_data_never_persisted_in_audit_or_events() -> None:
    """Verify raw body, secrets, credentials, and card numbers are never persisted."""
    service, store, audited_tx, provider, org_id, member_id, actor = _build_test_setup()

    _ = service.record_payment(
        actor=actor,
        member_id=member_id,
        amount=Decimal("60.0000"),
        currency="USD",
        provider="mock_provider",
        provider_reference="ch_secret_test",
        initial_status=PaymentStatus.PENDING,
    )

    sensitive_webhook_payload = {
        "event_id": "evt_sensitive_001",
        "event_type": "payment.succeeded",
        "provider_reference": "ch_secret_test",
        "amount": "60.0000",
        "currency": "USD",
        "card_number": "4111222233334444",
        "cvv": "999",
        "client_secret": "whsec_super_secret_never_leak",
    }
    raw_body = json.dumps(sensitive_webhook_payload).encode("utf-8")
    now_ts = int(datetime.now(timezone.utc).timestamp())
    sig = provider.generate_signature(raw_body, now_ts)
    headers = {
        "X-Webhook-Signature": sig,
        "X-Webhook-Timestamp": str(now_ts),
    }

    service.handle_payment_webhook(
        organization_id=org_id,
        provider="mock_provider",
        raw_body=raw_body,
        headers=headers,
        secret=provider.secret,
    )

    # 1. Audit payloads check
    for audit in audited_tx.recorded_audits:
        audit_str = json.dumps(audit.payload)
        assert "4111222233334444" not in audit_str
        assert "999" not in audit_str
        assert "whsec_super_secret" not in audit_str
        assert "raw_webhook_body" not in audit_str

    # 2. Outbox payloads check
    for outbox in audited_tx.recorded_outboxes:
        outbox_str = json.dumps(outbox.payload)
        assert "4111222233334444" not in outbox_str
        assert "999" not in outbox_str
        assert "whsec_super_secret" not in outbox_str
        assert "raw_webhook_body" not in outbox_str

    # 3. PaymentEvent store check: stores payload_hash, never raw_body or secrets!
    event = store.get_payment_event(org_id, "mock_provider", "evt_sensitive_001")
    assert event is not None
    assert event.payload_hash == hashlib.sha256(raw_body).hexdigest()
    assert not hasattr(event, "raw_body")
