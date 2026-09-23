"""Unit and domain tests for copy status transitions and append-only history."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TypeVar
from uuid import UUID, uuid4

import pytest

from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.authorization import (
    AuthorizationDenied,
    AuthorizationPort,
)
from openlibrary.modules.core.application.copy_status import (
    CopyStatusHistory,
    CopyStatusService,
    CopyStatusStore,
)
from openlibrary.modules.core.application.inventory import BookCopy
from openlibrary.modules.core.domain.copy_status import (
    ALLOWED_TRANSITIONS,
    CopyStatus,
    InvalidCopyStatusTransitionError,
    is_allowed_transition,
    validate_transition,
)
from openlibrary.modules.ops.application.persistence import (
    AuditEvent,
    AuditedTransaction,
    OutboxEvent,
)

T = TypeVar("T")

ORG_A = uuid4()
ORG_B = uuid4()
USER_A = uuid4()
USER_B = uuid4()
ACTOR_A = Principal(user_id=USER_A, organization_id=ORG_A, session_id=uuid4())
ACTOR_B = Principal(user_id=USER_B, organization_id=ORG_B, session_id=uuid4())


# ---------------------------------------------------------------------------
# In-Memory Test Doubles
# ---------------------------------------------------------------------------


class _AllowAllAuthorizer(AuthorizationPort):
    def require(self, principal: Principal, permission: str) -> None:
        pass


class _DenyAllAuthorizer(AuthorizationPort):
    def require(self, principal: Principal, permission: str) -> None:
        raise AuthorizationDenied(f"Permission denied: {permission}")


class _SelectiveAuthorizer(AuthorizationPort):
    def __init__(self, allowed_permissions: set[str]) -> None:
        self.allowed = allowed_permissions

    def require(self, principal: Principal, permission: str) -> None:
        if permission not in self.allowed:
            raise AuthorizationDenied(f"Permission denied: {permission}")


@dataclass
class _InMemoryCopyStatusStore(CopyStatusStore):
    copies: dict[UUID, BookCopy] = field(default_factory=dict)
    history: list[CopyStatusHistory] = field(default_factory=list)

    def get_copy(self, organization_id: UUID, copy_id: UUID) -> BookCopy:
        copy = self.copies.get(copy_id)
        if copy is None or copy.organization_id != organization_id:
            raise KeyError(copy_id)
        return copy

    def update_copy_status(
        self,
        organization_id: UUID,
        copy_id: UUID,
        to_status: str,
    ) -> BookCopy:
        copy = self.get_copy(organization_id, copy_id)
        updated = BookCopy(
            copy_id=copy.copy_id,
            organization_id=copy.organization_id,
            book_id=copy.book_id,
            barcode=copy.barcode,
            location_id=copy.location_id,
            status=to_status,
            condition_code=copy.condition_code,
            acquired_at=copy.acquired_at,
            created_at=copy.created_at,
            updated_at=datetime.now(timezone.utc),
        )
        self.copies[copy_id] = updated
        return updated

    def append_history(self, record: CopyStatusHistory) -> CopyStatusHistory:
        self.history.append(record)
        return record

    def list_history_for_copy(
        self, organization_id: UUID, copy_id: UUID
    ) -> list[CopyStatusHistory]:
        return [
            h
            for h in self.history
            if h.organization_id == organization_id and h.copy_id == copy_id
        ]


class _InMemoryAuditedTransaction(AuditedTransaction):
    def __init__(
        self, *, fail_audit: bool = False, fail_mutation: bool = False
    ) -> None:
        self.audit_events: list[AuditEvent] = []
        self.outbox_events: list[OutboxEvent] = []
        self._fail_audit = fail_audit
        self._fail_mutation = fail_mutation

    def run(
        self,
        connection: object,
        mutation: Callable[[object], T],
        audit_event: AuditEvent,
        outbox_events: Sequence[OutboxEvent],
    ) -> T:
        if self._fail_mutation:
            raise RuntimeError("Simulated mutation failure in transaction")
        result = mutation(connection)
        if self._fail_audit:
            raise RuntimeError("Simulated audit write failure in transaction")
        self.audit_events.append(audit_event)
        self.outbox_events.extend(outbox_events)
        return result


def _make_sample_copy(
    organization_id: UUID = ORG_A,
    book_id: UUID | None = None,
    status: str = "available",
) -> BookCopy:
    now = datetime.now(timezone.utc)
    return BookCopy(
        copy_id=uuid4(),
        organization_id=organization_id,
        book_id=book_id or uuid4(),
        barcode=f"BC-{uuid4().hex[:8]}",
        location_id=uuid4(),
        status=status,
        condition_code="good",
        acquired_at=now,
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# Domain Policy Tests: Allowed and Rejected Transitions
# ---------------------------------------------------------------------------


class TestCopyStatusDomainPolicy:
    """Test transitions among available, borrowed, lost, damaged and maintenance."""

    @pytest.mark.parametrize(
        ("from_status", "to_status"),
        [
            # From available
            (CopyStatus.AVAILABLE, CopyStatus.BORROWED),
            (CopyStatus.AVAILABLE, CopyStatus.MAINTENANCE),
            (CopyStatus.AVAILABLE, CopyStatus.DAMAGED),
            (CopyStatus.AVAILABLE, CopyStatus.LOST),
            # From borrowed
            (CopyStatus.BORROWED, CopyStatus.AVAILABLE),
            (CopyStatus.BORROWED, CopyStatus.MAINTENANCE),
            (CopyStatus.BORROWED, CopyStatus.DAMAGED),
            (CopyStatus.BORROWED, CopyStatus.LOST),
            # From maintenance
            (CopyStatus.MAINTENANCE, CopyStatus.AVAILABLE),
            (CopyStatus.MAINTENANCE, CopyStatus.DAMAGED),
            (CopyStatus.MAINTENANCE, CopyStatus.LOST),
            # From damaged
            (CopyStatus.DAMAGED, CopyStatus.AVAILABLE),
            (CopyStatus.DAMAGED, CopyStatus.MAINTENANCE),
            (CopyStatus.DAMAGED, CopyStatus.LOST),
            # From lost
            (CopyStatus.LOST, CopyStatus.AVAILABLE),
            (CopyStatus.LOST, CopyStatus.MAINTENANCE),
            (CopyStatus.LOST, CopyStatus.DAMAGED),
        ],
    )
    def test_allowed_transitions(self, from_status: str, to_status: str) -> None:
        assert is_allowed_transition(from_status, to_status) is True
        assert (from_status, to_status) in ALLOWED_TRANSITIONS
        # validate_transition does not raise for allowed transitions
        validate_transition(from_status, to_status)

    @pytest.mark.parametrize(
        ("from_status", "to_status"),
        [
            # Invariant: lost, damaged, maintenance cannot enter borrowable without explicit allowed transition
            (CopyStatus.MAINTENANCE, CopyStatus.BORROWED),
            (CopyStatus.DAMAGED, CopyStatus.BORROWED),
            (CopyStatus.LOST, CopyStatus.BORROWED),
            # Self transitions are rejected
            (CopyStatus.AVAILABLE, CopyStatus.AVAILABLE),
            (CopyStatus.BORROWED, CopyStatus.BORROWED),
            (CopyStatus.MAINTENANCE, CopyStatus.MAINTENANCE),
            (CopyStatus.DAMAGED, CopyStatus.DAMAGED),
            (CopyStatus.LOST, CopyStatus.LOST),
            # Unknown / invalid statuses
            ("unknown", CopyStatus.AVAILABLE),
            (CopyStatus.AVAILABLE, "unknown"),
            ("", CopyStatus.AVAILABLE),
            (CopyStatus.AVAILABLE, ""),
        ],
    )
    def test_rejected_transitions_raise_domain_error(
        self, from_status: str, to_status: str
    ) -> None:
        assert is_allowed_transition(from_status, to_status) is False
        with pytest.raises(InvalidCopyStatusTransitionError) as exc_info:
            validate_transition(from_status, to_status)

        err = exc_info.value
        assert err.from_status == from_status
        assert err.to_status == to_status
        assert (
            err.problem_type
            == "https://openlibraryos.example/problems/invalid-copy-status-transition"
        )
        assert err.status_code == 409


# ---------------------------------------------------------------------------
# Application Service Tests: Transition, History, and Audit Atomicity
# ---------------------------------------------------------------------------


class TestCopyStatusService:
    def test_accepted_transition_has_exactly_one_history_and_one_audit_record(
        self,
    ) -> None:
        store = _InMemoryCopyStatusStore()
        tx = _InMemoryAuditedTransaction()
        service = CopyStatusService(
            store=store,
            authorizer=_AllowAllAuthorizer(),
            transaction=tx,
        )
        copy = _make_sample_copy(ORG_A, status=CopyStatus.AVAILABLE)
        store.copies[copy.copy_id] = copy

        correlation_id = uuid4()
        updated_copy = service.transition_status(
            actor=ACTOR_A,
            copy_id=copy.copy_id,
            to_status=CopyStatus.MAINTENANCE,
            reason="Routine spine inspection and rebinding",
            correlation_id=correlation_id,
        )

        assert updated_copy.status == CopyStatus.MAINTENANCE

        # Exactly one history record in the store
        history_records = store.list_history_for_copy(ORG_A, copy.copy_id)
        assert len(history_records) == 1
        h = history_records[0]
        assert h.organization_id == ORG_A
        assert h.copy_id == copy.copy_id
        assert h.from_status == CopyStatus.AVAILABLE
        assert h.to_status == CopyStatus.MAINTENANCE
        assert h.reason == "Routine spine inspection and rebinding"
        assert h.actor_id == ACTOR_A.user_id
        assert isinstance(h.created_at, datetime)

        # Exactly one audit record in the audited transaction
        assert len(tx.audit_events) == 1
        audit = tx.audit_events[0]
        assert audit.action == "copy.status_changed"
        assert audit.entity_type == "copy"
        assert audit.entity_id == copy.copy_id
        assert audit.actor_user_id == ACTOR_A.user_id
        assert audit.actor_type == "user"
        assert audit.correlation_id == correlation_id
        assert audit.payload == {
            "copy_id": str(copy.copy_id),
            "from_status": CopyStatus.AVAILABLE,
            "to_status": CopyStatus.MAINTENANCE,
            "reason": "Routine spine inspection and rebinding",
        }

    def test_invalid_transition_returns_documented_domain_problem_type(self) -> None:
        store = _InMemoryCopyStatusStore()
        tx = _InMemoryAuditedTransaction()
        service = CopyStatusService(
            store=store,
            authorizer=_AllowAllAuthorizer(),
            transaction=tx,
        )
        copy = _make_sample_copy(ORG_A, status=CopyStatus.DAMAGED)
        store.copies[copy.copy_id] = copy

        with pytest.raises(InvalidCopyStatusTransitionError) as exc_info:
            service.transition_status(
                actor=ACTOR_A,
                copy_id=copy.copy_id,
                to_status=CopyStatus.BORROWED,
                reason="Attempting to borrow damaged book",
            )

        err = exc_info.value
        assert (
            err.problem_type
            == "https://openlibraryos.example/problems/invalid-copy-status-transition"
        )
        assert err.status_code == 409
        # State was unchanged
        assert store.copies[copy.copy_id].status == CopyStatus.DAMAGED
        # Neither history nor audit record written
        assert len(store.history) == 0
        assert len(tx.audit_events) == 0

    def test_transition_requires_actor_and_non_empty_reason(self) -> None:
        store = _InMemoryCopyStatusStore()
        tx = _InMemoryAuditedTransaction()
        service = CopyStatusService(
            store=store,
            authorizer=_AllowAllAuthorizer(),
            transaction=tx,
        )
        copy = _make_sample_copy(ORG_A, status=CopyStatus.AVAILABLE)
        store.copies[copy.copy_id] = copy

        # Empty reason
        with pytest.raises(ValueError, match="reason"):
            service.transition_status(
                actor=ACTOR_A,
                copy_id=copy.copy_id,
                to_status=CopyStatus.MAINTENANCE,
                reason="   ",
            )

        # Actor without user_id
        system_actor = Principal(
            user_id=None, organization_id=ORG_A, session_id=uuid4()
        )
        with pytest.raises(ValueError, match="(?i)actor"):
            service.transition_status(
                actor=system_actor,
                copy_id=copy.copy_id,
                to_status=CopyStatus.MAINTENANCE,
                reason="Valid reason",
            )

    def test_transition_requires_inventory_manage_permission(self) -> None:
        store = _InMemoryCopyStatusStore()
        tx = _InMemoryAuditedTransaction()
        service = CopyStatusService(
            store=store,
            authorizer=_SelectiveAuthorizer(allowed_permissions={"catalog.read"}),
            transaction=tx,
        )
        copy = _make_sample_copy(ORG_A, status=CopyStatus.AVAILABLE)
        store.copies[copy.copy_id] = copy

        with pytest.raises(AuthorizationDenied):
            service.transition_status(
                actor=ACTOR_A,
                copy_id=copy.copy_id,
                to_status=CopyStatus.MAINTENANCE,
                reason="Valid reason",
            )

    def test_status_logic_is_copy_level_never_book_level(self) -> None:
        shared_book_id = uuid4()
        store = _InMemoryCopyStatusStore()
        tx = _InMemoryAuditedTransaction()
        service = CopyStatusService(
            store=store,
            authorizer=_AllowAllAuthorizer(),
            transaction=tx,
        )
        copy1 = _make_sample_copy(
            ORG_A, book_id=shared_book_id, status=CopyStatus.AVAILABLE
        )
        copy2 = _make_sample_copy(
            ORG_A, book_id=shared_book_id, status=CopyStatus.AVAILABLE
        )
        store.copies[copy1.copy_id] = copy1
        store.copies[copy2.copy_id] = copy2

        service.transition_status(
            actor=ACTOR_A,
            copy_id=copy1.copy_id,
            to_status=CopyStatus.DAMAGED,
            reason="Water damage",
        )

        assert store.copies[copy1.copy_id].status == CopyStatus.DAMAGED
        # Sibling copy of same book remains available
        assert store.copies[copy2.copy_id].status == CopyStatus.AVAILABLE

    def test_cross_tenant_isolation(self) -> None:
        store = _InMemoryCopyStatusStore()
        tx = _InMemoryAuditedTransaction()
        service = CopyStatusService(
            store=store,
            authorizer=_AllowAllAuthorizer(),
            transaction=tx,
        )
        copy_b = _make_sample_copy(ORG_B, status=CopyStatus.AVAILABLE)
        store.copies[copy_b.copy_id] = copy_b

        # Actor from ORG_A cannot transition ORG_B copy
        with pytest.raises(KeyError):
            service.transition_status(
                actor=ACTOR_A,
                copy_id=copy_b.copy_id,
                to_status=CopyStatus.LOST,
                reason="Attempt cross tenant",
            )

        # Actor from ORG_A cannot list ORG_B history
        history = service.list_copy_history(actor=ACTOR_A, copy_id=copy_b.copy_id)
        assert history == []

    def test_history_rows_cannot_be_updated_or_deleted_through_application_service(
        self,
    ) -> None:
        service = CopyStatusService(
            store=_InMemoryCopyStatusStore(),
            authorizer=_AllowAllAuthorizer(),
            transaction=_InMemoryAuditedTransaction(),
        )
        assert not hasattr(service, "update_history")
        assert not hasattr(service, "delete_history")
        assert not hasattr(service, "modify_history")

    def test_failed_transaction_leaves_neither_copy_nor_audit_record(self) -> None:
        store = _InMemoryCopyStatusStore()
        failing_tx = _InMemoryAuditedTransaction(fail_audit=True)
        service = CopyStatusService(
            store=store,
            authorizer=_AllowAllAuthorizer(),
            transaction=failing_tx,
        )
        copy = _make_sample_copy(ORG_A, status=CopyStatus.AVAILABLE)
        store.copies[copy.copy_id] = copy

        with pytest.raises(RuntimeError, match="Simulated audit write failure"):
            service.transition_status(
                actor=ACTOR_A,
                copy_id=copy.copy_id,
                to_status=CopyStatus.LOST,
                reason="Missing from shelf",
            )

        # In real DB, the transaction rolls back both writes
        assert len(failing_tx.audit_events) == 0
