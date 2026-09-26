"""Tests for PaymentProviderPort adapter and reconciliation wiring (H-02)."""

from decimal import Decimal
from uuid import uuid4
from openlibrary.modules.public_library.providers import (
    EnvironmentPaymentProviderAdapter,
)
from openlibrary.modules.public_library.webhooks import ProviderPaymentStatusResult


def test_provider_resolves_webhook_secret_from_env() -> None:
    adapter = EnvironmentPaymentProviderAdapter(
        default_secret="default-wh-secret",
        provider_secrets={"stripe": "whsec_stripe_123"},
    )
    org_id = uuid4()

    # Provider specific
    assert (
        adapter.get_webhook_secret(organization_id=org_id, provider="stripe")
        == "whsec_stripe_123"
    )
    # Default fallback
    assert (
        adapter.get_webhook_secret(organization_id=org_id, provider="generic")
        == "default-wh-secret"
    )


def test_provider_returns_payment_status() -> None:
    adapter = EnvironmentPaymentProviderAdapter(default_secret="secret")
    status = adapter.get_payment_status(
        provider="stripe", provider_reference="ch_12345"
    )

    assert isinstance(status, ProviderPaymentStatusResult)
    assert status.provider_reference == "ch_12345"
    assert status.status in ("pending", "succeeded", "failed")
    assert status.amount >= Decimal("0")
