"""Payment webhook verification, provider protocols, and replay protection."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import hmac
from typing import Protocol
from uuid import UUID

from openlibrary.modules.public_library.domain import (
    InvalidWebhookSignatureError,
    MissingWebhookSignatureError,
    StaleWebhookTimestampError,
)


@dataclass(frozen=True, slots=True)
class ProviderPaymentStatusResult:
    """The normalized status result returned when querying a payment provider."""

    provider_reference: str
    status: str
    amount: Decimal
    currency: str
    paid_at: datetime | None = None
    failure_reason: str | None = None


class PaymentProviderPort(Protocol):
    """Port for querying payment provider status out of band."""

    def get_payment_status(
        self,
        *,
        provider: str,
        provider_reference: str,
    ) -> ProviderPaymentStatusResult:
        """Query the remote payment provider for the current status of a reference."""
        ...

    def get_webhook_secret(
        self,
        *,
        organization_id: UUID,
        provider: str,
    ) -> str:
        """Retrieve the webhook signing secret for the provider and organization."""
        ...


class WebhookSignatureVerifier:
    """Verifies provider signature and timestamp on raw request bytes before parsing."""

    def __init__(self, tolerance_seconds: int = 300) -> None:
        self._tolerance_seconds = tolerance_seconds

    def verify(
        self,
        *,
        provider: str,
        raw_body: bytes,
        headers: Mapping[str, str],
        secret: str,
        current_time: datetime | None = None,
    ) -> None:
        """Verify signature and replay window.

        Raises:
            MissingWebhookSignatureError: If headers lack timestamp or signature.
            StaleWebhookTimestampError: If timestamp is outside replay tolerance.
            InvalidWebhookSignatureError: If signature check fails.
        """
        del provider
        now = current_time or datetime.now(timezone.utc)
        timestamp_str, raw_signature = self._extract_headers(headers)

        timestamp_dt = self._parse_timestamp(timestamp_str)
        delta_seconds = abs((now - timestamp_dt).total_seconds())
        if delta_seconds > self._tolerance_seconds:
            raise StaleWebhookTimestampError(
                f"Webhook timestamp outside allowed replay window of {self._tolerance_seconds}s (delta: {delta_seconds:.1f}s)"
            )

        if not self._check_signature(raw_body, timestamp_str, raw_signature, secret):
            raise InvalidWebhookSignatureError(
                "Webhook signature verification failed on raw request body"
            )

    def _extract_headers(self, headers: Mapping[str, str]) -> tuple[str, str]:
        # Case-insensitive header lookup
        normalized = {k.lower(): v for k, v in headers.items()}

        # 1. Check for combined Stripe-style signature header: t=12345678,v1=abcdef...
        sig_header = (
            normalized.get("stripe-signature")
            or normalized.get("x-signature")
            or normalized.get("x-webhook-signature")
            or normalized.get("x-hub-signature-256")
        )
        timestamp_header = (
            normalized.get("x-webhook-timestamp")
            or normalized.get("x-timestamp")
            or normalized.get("x-signature-timestamp")
        )

        if sig_header and ("t=" in sig_header or "v1=" in sig_header):
            parts = sig_header.split(",")
            t_val: str | None = None
            v1_val: str | None = None
            for p in parts:
                p_clean = p.strip()
                if p_clean.startswith("t="):
                    t_val = p_clean[2:]
                elif p_clean.startswith("v1="):
                    v1_val = p_clean[3:]
                elif p_clean.startswith("sha256="):
                    v1_val = p_clean[7:]
            if t_val and v1_val:
                return t_val, v1_val
            if v1_val and timestamp_header:
                return timestamp_header, v1_val

        if not timestamp_header:
            raise StaleWebhookTimestampError("Missing webhook timestamp header")
        if not sig_header:
            raise MissingWebhookSignatureError("Missing webhook signature header")

        sig_val = sig_header.strip()
        if sig_val.startswith("sha256="):
            sig_val = sig_val[7:]
        elif sig_val.startswith("v1="):
            sig_val = sig_val[3:]

        return timestamp_header.strip(), sig_val

    def _parse_timestamp(self, ts_str: str) -> datetime:
        try:
            # Check integer or float Unix epoch timestamp
            epoch_val = float(ts_str)
            return datetime.fromtimestamp(epoch_val, tz=timezone.utc)
        except ValueError:
            pass

        try:
            # Check ISO format
            dt = datetime.fromisoformat(ts_str)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError as err:
            raise StaleWebhookTimestampError(
                f"Invalid webhook timestamp format: {ts_str}"
            ) from err

    def _check_signature(
        self,
        raw_body: bytes,
        timestamp_str: str,
        received_signature: str,
        secret: str,
    ) -> bool:
        secret_bytes = secret.encode("utf-8")
        candidates = [
            # Stripe standard: timestamp.payload
            f"{timestamp_str}.".encode("utf-8") + raw_body,
            # Payload directly
            raw_body,
            # Timestamp directly concatenated
            f"{timestamp_str}".encode("utf-8") + raw_body,
        ]

        clean_received = received_signature.lower().strip()
        for candidate in candidates:
            expected = hmac.new(secret_bytes, candidate, hashlib.sha256).hexdigest()
            if hmac.compare_digest(expected, clean_received):
                return True
        return False
