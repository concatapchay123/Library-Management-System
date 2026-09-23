"""Unit tests for BE-017: Copy row locking protocol and IdempotencyService replay and conflict handling."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import threading
from typing import Any
from uuid import UUID, uuid4

import pytest

from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.authorization import AuthorizationPort
from openlibrary.modules.core.application.copy_status import (
    CopyStatusHistory,
    CopyStatusStore,
)
from openlibrary.modules.core.application.inventory import BookCopy
from openlibrary.modules.core.application.loans import Loan, LoanService, LoanStore
from openlibrary.modules.core.domain.copy_status import CopyStatus
from openlibrary.modules.core.domain.loans import (
    CopyNotAvailableForLoanError,
    LoanNotFoundError,
    LoanStatus,
)
from openlibrary.modules.ops.application.idempotency import (
    IdempotencyConflictError,
    IdempotencyRecord,
    IdempotencyService,
    IdempotencyStore,
    compute_request_hash,
    validate_safe_response,
)
from openlibrary.modules.ops.application.persistence import (
    AuditEvent,
    AuditedTransaction,
    OutboxEvent,
)

ORG_A = uuid4()
ORG_B = uuid4()
BORROWER_ID = uuid4()
LIBRARIAN_ID = uuid4()
LIBRARIAN_ACTOR = Principal(
    user_id=LIBRARIAN_ID, organization_id=ORG_A, session_id=uuid4()
)


class _AllowAllAuthorizer(AuthorizationPort):
    def require(self, principal: Principal, permission: str) -> None:
        pass


@dataclass
class _InMemoryLoanStore(LoanStore):
    loans: dict[UUID, Loan] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def create_loan(self, loan: Loan) -> Loan:
        with self._lock:
            self.loans[loan.loan_id] = loan
            return loan

    def get_loan(self, organization_id: UUID, loan_id: UUID) -> Loan:
        with self._lock:
            loan = self.loans.get(loan_id)
            if loan is None or loan.organization_id != organization_id:
                raise LoanNotFoundError(loan_id)
            return loan

    def update_loan(self, loan: Loan) -> Loan:
        with self._lock:
            if (
                loan.loan_id not in self.loans
                or self.loans[loan.loan_id].organization_id != loan.organization_id
            ):
                raise LoanNotFoundError(loan.loan_id)
            self.loans[loan.loan_id] = loan
            return loan

    def list_loans(
        self,
        organization_id: UUID,
        *,
        borrower_user_id: UUID | None = None,
        copy_id: UUID | None = None,
        status: str | None = None,
    ) -> list[Loan]:
        with self._lock:
            results = [
                loan_item
                for loan_item in self.loans.values()
                if loan_item.organization_id == organization_id
            ]
            if borrower_user_id is not None:
                results = [
                    loan_item
                    for loan_item in results
                    if loan_item.borrower_user_id == borrower_user_id
                ]
            if copy_id is not None:
                results = [
                    loan_item for loan_item in results if loan_item.copy_id == copy_id
                ]
            if status is not None:
                results = [
                    loan_item for loan_item in results if loan_item.status == status
                ]
            return sorted(
                results, key=lambda loan_item: loan_item.created_at, reverse=True
            )

    def count_active_loans_for_borrower(
        self, organization_id: UUID, borrower_user_id: UUID
    ) -> int:
        with self._lock:
            return sum(
                1
                for loan_item in self.loans.values()
                if loan_item.organization_id == organization_id
                and loan_item.borrower_user_id == borrower_user_id
                and loan_item.status == LoanStatus.CHECKED_OUT
            )

    def get_active_loan_for_copy(
        self, organization_id: UUID, copy_id: UUID
    ) -> Loan | None:
        with self._lock:
            for loan_item in self.loans.values():
                if (
                    loan_item.organization_id == organization_id
                    and loan_item.copy_id == copy_id
                    and loan_item.status == LoanStatus.CHECKED_OUT
                ):
                    return loan_item
            return None


@dataclass
class _LockingCopyStore(CopyStatusStore):
    """Simulates row locking via mutex locks per copy_id."""

    copies: dict[UUID, BookCopy] = field(default_factory=dict)
    history: list[CopyStatusHistory] = field(default_factory=list)
    lock_calls: list[UUID] = field(default_factory=list)
    _copy_mutexes: dict[UUID, threading.Lock] = field(default_factory=dict)
    _global_lock: threading.Lock = field(default_factory=threading.Lock)

    def _get_copy_mutex(self, copy_id: UUID) -> threading.Lock:
        with self._global_lock:
            if copy_id not in self._copy_mutexes:
                self._copy_mutexes[copy_id] = threading.Lock()
            return self._copy_mutexes[copy_id]

    def get_copy(self, organization_id: UUID, copy_id: UUID) -> BookCopy:
        copy = self.copies.get(copy_id)
        if copy is None or copy.organization_id != organization_id:
            raise KeyError(copy_id)
        return copy

    def get_copy_for_update_in_connection(
        self, connection: Any, organization_id: UUID, copy_id: UUID
    ) -> BookCopy:
        """Acquire copy row lock and return fresh state."""
        self.lock_calls.append(copy_id)
        mutex = self._get_copy_mutex(copy_id)
        mutex.acquire()
        if connection is not None and hasattr(connection, "add_cleanup"):
            connection.add_cleanup(lambda: mutex.release())
        copy = self.copies.get(copy_id)
        if copy is None or copy.organization_id != organization_id:
            mutex.release()
            raise KeyError(copy_id)
        return copy

    def update_copy_status(
        self, organization_id: UUID, copy_id: UUID, to_status: str
    ) -> BookCopy:
        copy = self.get_copy(organization_id, copy_id)
        now = datetime.now(timezone.utc)
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
            updated_at=now,
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


class _SimulatedConnection:
    def __init__(self) -> None:
        self.cleanups: list[Any] = []

    def add_cleanup(self, fn: Any) -> None:
        self.cleanups.append(fn)

    def close(self) -> None:
        for fn in reversed(self.cleanups):
            fn()
        self.cleanups.clear()

    def __enter__(self) -> _SimulatedConnection:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()


@dataclass
class _SimulatedTransaction(AuditedTransaction):
    audit_events: list[AuditEvent] = field(default_factory=list)
    outbox_events: list[OutboxEvent] = field(default_factory=list)

    def run(
        self,
        connection: Any,
        mutation: Any,
        audit_event: AuditEvent,
        outbox_events: Any,
    ) -> Any:
        result = mutation(connection)
        self.audit_events.append(audit_event)
        self.outbox_events.extend(outbox_events)
        return result


@dataclass
class _InMemoryIdempotencyStore(IdempotencyStore):
    records: dict[tuple[UUID, str, str, str], IdempotencyRecord] = field(
        default_factory=dict
    )

    def get_record(
        self, organization_id: UUID, key: str, method: str, endpoint: str
    ) -> IdempotencyRecord | None:
        return self.records.get((organization_id, key, method, endpoint))

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
    ) -> IdempotencyRecord:
        record = IdempotencyRecord(
            key_id=key_id,
            organization_id=organization_id,
            key=key,
            method=method,
            endpoint=endpoint,
            request_hash=request_hash,
            resource_reference=resource_reference,
            status_code=status_code,
            safe_response_json=safe_response_json,
            created_at=created_at,
            expires_at=expires_at,
        )
        self.records[(organization_id, key, method, endpoint)] = record
        return record

    def delete_record(self, organization_id: UUID, key_id: UUID) -> None:
        for k, rec in list(self.records.items()):
            if rec.organization_id == organization_id and rec.key_id == key_id:
                del self.records[k]


def _make_sample_copy(copy_id: UUID, status: str = CopyStatus.AVAILABLE) -> BookCopy:
    now = datetime.now(timezone.utc)
    return BookCopy(
        copy_id=copy_id,
        organization_id=ORG_A,
        book_id=uuid4(),
        barcode="BC-LOCK-1",
        location_id=uuid4(),
        status=status,
        condition_code="good",
        acquired_at=now,
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# Concurrency & Row Locking Tests
# ---------------------------------------------------------------------------


def test_checkout_loan_calls_get_copy_for_update_in_connection() -> None:
    """Checkout invokes get_copy_for_update_in_connection to lock copy row."""
    copy_id = uuid4()
    copy_store = _LockingCopyStore()
    copy_store.copies[copy_id] = _make_sample_copy(copy_id)

    loan_id = uuid4()
    now = datetime.now(timezone.utc)
    loan_store = _InMemoryLoanStore()
    loan_store.create_loan(
        Loan(
            loan_id=loan_id,
            organization_id=ORG_A,
            copy_id=copy_id,
            borrower_user_id=BORROWER_ID,
            status=LoanStatus.APPROVED,
            loan_status=LoanStatus.APPROVED,
            request_status="approved",
            requested_at=now,
            approved_at=now,
            created_at=now,
            updated_at=now,
        )
    )

    tx = _SimulatedTransaction()
    service = LoanService(
        loan_store=loan_store,
        copy_store=copy_store,
        authorizer=_AllowAllAuthorizer(),
        transaction=tx,
        connection_provider=lambda org_id: _SimulatedConnection(),
    )

    loan = service.checkout_loan(
        actor=LIBRARIAN_ACTOR,
        loan_id=loan_id,
        duration_days=14,
    )

    assert loan.status == LoanStatus.CHECKED_OUT
    assert copy_id in copy_store.lock_calls


def test_concurrent_checkout_attempts_on_same_copy_yield_one_success_one_conflict() -> (
    None
):
    """Simulate two threads attempting to checkout the same copy concurrently."""
    copy_id = uuid4()
    copy_store = _LockingCopyStore()
    copy_store.copies[copy_id] = _make_sample_copy(copy_id)

    now = datetime.now(timezone.utc)
    loan_1_id = uuid4()
    loan_2_id = uuid4()
    loan_store = _InMemoryLoanStore()

    loan_store.create_loan(
        Loan(
            loan_id=loan_1_id,
            organization_id=ORG_A,
            copy_id=copy_id,
            borrower_user_id=BORROWER_ID,
            status=LoanStatus.APPROVED,
            loan_status=LoanStatus.APPROVED,
            request_status="approved",
            requested_at=now,
            approved_at=now,
            created_at=now,
            updated_at=now,
        )
    )
    loan_store.create_loan(
        Loan(
            loan_id=loan_2_id,
            organization_id=ORG_A,
            copy_id=copy_id,
            borrower_user_id=BORROWER_ID,
            status=LoanStatus.APPROVED,
            loan_status=LoanStatus.APPROVED,
            request_status="approved",
            requested_at=now,
            approved_at=now,
            created_at=now,
            updated_at=now,
        )
    )

    tx = _SimulatedTransaction()
    service = LoanService(
        loan_store=loan_store,
        copy_store=copy_store,
        authorizer=_AllowAllAuthorizer(),
        transaction=tx,
        connection_provider=lambda org_id: _SimulatedConnection(),
    )

    results: list[Loan] = []
    errors: list[Exception] = []
    results_lock = threading.Lock()

    def _worker(lid: UUID) -> None:
        try:
            res = service.checkout_loan(
                actor=LIBRARIAN_ACTOR,
                loan_id=lid,
                duration_days=14,
            )
            with results_lock:
                results.append(res)
        except Exception as exc:
            with results_lock:
                errors.append(exc)

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(_worker, loan_1_id)
        f2 = executor.submit(_worker, loan_2_id)
        f1.result()
        f2.result()

    assert len(results) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], CopyNotAvailableForLoanError)


# ---------------------------------------------------------------------------
# Idempotency Hashing & Response Sanitization Tests
# ---------------------------------------------------------------------------


def test_compute_request_hash_deterministic_and_order_independent() -> None:
    payload_a = {"copy_id": "abc", "duration_days": 14, "notes": None}
    payload_b = {"notes": None, "duration_days": 14, "copy_id": "abc"}
    assert compute_request_hash(payload_a) == compute_request_hash(payload_b)

    # Empty payload
    empty_hash = compute_request_hash({})
    none_hash = compute_request_hash(None)
    assert empty_hash == none_hash


def test_validate_safe_response_rejects_sensitive_keys() -> None:
    # Safe response serializes cleanly
    safe_body = {"loan_id": str(uuid4()), "status": "checked_out"}
    serialized = validate_safe_response(safe_body)
    assert "loan_id" in serialized

    # Sensitive keys raise ValueError
    for bad_key in ["token", "password", "card_number", "access_token", "secret"]:
        with pytest.raises(ValueError, match="sensitive"):
            validate_safe_response({"data": "ok", bad_key: "secret_value"})


# ---------------------------------------------------------------------------
# IdempotencyService Replay, Conflict, and Expiration Tests
# ---------------------------------------------------------------------------


def test_idempotency_service_first_request_executes_and_stores() -> None:
    store = _InMemoryIdempotencyStore()
    service = IdempotencyService(store)

    key = "first-req-key"
    payload = {"copy_id": "copy-1"}
    resp = {"loan_id": "loan-1", "status": "approved"}

    executed = False

    def _exec() -> tuple[int, dict[str, Any], str]:
        nonlocal executed
        executed = True
        return 201, resp, "ref-1"

    result = service.process_or_replay(
        organization_id=ORG_A,
        key=key,
        method="POST",
        endpoint="/api/v1/loans/request",
        request_payload=payload,
        execute=_exec,
    )

    assert executed is True
    assert result.replayed is False
    assert result.status_code == 201
    assert result.body == resp
    assert result.resource_reference == "ref-1"

    # Verify stored in store
    rec = store.get_record(ORG_A, key, "POST", "/api/v1/loans/request")
    assert rec is not None
    assert rec.status_code == 201


def test_idempotency_service_repeated_request_replays_without_execution() -> None:
    store = _InMemoryIdempotencyStore()
    service = IdempotencyService(store)

    key = "repeat-req-key"
    payload = {"copy_id": "copy-1"}
    resp = {"loan_id": "loan-1", "status": "approved"}

    # First execution
    service.process_or_replay(
        organization_id=ORG_A,
        key=key,
        method="POST",
        endpoint="/api/v1/loans/request",
        request_payload=payload,
        execute=lambda: (201, resp, "ref-1"),
    )

    # Replay
    executed = False

    def _should_not_run() -> tuple[int, dict[str, Any], str]:
        nonlocal executed
        executed = True
        return 500, {}, ""

    replay_result = service.process_or_replay(
        organization_id=ORG_A,
        key=key,
        method="POST",
        endpoint="/api/v1/loans/request",
        request_payload=payload,
        execute=_should_not_run,
    )

    assert executed is False
    assert replay_result.replayed is True
    assert replay_result.status_code == 201
    assert replay_result.body == resp


def test_idempotency_service_conflict_raises_and_audits() -> None:
    store = _InMemoryIdempotencyStore()
    audit_events: list[AuditEvent] = []
    service = IdempotencyService(store, audit_recorder=audit_events.append)

    key = "conflict-req-key"
    payload_1 = {"copy_id": "copy-1"}
    payload_2 = {"copy_id": "copy-2"}

    service.process_or_replay(
        organization_id=ORG_A,
        key=key,
        method="POST",
        endpoint="/api/v1/loans/request",
        request_payload=payload_1,
        execute=lambda: (201, {"status": "ok"}, "ref-1"),
    )

    with pytest.raises(IdempotencyConflictError) as exc_info:
        service.process_or_replay(
            organization_id=ORG_A,
            key=key,
            method="POST",
            endpoint="/api/v1/loans/request",
            request_payload=payload_2,
            execute=lambda: (201, {"status": "ok"}, "ref-2"),
        )

    assert exc_info.value.status_code == 409
    assert len(audit_events) == 1
    assert audit_events[0].action == "idempotency.request_hash_mismatch"
    assert audit_events[0].payload["idempotency_key"] == key


def test_idempotency_service_expired_record_does_not_suppress_new_request() -> None:
    store = _InMemoryIdempotencyStore()
    service = IdempotencyService(store)

    key = "expired-req-key"
    old_payload = {"copy_id": "copy-old"}
    new_payload = {"copy_id": "copy-new"}

    # Seed an expired record (> 24 hours ago)
    now = datetime.now(timezone.utc)
    past = now - timedelta(hours=25)
    store.save_record(
        key_id=uuid4(),
        organization_id=ORG_A,
        key=key,
        method="POST",
        endpoint="/api/v1/loans/request",
        request_hash=compute_request_hash(old_payload),
        resource_reference="old-ref",
        status_code=201,
        safe_response_json='{"loan_id": "old"}',
        created_at=past - timedelta(hours=24),
        expires_at=past,
    )

    new_resp = {"loan_id": "new-loan", "status": "approved"}
    result = service.process_or_replay(
        organization_id=ORG_A,
        key=key,
        method="POST",
        endpoint="/api/v1/loans/request",
        request_payload=new_payload,
        execute=lambda: (201, new_resp, "new-ref"),
    )

    assert result.replayed is False
    assert result.body == new_resp
    assert result.status_code == 201


def test_idempotency_service_tenant_isolation() -> None:
    store = _InMemoryIdempotencyStore()
    service = IdempotencyService(store)

    key = "shared-key"
    payload = {"copy_id": "copy-1"}

    # Process under ORG_A
    service.process_or_replay(
        organization_id=ORG_A,
        key=key,
        method="POST",
        endpoint="/api/v1/loans/request",
        request_payload=payload,
        execute=lambda: (201, {"org": "A"}, "ref-A"),
    )

    # Process same key under ORG_B: should execute independently
    executed_b = False

    def _exec_b() -> tuple[int, dict[str, Any], str]:
        nonlocal executed_b
        executed_b = True
        return 201, {"org": "B"}, "ref-B"

    res_b = service.process_or_replay(
        organization_id=ORG_B,
        key=key,
        method="POST",
        endpoint="/api/v1/loans/request",
        request_payload=payload,
        execute=_exec_b,
    )

    assert executed_b is True
    assert res_b.body == {"org": "B"}


def test_idempotency_key_validation() -> None:
    store = _InMemoryIdempotencyStore()
    service = IdempotencyService(store)

    with pytest.raises(ValueError, match="between 1 and 128"):
        service.process_or_replay(
            organization_id=ORG_A,
            key="",
            method="POST",
            endpoint="/test",
            request_payload={},
            execute=lambda: (200, {}, None),
        )

    with pytest.raises(ValueError, match="between 1 and 128"):
        service.process_or_replay(
            organization_id=ORG_A,
            key="a" * 129,
            method="POST",
            endpoint="/test",
            request_payload={},
            execute=lambda: (200, {}, None),
        )
