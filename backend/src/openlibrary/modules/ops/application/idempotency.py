"""Application contracts and service for request idempotency and response replay."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Protocol
from uuid import UUID, uuid4

from openlibrary.modules.ops.application.persistence import (
    AuditEvent,
    _reject_sensitive_keys,
)


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    """One durable idempotency record linking a tenant request to its original response."""

    key_id: UUID
    organization_id: UUID
    key: str
    method: str
    endpoint: str
    request_hash: str
    status_code: int
    safe_response_json: str
    created_at: datetime
    expires_at: datetime
    resource_reference: str | None = None


class IdempotencyConflictError(Exception):
    """Raised when an idempotency key is reused with a different request payload."""

    def __init__(
        self,
        message: str = "Idempotency key already used with a different request payload.",
    ) -> None:
        super().__init__(message)
        self.status_code = 409
        self.title = "Idempotency conflict"
        self.problem_type = (
            "https://openlibraryos.example/problems/idempotency-conflict"
        )


def compute_request_hash(payload: object) -> str:
    """Produce a deterministic SHA-256 hash of the canonical JSON request payload."""
    effective: object
    if payload is None:
        effective = {}
    elif isinstance(payload, (Mapping, list)):
        effective = payload
    else:
        effective = {"value": str(payload)}

    canonical_json = json.dumps(effective, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def validate_safe_response(response_body: Mapping[str, object] | object) -> str:
    """Validate and serialize response representation, banning secrets, tokens, or card data."""
    if isinstance(response_body, Mapping):
        _reject_sensitive_keys(dict(response_body))
    try:
        return json.dumps(response_body, separators=(",", ":"), sort_keys=True)
    except (TypeError, ValueError) as error:
        raise ValueError("response body must be JSON serializable") from error


class IdempotencyStore(Protocol):
    """Persistence port for tenant-scoped idempotency keys."""

    def get_record(
        self, organization_id: UUID, key: str, method: str, endpoint: str
    ) -> IdempotencyRecord | None: ...

    def save_record(
        self,
        *,
        key_id: UUID,
        organization_id: UUID,
        key: str,
        method: str,
        endpoint: str,
        request_hash: str,
        resource_reference: str | None,
        status_code: int,
        safe_response_json: str,
        created_at: datetime,
        expires_at: datetime,
    ) -> IdempotencyRecord: ...

    def delete_record(self, organization_id: UUID, key_id: UUID) -> None: ...


@dataclass(frozen=True, slots=True)
class IdempotencyResult:
    """Outcome of an idempotent execution attempt."""

    replayed: bool
    status_code: int
    body: dict[str, Any]
    resource_reference: str | None = None


AuditRecorder = Callable[[AuditEvent], None]


class IdempotencyService:
    """Coordinates request deduplication, canonical hash validation, and safe replay."""

    _DEFAULT_TTL = timedelta(hours=24)

    def __init__(
        self,
        store: IdempotencyStore,
        audit_recorder: AuditRecorder | None = None,
    ) -> None:
        self._store = store
        self._audit_recorder = audit_recorder

    def process_or_replay(
        self,
        *,
        organization_id: UUID,
        key: str,
        method: str,
        endpoint: str,
        request_payload: object,
        execute: Callable[[], tuple[int, dict[str, Any], str | None]],
        correlation_id: UUID | None = None,
        actor_user_id: UUID | None = None,
    ) -> IdempotencyResult:
        """Execute mutation or return cached safe response if the key was already processed."""
        clean_key = key.strip()
        if not clean_key or len(clean_key) > 128:
            raise ValueError("Idempotency key must be between 1 and 128 characters.")

        normalized_method = method.strip().upper()
        normalized_endpoint = endpoint.strip()
        request_hash = compute_request_hash(request_payload)

        now = datetime.now(timezone.utc)
        existing = self._store.get_record(
            organization_id, clean_key, normalized_method, normalized_endpoint
        )

        if existing is not None:
            # Check 24-hour expiration
            if now < existing.expires_at:
                # Key is active: check payload hash equality
                if existing.request_hash != request_hash:
                    # Explicit mismatch: write audit event and reject with 409
                    if self._audit_recorder is not None:
                        audit_event = AuditEvent(
                            action="idempotency.request_hash_mismatch",
                            entity_type="idempotency_key",
                            entity_id=existing.key_id,
                            payload={
                                "idempotency_key": existing.key,
                                "method": existing.method,
                                "endpoint": existing.endpoint,
                                "existing_hash": existing.request_hash,
                                "incoming_hash": request_hash,
                            },
                            correlation_id=correlation_id or uuid4(),
                            actor_user_id=actor_user_id,
                            actor_type="user" if actor_user_id else "system",
                        )
                        self._audit_recorder(audit_event)

                    raise IdempotencyConflictError(
                        "Idempotency key already used with a different request payload."
                    )

                # Replay original result without executing side effects
                replayed_body = json.loads(existing.safe_response_json)
                return IdempotencyResult(
                    replayed=True,
                    status_code=existing.status_code,
                    body=replayed_body,
                    resource_reference=existing.resource_reference,
                )

            # Record has expired (> 24 hours): clean it up so it does not suppress the new request
            self._store.delete_record(organization_id, existing.key_id)

        # First request or previous record expired: execute the business mutation
        status_code, response_body, resource_reference = execute()

        safe_json = validate_safe_response(response_body)
        key_id = uuid4()
        expires_at = now + self._DEFAULT_TTL

        self._store.save_record(
            key_id=key_id,
            organization_id=organization_id,
            key=clean_key,
            method=normalized_method,
            endpoint=normalized_endpoint,
            request_hash=request_hash,
            resource_reference=resource_reference,
            status_code=status_code,
            safe_response_json=safe_json,
            created_at=now,
            expires_at=expires_at,
        )

        return IdempotencyResult(
            replayed=False,
            status_code=status_code,
            body=response_body,
            resource_reference=resource_reference,
        )
