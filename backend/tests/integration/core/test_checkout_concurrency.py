"""SQL Server integration coverage for BE-017 concurrent checkout locking and idempotency replay."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy.engine import make_url

from openlibrary.infrastructure.sqlserver.migrate import (
    bootstrap_database_identities,
    connect,
    database_url_for,
    run_migrations,
)
from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.authorization import AuthorizationPort
from openlibrary.modules.core.application.loans import Loan, LoanService
from openlibrary.modules.core.domain.loans import (
    CopyNotAvailableForLoanError,
    LoanStatus,
)
from openlibrary.modules.core.infrastructure.copy_status import SqlServerCopyStatusStore
from openlibrary.modules.core.infrastructure.loans import SqlServerLoanStore
from openlibrary.modules.ops.application.idempotency import (
    IdempotencyConflictError,
    IdempotencyService,
)
from openlibrary.modules.ops.infrastructure.idempotency import SqlServerIdempotencyStore
from openlibrary.modules.ops.infrastructure.sqlserver import SqlServerAuditedTransaction


class SqlServerUrls(dict[str, str]):
    """Credential-bearing integration settings with a safe pytest representation."""

    def __repr__(self) -> str:
        return "SqlServerUrls(redacted)"


@pytest.fixture(scope="module")
def database_urls() -> SqlServerUrls:
    """Return SQL Server URLs supplied only by the dedicated integration environment."""
    required_names = (
        "DATABASE_BOOTSTRAP_URL",
        "DATABASE_MIGRATION_URL",
        "DATABASE_RUNTIME_URL",
    )
    missing = [name for name in required_names if not os.environ.get(name, "").strip()]
    if missing:
        pytest.skip(f"SQL Server integration requires: {', '.join(missing)}")
    return SqlServerUrls({name: os.environ[name] for name in required_names})


@pytest.fixture(scope="module")
def seeded_database_urls(database_urls: SqlServerUrls) -> Iterator[SqlServerUrls]:
    """Create a disposable database, run migrations, and seed initial tenant entities."""
    database_name = f"openlibrary_be017_{uuid4().hex}"
    bootstrap_url = database_urls["DATABASE_BOOTSTRAP_URL"]
    with connect(bootstrap_url, database="master") as connection:
        connection.execute(f"CREATE DATABASE [{database_name}]")

    urls = SqlServerUrls(
        {
            name: database_url_for(url, database_name)
            for name, url in database_urls.items()
        }
    )
    migration_login = f"be017_migrator_{uuid4().hex}"
    runtime_login = f"be017_runtime_{uuid4().hex}"
    urls["DATABASE_MIGRATION_URL"] = (
        make_url(urls["DATABASE_MIGRATION_URL"])
        .set(username=migration_login)
        .render_as_string(hide_password=False)
    )
    urls["DATABASE_RUNTIME_URL"] = (
        make_url(urls["DATABASE_RUNTIME_URL"])
        .set(username=runtime_login)
        .render_as_string(hide_password=False)
    )

    identities = bootstrap_database_identities(
        bootstrap_url=urls["DATABASE_BOOTSTRAP_URL"],
        migration_url=urls["DATABASE_MIGRATION_URL"],
        runtime_url=urls["DATABASE_RUNTIME_URL"],
    )
    run_migrations(
        urls["DATABASE_MIGRATION_URL"],
        runtime_login=identities.runtime_login,
    )

    org_id = uuid4()
    user_id = uuid4()
    librarian_id = uuid4()
    with connect(urls["DATABASE_BOOTSTRAP_URL"]) as connection:
        connection.execute(
            "INSERT INTO core.organizations "
            "(organization_id, name, slug, organization_type, status, timezone, settings_json) "
            f"VALUES ('{org_id}', N'Campus BE017', 'campus-be017', 'education', 'active', 'UTC', N'{{}}')"
        )
        connection.execute(
            "INSERT INTO core.users "
            "(user_id, organization_id, email, full_name, user_type, status, password_hash) "
            f"VALUES ('{user_id}', '{org_id}', 'borrower@example.com', N'Borrower One', 'member', 'active', 'hash'), "
            f"('{librarian_id}', '{org_id}', 'librarian@example.com', N'Librarian Desk', 'staff', 'active', 'hash')"
        )

    urls["ORGANIZATION_ID"] = str(org_id)
    urls["BORROWER_ID"] = str(user_id)
    urls["LIBRARIAN_ID"] = str(librarian_id)

    try:
        yield urls
    finally:
        with connect(bootstrap_url, database="master") as connection:
            connection.execute(
                f"ALTER DATABASE [{database_name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE"
            )
            connection.execute(f"DROP DATABASE [{database_name}]")
            connection.execute(f"DROP LOGIN [{runtime_login}]")
            connection.execute(f"DROP LOGIN [{migration_login}]")


class _AllowAllAuthorizer(AuthorizationPort):
    def require(self, principal: Principal, permission: str) -> None:
        pass


def _seed_book_and_copy(database_url: str, org_id: UUID) -> UUID:
    book_id = uuid4()
    loc_id = uuid4()
    copy_id = uuid4()
    with connect(database_url) as connection:
        connection.execute(
            "INSERT INTO core.locations (location_id, organization_id, code, name, location_type, status) "
            f"VALUES ('{loc_id}', '{org_id}', 'LOC-BE017', N'Main Shelf', 'shelf', 'active')"
        )
        connection.execute(
            "INSERT INTO core.books (book_id, organization_id, isbn, title, author, status) "
            f"VALUES ('{book_id}', '{org_id}', '9780123456789', N'Concurrent Systems', N'Leslie Lamport', 'active')"
        )
        connection.execute(
            "INSERT INTO core.book_copies "
            "(copy_id, organization_id, book_id, barcode, location_id, status, condition_code, acquired_at) "
            f"VALUES ('{copy_id}', '{org_id}', '{book_id}', 'BC-{uuid4().hex[:6]}', '{loc_id}', 'available', 'good', SYSUTCDATETIME())"
        )
    return copy_id


def test_concurrent_checkouts_for_same_copy_yield_one_success_and_one_conflict(
    seeded_database_urls: SqlServerUrls,
) -> None:
    """Two simultaneous checkout attempts for one copy yield one success and one documented conflict."""
    org_id = UUID(seeded_database_urls["ORGANIZATION_ID"])
    librarian_id = UUID(seeded_database_urls["LIBRARIAN_ID"])
    borrower_id = UUID(seeded_database_urls["BORROWER_ID"])
    librarian_actor = Principal(librarian_id, org_id, uuid4())

    copy_id = _seed_book_and_copy(
        seeded_database_urls["DATABASE_BOOTSTRAP_URL"], org_id
    )

    db_url = seeded_database_urls["DATABASE_RUNTIME_URL"]
    loan_store = SqlServerLoanStore(db_url)
    copy_store = SqlServerCopyStatusStore(db_url)
    tx = SqlServerAuditedTransaction()

    # Create two pre-approved loans for the same copy
    now = datetime.now(timezone.utc)
    loan_1_id = uuid4()
    loan_2_id = uuid4()
    loan_store.create_loan(
        Loan(
            loan_id=loan_1_id,
            organization_id=org_id,
            copy_id=copy_id,
            borrower_user_id=borrower_id,
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
            organization_id=org_id,
            copy_id=copy_id,
            borrower_user_id=borrower_id,
            status=LoanStatus.APPROVED,
            loan_status=LoanStatus.APPROVED,
            request_status="approved",
            requested_at=now,
            approved_at=now,
            created_at=now,
            updated_at=now,
        )
    )

    service = LoanService(
        loan_store=loan_store,
        copy_store=copy_store,
        authorizer=_AllowAllAuthorizer(),
        transaction=tx,
        connection_provider=lambda o_id: copy_store._tenant_connection(o_id),
    )

    results: list[object] = []
    errors: list[Exception] = []

    def _attempt_checkout(target_loan_id: UUID) -> None:
        try:
            loan = service.checkout_loan(
                actor=librarian_actor,
                loan_id=target_loan_id,
                duration_days=14,
            )
            results.append(loan)
        except Exception as exc:
            errors.append(exc)

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(_attempt_checkout, loan_1_id)
        f2 = executor.submit(_attempt_checkout, loan_2_id)
        f1.result()
        f2.result()

    # Evidence: Exactly 1 success, 1 documented conflict
    assert len(results) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], CopyNotAvailableForLoanError)


def test_repeated_idempotency_key_returns_original_response_without_duplicate_events(
    seeded_database_urls: SqlServerUrls,
) -> None:
    """A repeated key returns the original result with no duplicate audit/outbox row."""
    org_id = UUID(seeded_database_urls["ORGANIZATION_ID"])
    db_url = seeded_database_urls["DATABASE_RUNTIME_URL"]

    store = SqlServerIdempotencyStore(db_url)
    idempotency_service = IdempotencyService(store)

    key = f"checkout-test-{uuid4().hex}"
    method = "POST"
    endpoint = "/api/v1/loans/desk-checkout"
    payload = {"copy_id": str(uuid4()), "borrower_user_id": str(uuid4())}
    response_body = {"loan_id": str(uuid4()), "status": "checked_out"}

    # First call: execute and store
    first_res = idempotency_service.process_or_replay(
        organization_id=org_id,
        key=key,
        method=method,
        endpoint=endpoint,
        request_payload=payload,
        execute=lambda: (201, response_body, str(response_body["loan_id"])),
    )
    assert first_res.status_code == 201
    assert first_res.body == response_body
    assert first_res.replayed is False

    # Second call with same key and payload: replay without executing action
    executed_second = False

    def _should_not_run() -> tuple[int, dict[str, object], str]:
        nonlocal executed_second
        executed_second = True
        return (201, {}, "")

    second_res = idempotency_service.process_or_replay(
        organization_id=org_id,
        key=key,
        method=method,
        endpoint=endpoint,
        request_payload=payload,
        execute=_should_not_run,
    )

    assert executed_second is False
    assert second_res.replayed is True
    assert second_res.status_code == 201
    assert second_res.body == response_body


def test_idempotency_key_reuse_with_different_payload_is_rejected(
    seeded_database_urls: SqlServerUrls,
) -> None:
    """Reject reuse of one key with a different payload and audit the mismatch."""
    org_id = UUID(seeded_database_urls["ORGANIZATION_ID"])
    db_url = seeded_database_urls["DATABASE_RUNTIME_URL"]

    store = SqlServerIdempotencyStore(db_url)
    idempotency_service = IdempotencyService(store)

    key = f"mismatch-key-{uuid4().hex}"
    method = "POST"
    endpoint = "/api/v1/loans/desk-checkout"

    payload_a = {"copy_id": str(uuid4()), "duration_days": 7}
    payload_b = {"copy_id": str(uuid4()), "duration_days": 14}

    idempotency_service.process_or_replay(
        organization_id=org_id,
        key=key,
        method=method,
        endpoint=endpoint,
        request_payload=payload_a,
        execute=lambda: (201, {"loan_id": str(uuid4())}, "ref-1"),
    )

    with pytest.raises(IdempotencyConflictError) as exc_info:
        idempotency_service.process_or_replay(
            organization_id=org_id,
            key=key,
            method=method,
            endpoint=endpoint,
            request_payload=payload_b,
            execute=lambda: (201, {"loan_id": str(uuid4())}, "ref-2"),
        )

    assert exc_info.value.status_code == 409
    assert "different request payload" in str(exc_info.value)


def test_expired_idempotency_record_does_not_suppress_valid_new_request(
    seeded_database_urls: SqlServerUrls,
) -> None:
    """Expired records no longer suppress a valid new request."""
    org_id = UUID(seeded_database_urls["ORGANIZATION_ID"])
    db_url = seeded_database_urls["DATABASE_RUNTIME_URL"]

    store = SqlServerIdempotencyStore(db_url)
    idempotency_service = IdempotencyService(store)

    key = f"expired-key-{uuid4().hex}"
    method = "POST"
    endpoint = "/api/v1/loans/desk-checkout"

    # Seed an already-expired record (25 hours ago)
    expired_time = datetime.now(timezone.utc) - timedelta(hours=25)
    store.save_record(
        key_id=uuid4(),
        organization_id=org_id,
        key=key,
        method=method,
        endpoint=endpoint,
        request_hash="oldhash",
        resource_reference="old-ref",
        status_code=201,
        safe_response_json=json.dumps({"loan_id": str(uuid4())}),
        created_at=expired_time - timedelta(hours=24),
        expires_at=expired_time,
    )

    # A valid new request with the same key must NOT be suppressed by the expired record
    new_payload = {"copy_id": str(uuid4())}
    new_response = {"loan_id": str(uuid4()), "status": "new_checked_out"}
    res = idempotency_service.process_or_replay(
        organization_id=org_id,
        key=key,
        method=method,
        endpoint=endpoint,
        request_payload=new_payload,
        execute=lambda: (201, new_response, str(new_response["loan_id"])),
    )

    assert res.replayed is False
    assert res.status_code == 201
    assert res.body == new_response
