"""Application service and ports for copy status transitions and history."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID, uuid4

from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.authorization import (
    AuthorizationDenied,
    AuthorizationPort,
)
from openlibrary.modules.core.application.inventory import BookCopy
from openlibrary.modules.core.domain.copy_status import validate_transition
from openlibrary.modules.ops.application.persistence import (
    AuditEvent,
    AuditedTransaction,
)


@dataclass(frozen=True, slots=True)
class CopyStatusHistory:
    """An immutable, append-only record of a physical copy status transition."""

    history_id: UUID
    organization_id: UUID
    copy_id: UUID
    from_status: str
    to_status: str
    reason: str
    actor_id: UUID
    created_at: datetime


class CopyStatusStore(Protocol):
    """Persistence port for copy status and append-only status history."""

    def get_copy(self, organization_id: UUID, copy_id: UUID) -> BookCopy: ...

    def update_copy_status(
        self,
        organization_id: UUID,
        copy_id: UUID,
        to_status: str,
    ) -> BookCopy: ...

    def append_history(self, record: CopyStatusHistory) -> CopyStatusHistory: ...

    def list_history_for_copy(
        self, organization_id: UUID, copy_id: UUID
    ) -> list[CopyStatusHistory]: ...

    def get_copy_for_update_in_connection(
        self, connection: Any, organization_id: UUID, copy_id: UUID
    ) -> BookCopy: ...

    def get_available_copy_for_book(
        self, organization_id: UUID, book_id: UUID
    ) -> BookCopy | None: ...


class CopyStatusService:
    """Orchestrate copy status transitions, history retention, and audit recording."""

    _MANAGE_PERMISSION = "inventory.manage"
    _READ_PERMISSIONS = ("inventory.manage", "inventory.read", "catalog.read")

    def __init__(
        self,
        *,
        store: CopyStatusStore,
        authorizer: AuthorizationPort,
        transaction: AuditedTransaction | None = None,
        connection_provider: Callable[[UUID], AbstractContextManager[object]]
        | None = None,
    ) -> None:
        self._store = store
        self._authorizer = authorizer
        self._transaction = transaction
        self._connection_provider = connection_provider

    def _require_manage(self, actor: Principal) -> None:
        self._authorizer.require(actor, self._MANAGE_PERMISSION)

    def _require_read(self, actor: Principal) -> None:
        for perm in self._READ_PERMISSIONS:
            try:
                self._authorizer.require(actor, perm)
                return
            except AuthorizationDenied:
                continue
        raise AuthorizationDenied("inventory.manage or catalog.read required")

    def transition_status(
        self,
        *,
        actor: Principal,
        copy_id: UUID,
        to_status: str,
        reason: str,
        correlation_id: UUID | None = None,
    ) -> BookCopy:
        """Validate and atomically apply an allowed copy status transition with history and audit."""
        if actor.user_id is None:
            raise ValueError("Actor user_id is required for manual inventory changes")

        self._require_manage(actor)

        cleaned_reason = _clean_string(reason, "transition reason", 500)
        current_copy = self._store.get_copy(actor.organization_id, copy_id)

        validate_transition(current_copy.status, to_status)

        now = datetime.now(timezone.utc)
        history_record = CopyStatusHistory(
            history_id=uuid4(),
            organization_id=actor.organization_id,
            copy_id=copy_id,
            from_status=current_copy.status,
            to_status=to_status,
            reason=cleaned_reason,
            actor_id=actor.user_id,
            created_at=now,
        )

        audit_correlation = correlation_id or uuid4()
        audit_event = AuditEvent(
            action="copy.status_changed",
            entity_type="copy",
            entity_id=copy_id,
            payload={
                "copy_id": str(copy_id),
                "from_status": current_copy.status,
                "to_status": to_status,
                "reason": cleaned_reason,
            },
            correlation_id=audit_correlation,
            actor_user_id=actor.user_id,
            actor_type="user",
        )

        def _mutation(connection: object) -> BookCopy:
            if hasattr(self._store, "record_transition_in_connection"):
                return self._store.record_transition_in_connection(  # type: ignore[no-any-return]
                    connection,
                    organization_id=actor.organization_id,
                    copy_id=copy_id,
                    to_status=to_status,
                    history_record=history_record,
                )
            updated = self._store.update_copy_status(
                actor.organization_id, copy_id, to_status
            )
            self._store.append_history(history_record)
            return updated

        if self._transaction is not None:
            if self._connection_provider is not None:
                with self._connection_provider(actor.organization_id) as conn:
                    return self._transaction.run(
                        conn,  # type: ignore[arg-type]
                        _mutation,
                        audit_event,
                        (),
                    )
            return self._transaction.run(
                None,  # type: ignore[arg-type]
                _mutation,
                audit_event,
                (),
            )

        # Fallback if no AuditedTransaction port is injected
        return _mutation(None)

    def list_copy_history(
        self,
        *,
        actor: Principal,
        copy_id: UUID,
    ) -> list[CopyStatusHistory]:
        """Return actor-attributed transition history for one copy within the tenant."""
        self._require_read(actor)
        return self._store.list_history_for_copy(actor.organization_id, copy_id)


def _clean_string(value: str, label: str, max_length: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Invalid {label}: expected string")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > max_length:
        raise ValueError(
            f"Invalid {label}: must be between 1 and {max_length} characters"
        )
    return cleaned
