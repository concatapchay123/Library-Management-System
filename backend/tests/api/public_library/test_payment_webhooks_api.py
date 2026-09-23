"""HTTP API contract and integration tests for payment webhooks, refund, and reconciliation."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json
from uuid import uuid4

from flask import Flask

from openlibrary.app.correlation import install_request_correlation
from openlibrary.app.errors import install_problem_details_handlers
from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.public_library.api import create_public_library_blueprint
from openlibrary.modules.public_library.application import (
    PublicLibraryFinanceService,
    PublicLibraryService,
)
from openlibrary.modules.public_library.domain import (
    AllocationType,
    Member,
    MemberStatus,
    PaymentStatus,
)
from openlibrary.modules.public_library.webhooks import (
    ProviderPaymentStatusResult,
    WebhookSignatureVerifier,
)
from tests.integration.public_library.test_payments import (
    _AllowAllAuthorizer,
    _InMemoryPaymentsStore,
    _RecordingAuditedTransaction,
    _StubPaymentProvider,
)


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


def _setup_api_test():
    org_id = uuid4()
    user_id = uuid4()
    principal = Principal(user_id=user_id, organization_id=org_id, session_id=uuid4())
    access_tokens = _StubAccessTokenService(principal)
    authorizer = _AllowAllAuthorizer()
    store = _InMemoryPaymentsStore(edition_enabled_orgs={org_id})
    audited_tx = _RecordingAuditedTransaction()
    provider = _StubPaymentProvider()
    verifier = WebhookSignatureVerifier(tolerance_seconds=300)

    member = Member(
        member_id=uuid4(),
        organization_id=org_id,
        user_id=user_id,
        member_number="MEM-API-001",
        status=MemberStatus.ACTIVE,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    store.create_member(member)

    fin_service = PublicLibraryFinanceService(
        store=store,
        authorizer=authorizer,
        transaction=audited_tx,
        clock=lambda: datetime.now(timezone.utc),
        payment_provider=provider,
        webhook_verifier=verifier,
    )
    pub_service = PublicLibraryService(store=store, authorizer=authorizer)

    app = Flask(__name__)
    install_request_correlation(app)
    install_problem_details_handlers(app)

    app.register_blueprint(
        create_public_library_blueprint(
            service=pub_service,
            access_tokens=access_tokens,  # type: ignore[arg-type]
            tenant_request_context=None,
            url_prefix="/api/v1/public-library",
            finance_service=fin_service,
        )
    )

    client = app.test_client()
    return client, org_id, member.member_id, fin_service, provider, store, principal


def test_webhook_endpoint_no_auth_header_required() -> None:
    """The webhook endpoint must not require a browser access token or session."""
    client, org_id, member_id, fin_service, provider, store, principal = (
        _setup_api_test()
    )

    ref = "ref_no_auth_test"
    payment = fin_service.record_payment(
        actor=principal,
        member_id=member_id,
        amount=Decimal("15.0000"),
        currency="USD",
        provider="mock_provider",
        provider_reference=ref,
        initial_status=PaymentStatus.PENDING,
    )

    payload = {
        "event_id": "evt_webhook_no_auth_1",
        "provider_reference": ref,
        "event_type": "payment.succeeded",
        "amount": "15.0000",
        "currency": "USD",
    }
    raw_body = json.dumps(payload).encode("utf-8")
    now_ts = int(datetime.now(timezone.utc).timestamp())
    signature = provider.generate_signature(raw_body, now_ts)

    resp = client.post(
        f"/api/v1/public-library/payments/webhooks/mock_provider?organization_id={org_id}",
        data=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Signature": signature,
            "X-Webhook-Timestamp": str(now_ts),
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["payment_id"] == str(payment.payment_id)
    assert data["status"] == PaymentStatus.SUCCEEDED


def test_webhook_missing_organization_id_returns_400() -> None:
    client, _, _, _, _, _, _ = _setup_api_test()

    resp = client.post(
        "/api/v1/public-library/payments/webhooks/mock_provider",
        data=b"{}",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400
    assert resp.mimetype == "application/problem+json"


def test_webhook_missing_signature_returns_400() -> None:
    client, org_id, _, _, _, _, _ = _setup_api_test()

    resp = client.post(
        f"/api/v1/public-library/payments/webhooks/mock_provider?organization_id={org_id}",
        data=b'{"test": 1}',
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400
    assert resp.mimetype == "application/problem+json"


def test_webhook_invalid_signature_returns_401() -> None:
    client, org_id, _, _, _, _, _ = _setup_api_test()
    now_ts = int(datetime.now(timezone.utc).timestamp())

    resp = client.post(
        f"/api/v1/public-library/payments/webhooks/mock_provider?organization_id={org_id}",
        data=b'{"test": 1}',
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Signature": "invalid_sig_deadbeef12345678",
            "X-Webhook-Timestamp": str(now_ts),
        },
    )
    assert resp.status_code == 401
    assert resp.mimetype == "application/problem+json"
    data = resp.get_json()
    assert "Invalid Webhook Signature" in data["title"]


def test_webhook_stale_timestamp_returns_400() -> None:
    client, org_id, _, _, provider, _, _ = _setup_api_test()
    stale_ts = int(datetime.now(timezone.utc).timestamp()) - 400
    raw_body = b'{"test": 1}'
    sig = provider.generate_signature(raw_body, stale_ts)

    resp = client.post(
        f"/api/v1/public-library/payments/webhooks/mock_provider?organization_id={org_id}",
        data=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Signature": sig,
            "X-Webhook-Timestamp": str(stale_ts),
        },
    )
    assert resp.status_code == 400
    assert resp.mimetype == "application/problem+json"


def test_webhook_duplicate_event_is_idempotent() -> None:
    """Duplicate provider webhook events must return 200 without changing state twice."""
    client, org_id, member_id, fin_service, provider, store, principal = (
        _setup_api_test()
    )

    ref = "ref_dup_webhook"
    _ = fin_service.record_payment(
        actor=principal,
        member_id=member_id,
        amount=Decimal("25.0000"),
        currency="USD",
        provider="mock_provider",
        provider_reference=ref,
        initial_status=PaymentStatus.PENDING,
    )

    payload = {
        "event_id": "evt_dup_101",
        "provider_reference": ref,
        "event_type": "payment.succeeded",
        "amount": "25.0000",
        "currency": "USD",
    }
    raw_body = json.dumps(payload).encode("utf-8")
    now_ts = int(datetime.now(timezone.utc).timestamp())
    sig = provider.generate_signature(raw_body, now_ts)

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": sig,
        "X-Webhook-Timestamp": str(now_ts),
    }

    # First call
    resp1 = client.post(
        f"/api/v1/public-library/payments/webhooks/mock_provider?organization_id={org_id}",
        data=raw_body,
        headers=headers,
    )
    assert resp1.status_code == 200

    # Second call (replay)
    resp2 = client.post(
        f"/api/v1/public-library/payments/webhooks/mock_provider?organization_id={org_id}",
        data=raw_body,
        headers=headers,
    )
    assert resp2.status_code == 200
    assert resp2.get_json()["status"] == PaymentStatus.SUCCEEDED


def test_refund_endpoint_requires_auth_and_succeeds() -> None:
    client, org_id, member_id, fin_service, _, store, principal = _setup_api_test()

    payment = fin_service.record_payment(
        actor=principal,
        member_id=member_id,
        amount=Decimal("50.0000"),
        currency="USD",
        provider="manual",
        initial_status=PaymentStatus.SUCCEEDED,
    )

    # 1. Unauthenticated -> 401
    resp_unauth = client.post(
        f"/api/v1/public-library/payments/{payment.payment_id}/refund",
        json={"amount": "20.0000", "reason": "Defective item"},
    )
    assert resp_unauth.status_code == 401

    # 2. Authenticated -> 201
    resp_auth = client.post(
        f"/api/v1/public-library/payments/{payment.payment_id}/refund",
        json={"amount": "20.0000", "reason": "Defective item"},
        headers={"Authorization": "Bearer valid-token"},
    )
    assert resp_auth.status_code == 201
    data = resp_auth.get_json()
    assert data["amount"] == "20.0000"
    assert data["allocation_type"] == AllocationType.REFUND

    # Check payment state is now partially_refunded
    updated = store.get_payment(org_id, payment.payment_id)
    assert updated is not None
    assert updated.status == PaymentStatus.PARTIALLY_REFUNDED


def test_refund_endpoint_over_refund_returns_409() -> None:
    client, org_id, member_id, fin_service, _, store, principal = _setup_api_test()

    payment = fin_service.record_payment(
        actor=principal,
        member_id=member_id,
        amount=Decimal("30.0000"),
        currency="USD",
        provider="manual",
        initial_status=PaymentStatus.SUCCEEDED,
    )

    # Attempt to refund $35 on a $30 payment
    resp = client.post(
        f"/api/v1/public-library/payments/{payment.payment_id}/refund",
        json={"amount": "35.0000", "reason": "Too much"},
        headers={"Authorization": "Bearer valid-token"},
    )
    assert resp.status_code == 409
    assert resp.mimetype == "application/problem+json"


def test_reconcile_endpoint_requires_auth_and_succeeds() -> None:
    client, org_id, member_id, fin_service, provider, store, principal = (
        _setup_api_test()
    )

    ref = "ref_recon_api"
    payment = fin_service.record_payment(
        actor=principal,
        member_id=member_id,
        amount=Decimal("60.0000"),
        currency="USD",
        provider="mock_provider",
        provider_reference=ref,
        initial_status=PaymentStatus.PENDING,
    )

    provider.status_responses[("mock_provider", ref)] = ProviderPaymentStatusResult(
        provider_reference=ref,
        status=PaymentStatus.SUCCEEDED,
        amount=Decimal("60.0000"),
        currency="USD",
        paid_at=datetime.now(timezone.utc),
    )

    # 1. Unauthenticated -> 401
    resp_unauth = client.post(
        f"/api/v1/public-library/payments/{payment.payment_id}/reconcile"
    )
    assert resp_unauth.status_code == 401

    # 2. Authenticated -> 200
    resp_auth = client.post(
        f"/api/v1/public-library/payments/{payment.payment_id}/reconcile",
        headers={"Authorization": "Bearer valid-token"},
    )
    assert resp_auth.status_code == 200
    data = resp_auth.get_json()
    assert data["status"] == PaymentStatus.SUCCEEDED
    assert data["payment_id"] == str(payment.payment_id)
