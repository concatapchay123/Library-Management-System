"""Email delivery adapter interface, value objects, and development sink."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import logging
from typing import Protocol
from uuid import UUID, uuid4


_LOGGER = logging.getLogger(__name__)


class EmailDeliveryError(RuntimeError):
    """Raised when an email delivery attempt fails."""


@dataclass(frozen=True, slots=True)
class EmailMessage:
    """One immutable email payload targeted to a recipient address."""

    to_address: str
    subject: str
    body_text: str
    body_html: str | None = None
    organization_id: UUID | None = None
    event_id: UUID | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EmailDeliveryResult:
    """The deterministic outcome of a delivery attempt."""

    success: bool
    message_id: str | None = None
    error_message: str | None = None


class EmailPort(Protocol):
    """Replaceable adapter interface for sending notification emails."""

    def send(self, message: EmailMessage) -> EmailDeliveryResult:
        """Send one email message or raise EmailDeliveryError."""
        ...


class DevelopmentEmailSink(EmailPort):
    """In-memory email delivery sink for deterministic testing and local development."""

    def __init__(self) -> None:
        self._deliveries: list[EmailMessage] = []
        self._failure_count: int = 0
        self._failure_error: Exception | None = None

    def simulate_failure(self, count: int = 1, error: Exception | None = None) -> None:
        """Configure the next count sends to fail with the specified error."""
        self._failure_count = count
        self._failure_error = error or EmailDeliveryError("Simulated delivery failure")

    def send(self, message: EmailMessage) -> EmailDeliveryResult:
        """Record the message in memory or simulate provider failure."""
        if self._failure_count > 0:
            self._failure_count -= 1
            err = self._failure_error or EmailDeliveryError(
                "Simulated delivery failure"
            )
            _LOGGER.warning(
                "Simulating email delivery failure for %s: %s",
                message.to_address,
                err,
            )
            raise err

        self._deliveries.append(message)
        message_id = f"dev-mail-{uuid4()}"
        _LOGGER.info(
            "Delivered development email to %s (subject: %s, message_id: %s)",
            message.to_address,
            message.subject,
            message_id,
        )
        return EmailDeliveryResult(success=True, message_id=message_id)

    def get_deliveries(self) -> list[EmailMessage]:
        """Return a copy of all delivered email messages in receipt order."""
        return list(self._deliveries)

    def get_deliveries_for(self, email: str) -> list[EmailMessage]:
        """Filter deliveries for a specific recipient email address."""
        normalized = email.strip().casefold()
        return [
            m for m in self._deliveries if m.to_address.strip().casefold() == normalized
        ]

    def clear(self) -> None:
        """Clear recorded deliveries and reset simulated failures."""
        self._deliveries.clear()
        self._failure_count = 0
        self._failure_error = None
