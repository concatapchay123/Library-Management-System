"""API tests for circulation loan idempotency replay and conflict detection."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest

from openlibrary.app.config import AppConfig
from openlibrary.app.factory import create_app
from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.authorization import AuthorizationDenied
from openlibrary.modules.core.application.copy_status import CopyStatusHistory
from openlibrary.modules.core.application.inventory import BookCopy
from openlibrary.modules.core.application.loans import Loan, LoanService
from openlibrary.modules.core.domain.copy_status import CopyStatus
from openlibrary.modules.core.domain.loans import LoanNotFoundError, LoanStatus
from openlibrary.modules.ops.application.idempotency import (
    IdempotencyRecord,
    IdempotencyService,
    IdempotencyStore,
)
from openlibrary.modules.ops.application.persistence import (
    AuditEvent,
    OutboxEvent,
)

ORGANIZATION_A = uuid4()
BORROWER_A = Principal(uuid4(), ORGANIZATION_A, uuid4())
LIBRARIAN_A = Principal(uuid4(), ORGANIZATION_A, uuid4())


@dataclass
class _InMemoryLoanStore:
    loans: dict[UUID, Loan] = field(default_factory=dict)

    def create_loan(self, loan: Loan) -> Loan:
        self.loans[loan.loan_id] = loan
        return loan

    def get_loan(self, organization_id: UUID, loan_id: UUID) -> Loan:
        loan = self.loans.get(loan_id)
        if loan is None or loan.organization_id != organization_id:
            raise LoanNotFoundError(loan_id)
        return loan

    def update_loan(self, loan: Loan) -> Loan:
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
            results = [loan_item for loan_item in results if loan_item.status == status]
        return sorted(results, key=lambda loan_item: loan_item.created_at, reverse=True)

    def count_active_loans_for_borrower(
        self, organization_id: UUID, borrower_user_id: UUID
    ) -> int:
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
        for loan_item in self.loans.values():
            if (
                loan_item.organization_id == organization_id
                and loan_item.copy_id == copy_id
                and loan_item.status == LoanStatus.CHECKED_OUT
            ):
                return loan_item
        return None


@dataclass
class _InMemoryCopyStore:
    copies: dict[UUID, BookCopy] = field(default_factory=dict)
    history: list[CopyStatusHistory] = field(default_factory=list)

    def get_copy(self, organization_id: UUID, copy_id: UUID) -> BookCopy:
        copy = self.copies.get(copy_id)
        if copy is None or copy.organization_id != organization_id:
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


@dataclass
class _RecordingAuditedTransaction:
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


class _StaticAuthorizer:
    def __init__(self, allowed: set[tuple[UUID, str]] | None = None) -> None:
        self._allowed = allowed if allowed is not None else set()

    def allow(self, principal: Principal, permission: str) -> None:
        self._allowed.add((principal.user_id, permission))

    def require(self, principal: Principal, permission: str) -> None:
        if (principal.user_id, permission) not in self._allowed:
            raise AuthorizationDenied(f"Permission {permission} denied")


class _StubAccessTokenService:
    def verify(self, token: str) -> Principal:
        if token == "borrower-a-token":
            return BORROWER_A
        if token == "librarian-a-token":
            return LIBRARIAN_A
        raise ValueError(f"Unknown token: {token}")


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
        target = None
        for k, rec in self.records.items():
            if rec.organization_id == organization_id and rec.key_id == key_id:
                target = k
                break
        if target:
            del self.records[target]


@pytest.fixture
def env() -> dict[str, Any]:
    copy_store = _InMemoryCopyStore()
    loan_store = _InMemoryLoanStore()
    authorizer = _StaticAuthorizer()
    tx = _RecordingAuditedTransaction()
    idempotency_store = _InMemoryIdempotencyStore()
    idempotency_audits: list[AuditEvent] = []

    authorizer.allow(BORROWER_A, "circulation.request")
    authorizer.allow(BORROWER_A, "circulation.read")
    authorizer.allow(LIBRARIAN_A, "circulation.request")
    authorizer.allow(LIBRARIAN_A, "circulation.approve")
    authorizer.allow(LIBRARIAN_A, "circulation.checkout")
    authorizer.allow(LIBRARIAN_A, "circulation.return")
    authorizer.allow(LIBRARIAN_A, "circulation.read")
    authorizer.allow(LIBRARIAN_A, "circulation.manage")

    now = datetime.now(timezone.utc)
    copy_id = uuid4()
    copy = BookCopy(
        copy_id=copy_id,
        organization_id=ORGANIZATION_A,
        book_id=uuid4(),
        barcode="BC-IDEMP-1",
        location_id=uuid4(),
        status=CopyStatus.AVAILABLE,
        condition_code="good",
        acquired_at=now,
        created_at=now,
        updated_at=now,
    )
    copy_store.copies[copy_id] = copy

    loan_service = LoanService(
        loan_store=loan_store,
        copy_store=copy_store,
        authorizer=authorizer,
        transaction=tx,
    )

    idempotency_service = IdempotencyService(
        store=idempotency_store,
        audit_recorder=idempotency_audits.append,
    )

    app = create_app(
        AppConfig(
            readiness_probe=lambda: True,
            access_tokens=_StubAccessTokenService(),  # type: ignore[arg-type]
            authorization=authorizer,  # type: ignore[arg-type]
            loan_service=loan_service,
            idempotency_service=idempotency_service,
        )
    )

    return {
        "client": app.test_client(),
        "copy_id": copy_id,
        "copy_store": copy_store,
        "loan_store": loan_store,
        "tx": tx,
        "idempotency_store": idempotency_store,
        "idempotency_audits": idempotency_audits,
    }


def test_desk_checkout_with_idempotency_key_replays_response_without_duplicate_events(
    env: dict[str, Any],
) -> None:
    client = env["client"]
    copy_id = env["copy_id"]
    tx = env["tx"]

    payload = {
        "copy_id": str(copy_id),
        "borrower_user_id": str(BORROWER_A.user_id),
        "duration_days": 14,
    }
    headers = {
        "Authorization": "Bearer librarian-a-token",
        "Idempotency-Key": "desk-key-100",
    }

    # 1. First execution
    res1 = client.post("/api/v1/loans/desk-checkout", headers=headers, json=payload)
    assert res1.status_code == 201
    data1 = res1.get_json()
    assert data1["status"] == "checked_out"
    assert "Idempotency-Replayed" not in res1.headers

    audit_count_after_first = len(tx.audit_events)
    outbox_count_after_first = len(tx.outbox_events)
    assert audit_count_after_first == 3  # requested, approved, checked_out
    assert outbox_count_after_first == 3

    # 2. Repeated execution with same key and payload
    res2 = client.post("/api/v1/loans/desk-checkout", headers=headers, json=payload)
    assert res2.status_code == 201
    assert res2.headers.get("Idempotency-Replayed") == "true"
    data2 = res2.get_json()
    assert data2 == data1

    # Checkpoint: No duplicate audit/outbox events were created
    assert len(tx.audit_events) == audit_count_after_first
    assert len(tx.outbox_events) == outbox_count_after_first


def test_checkout_and_return_with_idempotency_key_replay(env: dict[str, Any]) -> None:
    client = env["client"]
    copy_id = env["copy_id"]

    # 1. Borrower requests
    req_res = client.post(
        "/api/v1/loans",
        headers={"Authorization": "Bearer borrower-a-token"},
        json={"copy_id": str(copy_id)},
    )
    loan_id = req_res.get_json()["loan_id"]

    # 2. Librarian approves
    client.post(
        f"/api/v1/loans/{loan_id}/approve",
        headers={"Authorization": "Bearer librarian-a-token"},
        json={},
    )

    # 3. Checkout with Idempotency-Key
    checkout_headers = {
        "Authorization": "Bearer librarian-a-token",
        "Idempotency-Key": "checkout-key-200",
    }
    co_res1 = client.post(
        f"/api/v1/loans/{loan_id}/checkout",
        headers=checkout_headers,
        json={"duration_days": 21},
    )
    assert co_res1.status_code == 200
    assert co_res1.get_json()["status"] == "checked_out"

    # Retry checkout with same key
    co_res2 = client.post(
        f"/api/v1/loans/{loan_id}/checkout",
        headers=checkout_headers,
        json={"duration_days": 21},
    )
    assert co_res2.status_code == 200
    assert co_res2.headers.get("Idempotency-Replayed") == "true"
    assert co_res2.get_json() == co_res1.get_json()

    # 4. Return with Idempotency-Key
    return_headers = {
        "Authorization": "Bearer librarian-a-token",
        "Idempotency-Key": "return-key-300",
    }
    ret_res1 = client.post(
        f"/api/v1/loans/{loan_id}/return",
        headers=return_headers,
        json={},
    )
    assert ret_res1.status_code == 200
    assert ret_res1.get_json()["status"] == "returned"

    # Retry return with same key (normally would 409 because already returned)
    ret_res2 = client.post(
        f"/api/v1/loans/{loan_id}/return",
        headers=return_headers,
        json={},
    )
    assert ret_res2.status_code == 200
    assert ret_res2.headers.get("Idempotency-Replayed") == "true"
    assert ret_res2.get_json() == ret_res1.get_json()


def test_idempotency_key_reuse_with_different_payload_returns_409_conflict(
    env: dict[str, Any],
) -> None:
    client = env["client"]
    copy_id = env["copy_id"]
    idempotency_audits = env["idempotency_audits"]

    key = "conflict-key-1"
    headers = {
        "Authorization": "Bearer librarian-a-token",
        "Idempotency-Key": key,
    }

    # Initial desk checkout
    res1 = client.post(
        "/api/v1/loans/desk-checkout",
        headers=headers,
        json={
            "copy_id": str(copy_id),
            "borrower_user_id": str(BORROWER_A.user_id),
            "duration_days": 7,
        },
    )
    assert res1.status_code == 201

    # Reuse same key with different duration_days payload
    res2 = client.post(
        "/api/v1/loans/desk-checkout",
        headers=headers,
        json={
            "copy_id": str(copy_id),
            "borrower_user_id": str(BORROWER_A.user_id),
            "duration_days": 14,
        },
    )
    assert res2.status_code == 409
    body = res2.get_json()
    assert body["type"] == "https://openlibraryos.example/problems/idempotency-conflict"
    assert "different request payload" in body["detail"]

    # Explicit audit event check
    assert len(idempotency_audits) == 1
    assert idempotency_audits[0].action == "idempotency.request_hash_mismatch"
    assert idempotency_audits[0].payload["idempotency_key"] == key


def test_invalid_idempotency_key_header_returns_400(env: dict[str, Any]) -> None:
    client = env["client"]
    copy_id = env["copy_id"]

    # Empty key
    res = client.post(
        "/api/v1/loans/desk-checkout",
        headers={
            "Authorization": "Bearer librarian-a-token",
            "Idempotency-Key": "   ",
        },
        json={"copy_id": str(copy_id), "borrower_user_id": str(BORROWER_A.user_id)},
    )
    assert res.status_code == 400
    assert "Idempotency-Key" in res.get_json()["detail"]

    # Key exceeding 128 characters
    res_long = client.post(
        "/api/v1/loans/desk-checkout",
        headers={
            "Authorization": "Bearer librarian-a-token",
            "Idempotency-Key": "k" * 129,
        },
        json={"copy_id": str(copy_id), "borrower_user_id": str(BORROWER_A.user_id)},
    )
    assert res_long.status_code == 400


def test_expired_idempotency_record_cleans_up_and_allows_new_request(
    env: dict[str, Any],
) -> None:
    client = env["client"]
    copy_id = env["copy_id"]
    idempotency_store = env["idempotency_store"]

    key = "expired-key-999"
    method = "POST"
    endpoint = "/api/v1/loans/desk-checkout"

    # Pre-seed an expired record (> 24 hours ago)
    expired_time = datetime.now(timezone.utc) - timedelta(hours=25)
    idempotency_store.save_record(
        key_id=uuid4(),
        organization_id=ORGANIZATION_A,
        key=key,
        method=method,
        endpoint=endpoint,
        request_hash="stale_hash",
        resource_reference="stale_ref",
        status_code=201,
        safe_response_json='{"loan_id": "stale"}',
        created_at=expired_time - timedelta(hours=24),
        expires_at=expired_time,
    )

    # Valid new request with the same key
    res = client.post(
        "/api/v1/loans/desk-checkout",
        headers={
            "Authorization": "Bearer librarian-a-token",
            "Idempotency-Key": key,
        },
        json={
            "copy_id": str(copy_id),
            "borrower_user_id": str(BORROWER_A.user_id),
            "duration_days": 10,
        },
    )
    assert res.status_code == 201
    assert "Idempotency-Replayed" not in res.headers
    assert res.get_json()["status"] == "checked_out"
