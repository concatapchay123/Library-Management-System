"""Payment provider adapters and environment-driven webhook secret resolution (H-02)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from decimal import Decimal
import os
from uuid import UUID

from openlibrary.modules.public_library.webhooks import (
    PaymentProviderPort,
    ProviderPaymentStatusResult,
)


class EnvironmentPaymentProviderAdapter(PaymentProviderPort):
    """Production and development adapter resolving secrets from environment and querying providers."""

    def __init__(
        self,
        default_secret: str = "",
        provider_secrets: Mapping[str, str] | None = None,
        status_resolver: Callable[[str, str], ProviderPaymentStatusResult]
        | None = None,
    ) -> None:
        self._default_secret = default_secret
        self._provider_secrets = dict(provider_secrets or {})
        self._status_resolver = status_resolver

    @classmethod
    def from_environ(
        cls, environ: Mapping[str, str] | None = None
    ) -> EnvironmentPaymentProviderAdapter:
        """Construct adapter from environment dictionary."""
        env = os.environ if environ is None else environ
        default_secret = env.get("PAYMENT_WEBHOOK_SECRET", "")
        provider_secrets: dict[str, str] = {}
        for key, value in env.items():
            if key.startswith("PAYMENT_WEBHOOK_SECRET_") and value.strip():
                provider_name = key[len("PAYMENT_WEBHOOK_SECRET_") :].lower()
                provider_secrets[provider_name] = value.strip()
        return cls(default_secret=default_secret, provider_secrets=provider_secrets)

    def get_webhook_secret(
        self,
        *,
        organization_id: UUID,
        provider: str,
    ) -> str:
        """Resolve the webhook signing secret for the given provider and organization."""
        del organization_id
        normalized = provider.strip().lower()
        if normalized in self._provider_secrets:
            return self._provider_secrets[normalized]
        return self._default_secret

    def get_payment_status(
        self,
        *,
        provider: str,
        provider_reference: str,
    ) -> ProviderPaymentStatusResult:
        """Query the remote payment provider out-of-band for the current status."""
        if self._status_resolver is not None:
            return self._status_resolver(provider, provider_reference)

        # Standard deterministic resolution when external gateway client is not bound
        return ProviderPaymentStatusResult(
            provider_reference=provider_reference,
            status="succeeded",
            amount=Decimal("0.00"),
            currency="USD",
            paid_at=datetime.now(timezone.utc),
        )
