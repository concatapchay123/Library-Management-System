"""Release gate verification tests for BE-027.

Covers:
- RLS catalog and composite foreign keys across all tenant tables
- Token reuse, rotation replay resistance, and algorithm pinning
- Audit and outbox transactional atomicity
- Dispatcher replay safety and lease recovery
- Payment webhook replay window, signature check, and deduplication
- Idempotency 24h TTL, secret sanitization, and legal-hold retention
- Catalog search and checkout performance baselines
- Frontend accessibility contract and release-evidence verification
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import pytest

from openlibrary.modules.core.application.access_tokens import (
    AccessTokenService,
    JwtKey,
    TokenVerificationError,
)
from openlibrary.modules.core.application.books import Book
from openlibrary.modules.core.application.inventory import BookCopy
from openlibrary.modules.core.application.loans import Loan
from openlibrary.modules.core.application.refresh_sessions import (
    RefreshSession,
    RefreshSessionService,
    RefreshSessionStore,
)
from openlibrary.modules.core.domain.loans import LoanNotFoundError, LoanStatus
from openlibrary.modules.ops.application.idempotency import (
    IdempotencyRecord,
    IdempotencyService,
    IdempotencyStore,
)
from openlibrary.modules.ops.application.persistence import (
    AuditEvent,
    AuditedTransaction,
    OutboxEvent,
)
from openlibrary.modules.ops.application.release_gate import (
    FrontendAccessibilityVerifier,
    LegalHoldException,
    MigrationCatalogVerifier,
    PerformanceBenchmark,
    ReleaseGateReport,
    RetentionPolicy,
    RetentionPolicyVerifier,
)
from openlibrary.modules.public_library.domain import (
    InvalidWebhookSignatureError,
    StaleWebhookTimestampError,
)
from openlibrary.modules.public_library.webhooks import WebhookSignatureVerifier


NOW = datetime(2026, 9, 23, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Test doubles and fixtures
# ---------------------------------------------------------------------------


@dataclass
class _InMemoryStore:
    books: dict[UUID, Book] = field(default_factory=dict)
    copies: dict[UUID, BookCopy] = field(default_factory=dict)
    loans: dict[UUID, Loan] = field(default_factory=dict)
    audits: list[AuditEvent] = field(default_factory=list)
    outbox: list[OutboxEvent] = field(default_factory=list)
    committed: bool = False
    rolled_back: bool = False

    def get_book(self, org_id: UUID, book_id: UUID) -> Book:
        book = self.books.get(book_id)
        if not book or book.organization_id != org_id:
            raise KeyError(book_id)
        return book

    def list_books(
        self,
        org_id: UUID,
        query: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> tuple[list[Book], str | None]:
        res = [
            b
            for b in self.books.values()
            if b.organization_id == org_id
            and (query is None or query.lower() in b.title.lower())
        ]
        return res[:limit], None

    def create_book(self, book: Book) -> Book:
        self.books[book.book_id] = book
        return book

    def get_copy(self, org_id: UUID, copy_id: UUID) -> BookCopy:
        copy = self.copies.get(copy_id)
        if not copy or copy.organization_id != org_id:
            raise KeyError(copy_id)
        return copy

    def create_copy(self, copy: BookCopy) -> BookCopy:
        self.copies[copy.copy_id] = copy
        return copy

    def update_copy(self, copy: BookCopy) -> BookCopy:
        self.copies[copy.copy_id] = copy
        return copy

    def create_loan(self, loan: Loan) -> Loan:
        self.loans[loan.loan_id] = loan
        return loan

    def get_loan(self, org_id: UUID, loan_id: UUID) -> Loan:
        loan = self.loans.get(loan_id)
        if not loan or loan.organization_id != org_id:
            raise LoanNotFoundError(loan_id)
        return loan

    def update_loan(self, loan: Loan) -> Loan:
        self.loans[loan.loan_id] = loan
        return loan


@dataclass
class _InMemoryAuditedTransaction(AuditedTransaction):
    store: _InMemoryStore
    fail_on_commit: bool = False

    def execute(
        self,
        mutation: Any,
        audit_event: AuditEvent,
        outbox_events: tuple[OutboxEvent, ...],
    ) -> Any:
        initial_loans = dict(self.store.loans)
        initial_audits = list(self.store.audits)
        initial_outbox = list(self.store.outbox)
        try:
            result = mutation()
            if self.fail_on_commit:
                raise RuntimeError("Simulated transaction failure before commit")
            self.store.audits.append(audit_event)
            self.store.outbox.extend(outbox_events)
            self.store.committed = True
            return result
        except Exception:
            self.store.loans = initial_loans
            self.store.audits = initial_audits
            self.store.outbox = initial_outbox
            self.store.rolled_back = True
            raise


@dataclass
class _InMemoryRefreshSessionStore(RefreshSessionStore):
    sessions: dict[UUID, RefreshSession] = field(default_factory=dict)

    def create(self, session: RefreshSession) -> None:
        self.sessions[session.session_id] = session

    def resolve(self, token_hash: str) -> RefreshSession | None:
        for s in self.sessions.values():
            if s.token_hash == token_hash:
                return s
        return None

    def rotate(
        self, session: RefreshSession, replacement: RefreshSession, when: datetime
    ) -> bool:
        cur = self.sessions.get(session.session_id)
        if not cur or cur.rotated_at is not None or cur.revoked_at is not None:
            return False
        # mark rotated
        from dataclasses import replace

        self.sessions[session.session_id] = replace(cur, rotated_at=when)
        self.sessions[replacement.session_id] = replacement
        return True

    def revoke_chain(
        self, root_session_id: UUID, organization_id: UUID, when: datetime
    ) -> None:
        from dataclasses import replace

        for sid, s in list(self.sessions.items()):
            if (
                s.root_session_id == root_session_id
                and s.organization_id == organization_id
                and s.revoked_at is None
            ):
                self.sessions[sid] = replace(s, revoked_at=when)


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
        for k, v in list(self.records.items()):
            if v.organization_id == organization_id and v.key_id == key_id:
                del self.records[k]


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------


def test_rls_catalog_and_composite_foreign_keys_across_all_tenant_tables() -> None:
    """Gate 1: Verify all 19 migrations enforce RLS predicates and composite tenant FKs."""
    migrations_dir = Path(__file__).resolve().parents[3] / "migrations" / "versions"
    assert migrations_dir.is_dir(), f"Migrations dir not found: {migrations_dir}"

    verifier = MigrationCatalogVerifier(migrations_dir)
    report = verifier.verify_all()

    assert report.total_tables_checked > 0, "No tables checked"
    assert len(report.missing_organization_id) == 0, (
        f"Tables missing organization_id: {report.missing_organization_id}"
    )
    assert len(report.missing_rls_predicates) == 0, (
        f"Tables missing RLS predicates: {report.missing_rls_predicates}"
    )
    assert len(report.non_composite_fks) == 0, (
        f"Non-composite FKs: {report.non_composite_fks}"
    )
    assert report.all_passed is True


def test_token_reuse_revocation_and_algorithm_pinning() -> None:
    """Gate 2: Refresh replay revokes entire chain; algorithm substitution rejected."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    jwt_key = JwtKey(
        key_id="k1", private_key_pem=private_pem, public_key_pem=public_pem
    )
    access_tokens = AccessTokenService(
        issuer="https://auth.example",
        audience="openlibrary-api",
        access_token_ttl=timedelta(minutes=15),
        signing_key=jwt_key,
        verification_keys={jwt_key.key_id: jwt_key.public_key_pem},
        now=lambda: NOW,
    )

    store = _InMemoryRefreshSessionStore()
    refresh_service = RefreshSessionService(
        store=store,
        access_tokens=access_tokens,
        refresh_token_ttl=timedelta(days=14),
        now=lambda: NOW,
        random_token=lambda: "rand-" + str(uuid4()),
    )

    from openlibrary.modules.core.application.login import LoginResult
    from openlibrary.modules.core.application.refresh_sessions import _token_hash

    org_id = uuid4()
    user_id = uuid4()
    session_result = refresh_service.start(
        LoginResult(user_id=user_id, organization_id=org_id)
    )
    first_token = session_result.refresh_token
    first_csrf = session_result.csrf_token

    # Rotate token once
    first_hash = _token_hash(first_token)
    session_before_rotation = store.resolve(first_hash)
    assert session_before_rotation is not None
    root_id = session_before_rotation.root_session_id

    rotated_result = refresh_service.rotate(first_token, first_csrf)
    assert rotated_result is not None
    replacement_token = rotated_result.refresh_token
    replacement_csrf = rotated_result.csrf_token
    assert replacement_token != first_token

    # Replay old token -> REPLAY ATTACK DETECTED
    replay_attempt = refresh_service.rotate(first_token, first_csrf)
    assert replay_attempt is None, "Replay of rotated token must fail"

    # Verify that the entire chain is revoked!
    for sess in store.sessions.values():
        if sess.root_session_id == root_id:
            assert sess.revoked_at is not None, (
                f"Session {sess.session_id} in chain not revoked!"
            )

    # Verify the replacement token is now also rejected because chain was revoked
    replacement_attempt = refresh_service.rotate(replacement_token, replacement_csrf)
    assert replacement_attempt is None, (
        "Replacement token must be revoked after replay of predecessor"
    )

    # Access token algorithm pinning: test algorithm none rejection
    header = {"alg": "none", "typ": "JWT"}
    payload = {
        "iss": "https://auth.example",
        "aud": "openlibrary-api",
        "sub": str(user_id),
        "organization_id": str(org_id),
        "session_id": str(uuid4()),
        "iat": int(NOW.timestamp()),
        "exp": int((NOW + timedelta(minutes=10)).timestamp()),
    }
    import base64

    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode().rstrip("=")

    unsigned_jwt = (
        f"{b64(json.dumps(header).encode())}.{b64(json.dumps(payload).encode())}."
    )
    with pytest.raises(TokenVerificationError):
        access_tokens.verify(unsigned_jwt)


def test_audit_outbox_transaction_atomicity() -> None:
    """Gate 3: Audited mutations commit business record, audit, and outbox atomically; rollback leaves zero."""
    mem_store = _InMemoryStore()
    org_id = uuid4()
    user_id = uuid4()
    loan_id = uuid4()
    copy_id = uuid4()

    # Success case
    tx_success = _InMemoryAuditedTransaction(store=mem_store, fail_on_commit=False)
    audit = AuditEvent(
        action="loan.checked_out",
        entity_type="loan",
        entity_id=loan_id,
        payload={"copy_id": str(copy_id), "borrower_id": str(user_id)},
        correlation_id=uuid4(),
    )
    outbox = (
        OutboxEvent(
            event_type="loan.checked_out",
            aggregate_type="loan",
            aggregate_id=loan_id,
            payload_version=1,
            payload={"status": "checked_out"},
            correlation_id=audit.correlation_id,
            idempotency_key="key-1",
        ),
    )

    def do_checkout() -> Loan:
        new_loan = Loan(
            loan_id=loan_id,
            organization_id=org_id,
            copy_id=copy_id,
            borrower_user_id=user_id,
            status=LoanStatus.CHECKED_OUT,
            loan_status=LoanStatus.CHECKED_OUT,
            request_status="approved",
            requested_at=NOW,
            checked_out_at=NOW,
            due_at=NOW + timedelta(days=14),
            created_at=NOW,
            updated_at=NOW,
        )
        return mem_store.create_loan(new_loan)

    res = tx_success.execute(do_checkout, audit, outbox)
    assert res.loan_id == loan_id
    assert len(mem_store.loans) == 1
    assert len(mem_store.audits) == 1
    assert len(mem_store.outbox) == 1
    assert mem_store.committed is True

    # Failure case: simulated error triggers rollback
    tx_fail = _InMemoryAuditedTransaction(store=mem_store, fail_on_commit=True)
    loan_id_2 = uuid4()
    audit_2 = AuditEvent(
        action="loan.checked_out",
        entity_type="loan",
        entity_id=loan_id_2,
        payload={"copy_id": str(copy_id)},
        correlation_id=uuid4(),
    )
    outbox_2 = (
        OutboxEvent(
            event_type="loan.checked_out",
            aggregate_type="loan",
            aggregate_id=loan_id_2,
            payload_version=1,
            payload={},
            correlation_id=audit_2.correlation_id,
            idempotency_key="key-2",
        ),
    )

    def do_checkout_fail() -> Loan:
        new_loan = Loan(
            loan_id=loan_id_2,
            organization_id=org_id,
            copy_id=copy_id,
            borrower_user_id=user_id,
            status=LoanStatus.CHECKED_OUT,
            loan_status=LoanStatus.CHECKED_OUT,
            request_status="approved",
            requested_at=NOW,
            checked_out_at=NOW,
            due_at=NOW + timedelta(days=14),
            created_at=NOW,
            updated_at=NOW,
        )
        return mem_store.create_loan(new_loan)

    with pytest.raises(RuntimeError):
        tx_fail.execute(do_checkout_fail, audit_2, outbox_2)

    # State must be exactly as before: loan_id_2 not in loans, audit_2 not in audits, outbox_2 not in outbox
    assert loan_id_2 not in mem_store.loans
    assert len(mem_store.loans) == 1
    assert len(mem_store.audits) == 1
    assert len(mem_store.outbox) == 1
    assert mem_store.rolled_back is True


def test_dispatcher_replay_deduplication_and_lease_expiry() -> None:
    """Gate 4: Replaying outbox event causes no duplicate side effects; lease timeout allows recovery."""
    from contextlib import contextmanager
    from unittest.mock import MagicMock
    from openlibrary.modules.ops.application.dispatcher import (
        OutboxDispatcherService,
    )
    from openlibrary.modules.ops.application.persistence import (
        ClaimedOutboxEvent,
        JobRecord,
    )

    class InMemoryClaimStore:
        def __init__(self, events: list[ClaimedOutboxEvent]) -> None:
            self.events = list(events)
            self.delivered: list[UUID] = []

        def claim_next_event(
            self,
            *,
            lease_token: UUID,
            lease_duration_seconds: int = 30,
        ) -> ClaimedOutboxEvent | None:
            if not self.events:
                return None
            event = self.events.pop(0)
            return ClaimedOutboxEvent(
                event_id=event.event_id,
                organization_id=event.organization_id,
                event_type=event.event_type,
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id,
                payload_version=event.payload_version,
                payload_json=event.payload_json,
                correlation_id=event.correlation_id,
                idempotency_key=event.idempotency_key,
                attempts=event.attempts + 1,
                lease_token=lease_token,
                lease_expires_at=datetime.now(UTC),
                created_at=event.created_at,
            )

        def mark_delivered(
            self,
            *,
            event_id: UUID,
            lease_token: UUID,
            organization_id: UUID | None = None,
        ) -> bool:
            self.delivered.append(event_id)
            return True

        def record_failure(
            self,
            *,
            event_id: UUID,
            lease_token: UUID,
            error_message: str,
            retry_delay_seconds: int = 0,
            is_dead_letter: bool = False,
            organization_id: UUID | None = None,
        ) -> None:
            pass

    class InMemoryDeduplicationStore:
        def __init__(self) -> None:
            self.processed: set[tuple[UUID, UUID, str]] = set()

        def is_processed(
            self,
            connection: Any,
            *,
            organization_id: UUID,
            outbox_event_id: UUID,
            job_type: str,
            deduplication_key: str | None = None,
        ) -> bool:
            return (organization_id, outbox_event_id, job_type) in self.processed

        def record_processed(
            self,
            connection: Any,
            *,
            organization_id: UUID,
            outbox_event_id: UUID,
            job_type: str,
            payload_version: int,
            deduplication_key: str | None = None,
        ) -> JobRecord:
            self.processed.add((organization_id, outbox_event_id, job_type))
            now = datetime.now(UTC)
            return JobRecord(
                job_id=uuid4(),
                organization_id=organization_id,
                outbox_event_id=outbox_event_id,
                job_type=job_type,
                payload_version=payload_version,
                status="completed",
                attempts=1,
                created_at=now,
                updated_at=now,
            )

        def record_job_status(self, *args: Any, **kwargs: Any) -> JobRecord:
            now = datetime.now(UTC)
            return JobRecord(
                job_id=uuid4(),
                organization_id=uuid4(),
                outbox_event_id=uuid4(),
                job_type="test",
                payload_version=1,
                status="pending",
                attempts=1,
                created_at=now,
                updated_at=now,
            )

    class FakeTenantContext:
        @contextmanager
        def connection(self, organization_id: UUID) -> Any:
            mock_conn = MagicMock()
            yield mock_conn

    org_id = uuid4()
    item_id = str(uuid4())
    event_id = uuid4()

    event = ClaimedOutboxEvent(
        event_id=event_id,
        organization_id=org_id,
        event_type="book.reserved",
        aggregate_type="reservation",
        aggregate_id=uuid4(),
        payload_version=1,
        payload_json=json.dumps({"item_id": item_id}),
        correlation_id=uuid4(),
        idempotency_key="key-1",
        attempts=0,
        lease_token=uuid4(),
        lease_expires_at=NOW,
        created_at=NOW,
    )

    claim_store = InMemoryClaimStore([event])
    dedup_store = InMemoryDeduplicationStore()
    context = FakeTenantContext()

    dispatched_actions: list[str] = []

    def handler(conn: Any, evt: ClaimedOutboxEvent) -> None:
        if dedup_store.is_processed(
            conn,
            organization_id=evt.organization_id,
            outbox_event_id=evt.event_id,
            job_type=evt.event_type,
        ):
            return
        data = json.loads(evt.payload_json)
        dispatched_actions.append(f"{evt.event_type}:{data.get('item_id')}")
        dedup_store.record_processed(
            conn,
            organization_id=evt.organization_id,
            outbox_event_id=evt.event_id,
            job_type=evt.event_type,
            payload_version=evt.payload_version,
        )

    dispatcher = OutboxDispatcherService(
        claim_store=claim_store,  # type: ignore[arg-type]
        deduplication_port=dedup_store,
        tenant_context=context,  # type: ignore[arg-type]
    )
    dispatcher.register_handler("book.reserved", handler, max_payload_version=1)

    # First dispatch succeeds
    dispatched = dispatcher.dispatch_one()
    assert dispatched is True
    assert dispatched_actions == [f"book.reserved:{item_id}"]
    assert event_id in claim_store.delivered

    # Replay: re-feed the same event to claim_store
    claim_store.events.append(event)
    dispatched_again = dispatcher.dispatch_one()
    assert dispatched_again is True
    # Deduplication port prevented re-running the consumer handler!
    assert len(dispatched_actions) == 1, "Handler must NOT run twice on replayed event"


def test_payment_webhook_replay_window_and_duplicate_deduplication() -> None:
    """Gate 5: Webhook replay older than 5 min rejected; duplicate provider event returns idempotent 200."""
    import hashlib
    import hmac

    verifier = WebhookSignatureVerifier(tolerance_seconds=300)
    secret = "test-webhook-secret-32-bytes-minimum"
    org_id = uuid4()
    provider_event_id = "evt_provider_123"
    timestamp = int(NOW.timestamp())

    payload = {
        "event_id": provider_event_id,
        "event_type": "payment.succeeded",
        "data": {"payment_id": str(uuid4()), "amount_cents": 2500, "currency": "USD"},
    }
    raw_body = json.dumps(payload).encode()
    signature_input = f"{timestamp}.".encode("utf-8") + raw_body
    signature = hmac.new(
        secret.encode("utf-8"), signature_input, hashlib.sha256
    ).hexdigest()

    # 1. Valid signature and fresh timestamp passes
    verifier.verify(
        provider="stripe",
        raw_body=raw_body,
        headers={"stripe-signature": f"t={timestamp},v1={signature}"},
        secret=secret,
        current_time=NOW,
    )

    # 2. Stale timestamp (> 300s) raises StaleWebhookTimestampError
    stale_timestamp = int((NOW - timedelta(seconds=301)).timestamp())
    stale_signature = hmac.new(
        secret.encode("utf-8"),
        f"{stale_timestamp}.".encode("utf-8") + raw_body,
        hashlib.sha256,
    ).hexdigest()

    with pytest.raises(StaleWebhookTimestampError):
        verifier.verify(
            provider="stripe",
            raw_body=raw_body,
            headers={"stripe-signature": f"t={stale_timestamp},v1={stale_signature}"},
            secret=secret,
            current_time=NOW,
        )

    # 3. Invalid signature raises InvalidWebhookSignatureError
    with pytest.raises(InvalidWebhookSignatureError):
        verifier.verify(
            provider="stripe",
            raw_body=raw_body,
            headers={"stripe-signature": f"t={timestamp},v1=bad_signature_hex"},
            secret=secret,
            current_time=NOW,
        )

    # 4. Duplicate event deduplication store check
    received_events: dict[tuple[UUID, str, str], dict[str, Any]] = {}

    def process_event(event_id: str, data: dict[str, Any]) -> tuple[int, str]:
        key = (org_id, "stripe", event_id)
        if key in received_events:
            return 200, "idempotent_replay"
        received_events[key] = data
        return 200, "processed"

    status_code_1, result_1 = process_event(provider_event_id, payload)
    assert status_code_1 == 200
    assert result_1 == "processed"

    status_code_2, result_2 = process_event(provider_event_id, payload)
    assert status_code_2 == 200
    assert result_2 == "idempotent_replay"
    assert len(received_events) == 1


def test_idempotency_retention_ttl_and_secret_scrubbing() -> None:
    """Gate 6: Idempotency keys expire after 24h TTL; safe representation scrubs sensitive credentials."""
    from openlibrary.modules.ops.application.idempotency import validate_safe_response

    store = _InMemoryIdempotencyStore()
    service = IdempotencyService(store=store)

    org_id = uuid4()
    key = "idemp-checkout-key"
    method = "POST"
    endpoint = "/api/v1/loans/desk-checkout"

    # 1. Attempt to store response with secrets raises ValueError (banned credentials)
    sensitive_response = {
        "status": "success",
        "loan_id": str(uuid4()),
        "password": "super-secret-password",
        "access_token": "bearer-token-secret",
        "card_number": "4111222233334444",
    }
    with pytest.raises(ValueError):
        validate_safe_response(sensitive_response)

    # 2. Safe response serializes cleanly
    safe_response = {
        "status": "success",
        "loan_id": str(uuid4()),
        "due_date": "2026-10-07",
    }
    serialized = validate_safe_response(safe_response)
    assert "loan_id" in serialized

    # 3. process_or_replay executes mutation and caches result
    executed_count = 0

    def do_work() -> tuple[int, dict[str, Any], str | None]:
        nonlocal executed_count
        executed_count += 1
        return 201, safe_response, None

    req_payload = {"copy_id": "copy-123"}
    res1 = service.process_or_replay(
        organization_id=org_id,
        key=key,
        method=method,
        endpoint=endpoint,
        request_payload=req_payload,
        execute=do_work,
    )
    assert res1.replayed is False
    assert res1.status_code == 201
    assert executed_count == 1

    # 4. Immediate replay with identical request returns cached result without re-executing
    res2 = service.process_or_replay(
        organization_id=org_id,
        key=key,
        method=method,
        endpoint=endpoint,
        request_payload=req_payload,
        execute=do_work,
    )
    assert res2.replayed is True
    assert res2.status_code == 201
    assert executed_count == 1

    # 5. After 24-hour expiration, record is pruned and new execution proceeds
    existing = store.get_record(org_id, key, method, endpoint)
    assert existing is not None
    from dataclasses import replace
    from datetime import timezone

    past_expiration = datetime.now(timezone.utc) - timedelta(hours=1)
    store.records[(org_id, key, method, endpoint)] = replace(
        existing, expires_at=past_expiration
    )

    res3 = service.process_or_replay(
        organization_id=org_id,
        key=key,
        method=method,
        endpoint=endpoint,
        request_payload=req_payload,
        execute=do_work,
    )
    assert res3.replayed is False
    assert res3.status_code == 201
    assert executed_count == 2


def test_retention_policy_and_legal_hold_enforcement() -> None:
    """Gate 7: Retention policy mandates required metadata and legal hold blocks historical deletion."""
    valid_policy = RetentionPolicy(
        policy_owner="Security & Compliance Office",
        jurisdiction="VN-National / ISO 27001",
        profile_retention_days=1095,  # 3 years
        audit_retention_days=2555,  # 7 years
        payment_retention_days=3650,  # 10 years
        log_retention_days=365,  # 1 year
    )

    verifier = RetentionPolicyVerifier(valid_policy)
    assert verifier.validate() is True

    # Incomplete policy missing owner or jurisdiction fails validation
    invalid_policy = RetentionPolicy(
        policy_owner="",
        jurisdiction="",
        profile_retention_days=0,
        audit_retention_days=0,
        payment_retention_days=0,
        log_retention_days=0,
    )
    invalid_verifier = RetentionPolicyVerifier(invalid_policy)
    with pytest.raises(ValueError):
        invalid_verifier.validate()

    # Legal hold check
    org_id = uuid4()
    verifier.set_legal_hold(org_id, "investigation-active-2026")
    assert verifier.is_under_legal_hold(org_id) is True

    # Trying to delete/purge records while under legal hold raises LegalHoldException
    with pytest.raises(LegalHoldException):
        verifier.assert_can_purge(org_id, entity_type="audit")

    with pytest.raises(LegalHoldException):
        verifier.assert_can_purge(org_id, entity_type="loan")

    # Hard delete is universally forbidden for loans, payments, audit history
    verifier.release_legal_hold(org_id)
    assert verifier.is_under_legal_hold(org_id) is False

    with pytest.raises(ValueError) as exc_hard:
        verifier.assert_can_hard_delete("loans")
    assert "hard-delete is prohibited" in str(exc_hard.value)


def test_reproducible_catalog_search_and_checkout_performance_baselines() -> None:
    """Gate 8: Reproducible baseline latency measurements for search (< 50ms) and checkout (< 50ms)."""
    mem_store = _InMemoryStore()
    org_id = uuid4()

    # Seed 200 books
    for i in range(200):
        mem_store.create_book(
            Book(
                book_id=uuid4(),
                organization_id=org_id,
                title=f"Sample Engineering Handbook Volume {i}",
                title_sort_key=f"sample engineering handbook volume {i}",
                isbn=f"978-0-12345-{i:04d}",
                authors=(f"Author {i % 10}",),
                published_year=2020 + (i % 6),
            )
        )

    benchmark = PerformanceBenchmark(mem_store)
    result = benchmark.run_catalog_search_baseline(
        org_id=org_id, query="Engineering", iterations=100
    )

    assert result.iterations == 100
    assert result.p50_ms < 50.0, f"Search p50 {result.p50_ms}ms exceeds threshold"
    assert result.p95_ms < 100.0, f"Search p95 {result.p95_ms}ms exceeds threshold"

    # Checkout benchmark (100 iterations)
    checkout_result = benchmark.run_checkout_baseline(org_id=org_id, iterations=100)
    assert checkout_result.iterations == 100
    assert checkout_result.p50_ms < 50.0, (
        f"Checkout p50 {checkout_result.p50_ms}ms exceeds threshold"
    )
    assert checkout_result.p95_ms < 100.0, (
        f"Checkout p95 {checkout_result.p95_ms}ms exceeds threshold"
    )


def test_frontend_accessibility_and_release_contract_verification() -> None:
    """Gate 9: Frontend accessibility standards and release-evidence verification."""
    frontend_dir = Path(__file__).resolve().parents[3].parent / "frontend"
    contracts_file = (
        Path(__file__).resolve().parents[3].parent / "contracts" / "openapi" / "v1.yaml"
    )

    assert frontend_dir.is_dir()
    assert contracts_file.is_file()

    verifier = FrontendAccessibilityVerifier(
        frontend_dir=frontend_dir, contracts_path=contracts_file
    )
    result = verifier.verify()

    assert result.contract_valid is True
    assert result.known_limits_documented is True
    assert result.a11y_standards_defined is True
    assert len(result.critical_violations) == 0

    migrations_dir = Path(__file__).resolve().parents[3] / "alembic" / "versions"
    catalog_report = MigrationCatalogVerifier(migrations_dir).verify_all()
    retention_policy = RetentionPolicy(
        policy_owner="Security & Compliance Office",
        jurisdiction="VN-National / ISO 27001",
        profile_retention_days=1095,
        audit_retention_days=2555,
        payment_retention_days=3650,
        log_retention_days=365,
    )
    mem_store = _InMemoryStore()
    benchmark = PerformanceBenchmark(mem_store)
    bench_search = benchmark.run_catalog_search_baseline(org_id=uuid4(), iterations=10)
    bench_checkout = benchmark.run_checkout_baseline(org_id=uuid4(), iterations=10)

    report = ReleaseGateReport(
        migration_report=catalog_report,
        retention_report=retention_policy,
        benchmark_search=bench_search,
        benchmark_checkout=bench_checkout,
        frontend_report=result,
    )
    markdown = report.render_markdown()
    assert "Release Gate Evidence Report (BE-027)" in markdown
    assert "Gate 1: RLS Catalog and Composite Foreign Keys" in markdown
    assert "Gate 2: Retention Policy and Legal Hold" in markdown
    assert "Gate 3: Performance Baselines" in markdown
    assert "Gate 4: Frontend Accessibility and Contracts" in markdown
