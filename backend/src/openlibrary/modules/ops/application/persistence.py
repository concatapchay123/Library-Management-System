"""Application contracts for an audited transactional mutation."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
import json
import re
from typing import Protocol, TypeVar
from uuid import UUID, uuid4

from sqlalchemy.engine import Connection


T = TypeVar("T")
_SENSITIVE_KEY = re.compile(r"[^a-z0-9]")
_SENSITIVE_NAMES = frozenset(
    {
        "apikey",
        "authorization",
        "cardnumber",
        "cardpan",
        "clientsecret",
        "cvc",
        "cvv",
        "idtoken",
        "pan",
        "password",
        "passwordhash",
        "paymentpayload",
        "rawpaymentpayload",
        "refreshtoken",
        "secret",
        "token",
    }
)


def serialize_event_payload(payload: Mapping[str, object]) -> str:
    """Validate and produce canonical JSON before a durable write can occur."""
    _reject_sensitive_keys(payload)
    try:
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)
    except (TypeError, ValueError) as error:
        raise ValueError("event payload must be JSON serializable") from error


def _reject_sensitive_keys(value: object) -> None:
    """Reject recursively nested credential fields from durable event payloads."""
    if isinstance(value, Mapping):
        for key, nested_value in value.items():
            if not isinstance(key, str):
                raise ValueError("event payload keys must be strings")
            normalized_key = _SENSITIVE_KEY.sub("", key.casefold())
            if (
                normalized_key in _SENSITIVE_NAMES
                or normalized_key.endswith("token")
                or "secret" in normalized_key
            ):
                raise ValueError(f"sensitive event payload field: {key}")
            _reject_sensitive_keys(nested_value)
    elif isinstance(value, (list, tuple)):
        for nested_value in value:
            _reject_sensitive_keys(nested_value)


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """One immutable audit record that documents a protected mutation."""

    action: str
    entity_type: str
    entity_id: UUID
    payload: Mapping[str, object]
    correlation_id: UUID
    actor_user_id: UUID | None = None
    actor_type: str = "system"
    payload_version: int = 1
    audit_id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        _validate_event_metadata(
            action=self.action,
            entity_type=self.entity_type,
            payload_version=self.payload_version,
        )
        serialize_event_payload(self.payload)


@dataclass(frozen=True, slots=True)
class OutboxEvent:
    """One durable asynchronous effect emitted with a protected mutation."""

    event_type: str
    aggregate_type: str
    aggregate_id: UUID
    payload_version: int
    payload: Mapping[str, object]
    correlation_id: UUID
    idempotency_key: str
    event_id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        _validate_event_metadata(
            action=self.event_type,
            entity_type=self.aggregate_type,
            payload_version=self.payload_version,
        )
        if not self.idempotency_key.strip():
            raise ValueError("outbox idempotency key must not be empty")
        serialize_event_payload(self.payload)


def _validate_event_metadata(
    *, action: str, entity_type: str, payload_version: int
) -> None:
    if not action.strip():
        raise ValueError("event action must not be empty")
    if not entity_type.strip():
        raise ValueError("event entity type must not be empty")
    if payload_version <= 0:
        raise ValueError("event payload version must be positive")


class AuditedTransaction(Protocol):
    """Port that atomically writes a mutation and its operational evidence."""

    def run(
        self,
        connection: Connection,
        mutation: Callable[[Connection], T],
        audit_event: AuditEvent,
        outbox_events: Sequence[OutboxEvent],
    ) -> T:
        """Write all protected records atomically in the caller's transaction."""
