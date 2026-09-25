"""Integration coverage for BE-019: overdue calculation, tenant isolation, and repeat job execution."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from openlibrary.infrastructure.sqlserver.migrate import (
    bootstrap_database_identities,
    connect,
    database_url_for,
    run_migrations,
)
from openlibrary.modules.core.application.overdue import (
    CIRCULATION_SCHEDULED_OVERDUE_EVENT,
    OverdueEvaluator,
    enqueue_scheduled_circulation_job,
    register_circulation_scheduled_jobs,
)
from openlibrary.modules.core.application.reservations import (
    ReservationService,
)
from openlibrary.modules.core.domain.loans import LoanStatus
from openlibrary.modules.core.infrastructure.copy_status import SqlServerCopyStatusStore
from openlibrary.modules.core.infrastructure.loans import SqlServerLoanStore
from openlibrary.modules.core.infrastructure.organizations import set_tenant_context
from openlibrary.modules.core.infrastructure.reservations import (
    SqlServerReservationStore,
)
from openlibrary.modules.core.infrastructure.tenancy import SqlServerTenantContext
from openlibrary.modules.ops.application.dispatcher import OutboxDispatcherService
from openlibrary.modules.ops.infrastructure.dispatcher import (
    SqlServerConsumerDeduplicationStore,
    SqlServerOutboxClaimStore,
)
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


@pytest.fixture
def clean_database_urls(database_urls: SqlServerUrls) -> Iterator[SqlServerUrls]:
    """Create a disposable database, run migrations, and tear down cleanly."""
    database_name = f"openlibrary_be019_{uuid4().hex}"
    bootstrap_url = database_urls["DATABASE_BOOTSTRAP_URL"]
    with connect(bootstrap_url, database="master") as connection:
        connection.execute(f"CREATE DATABASE [{database_name}]")

    urls = SqlServerUrls(
        {
            name: database_url_for(url, database_name)
            for name, url in database_urls.items()
        }
    )
    migration_login = f"be019_migrator_{uuid4().hex}"
    runtime_login = f"be019_runtime_{uuid4().hex}"
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

    org_a = uuid4()
    org_b = uuid4()
    user_a = uuid4()
    user_b = uuid4()
    with connect(urls["DATABASE_BOOTSTRAP_URL"]) as connection:
        connection.execute(
            "INSERT INTO core.organizations "
            "(organization_id, name, slug, organization_type, status, timezone, settings_json) "
            f"VALUES ('{org_a}', N'Campus Alpha', 'campus-alpha', 'education', 'active', 'UTC', N'{{}}'), "
            f"('{org_b}', N'Campus Beta', 'campus-beta', 'education', 'active', 'UTC', N'{{}}')"
        )
        connection.execute(
            "INSERT INTO core.users "
            "(user_id, organization_id, email, status, password_hash) "
            f"VALUES ('{user_a}', '{org_a}', 'user_a@example.com', 'active', 'hash'), "
            f"('{user_b}', '{org_b}', 'user_b@example.com', 'active', 'hash')"
        )
        connection.execute(
            "INSERT INTO core.user_profiles "
            "(profile_id, organization_id, user_id, display_name) "
            f"VALUES ('{uuid4()}', '{org_a}', '{user_a}', N'Patron Alpha'), "
            f"('{uuid4()}', '{org_b}', '{user_b}', N'Patron Beta')"
        )

    urls["ORGANIZATION_A"] = str(org_a)
    urls["ORGANIZATION_B"] = str(org_b)
    urls["USER_A"] = str(user_a)
    urls["USER_B"] = str(user_b)

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


def _seed_book_and_copy(database_url: str, org_id: UUID) -> tuple[UUID, UUID]:
    book_id = uuid4()
    loc_id = uuid4()
    copy_id = uuid4()
    with connect(database_url) as connection:
        connection.execute(
            "INSERT INTO core.locations (location_id, organization_id, code, name, status) "
            f"VALUES ('{loc_id}', '{org_id}', 'LOC-{uuid4().hex[:4]}', N'Main Shelf', 'active')"
        )
        connection.execute(
            "INSERT INTO core.books (book_id, organization_id, title, title_sort_key, isbn, authors_json, published_year) "
            f"VALUES ('{book_id}', '{org_id}', N'Test Book', N'test book', '978-0000000000', N'[\"Author\"]', 2020)"
        )
        connection.execute(
            "INSERT INTO core.book_copies (copy_id, organization_id, book_id, barcode, location_id, status, condition_code, acquired_at) "
            f"VALUES ('{copy_id}', '{org_id}', '{book_id}', 'BC-{uuid4().hex[:6]}', '{loc_id}', 'checked_out', 'good', SYSUTCDATETIME())"
        )
    return book_id, copy_id


def _seed_checked_out_loan(
    database_url: str,
    *,
    organization_id: UUID,
    borrower_user_id: UUID,
    copy_id: UUID,
    due_at: datetime,
) -> UUID:
    loan_id = uuid4()
    now = datetime.now(timezone.utc)
    engine = create_engine(database_url)
    with engine.connect() as conn:
        set_tenant_context(conn, organization_id)
        conn.execute(
            text(
                "INSERT INTO core.loans (loan_id, organization_id, copy_id, borrower_user_id, "
                "status, loan_status, request_status, requested_at, approved_at, checked_out_at, "
                "due_at, returned_at, policy_snapshot_json, created_at, updated_at) "
                "VALUES (:loan_id, :organization_id, :copy_id, :borrower_user_id, "
                ":status, :loan_status, :request_status, :requested_at, :approved_at, :checked_out_at, "
                ":due_at, NULL, '{}', :created_at, :updated_at)"
            ),
            {
                "loan_id": str(loan_id),
                "organization_id": str(organization_id),
                "copy_id": str(copy_id),
                "borrower_user_id": str(borrower_user_id),
                "status": LoanStatus.CHECKED_OUT,
                "loan_status": LoanStatus.CHECKED_OUT,
                "request_status": "fulfilled",
                "requested_at": now - timedelta(days=20),
                "approved_at": now - timedelta(days=19),
                "checked_out_at": now - timedelta(days=18),
                "due_at": due_at,
                "created_at": now - timedelta(days=20),
                "updated_at": now - timedelta(days=18),
            },
        )
        conn.commit()
    engine.dispose()
    return loan_id


def test_overdue_loan_transition_under_rls(clean_database_urls: SqlServerUrls) -> None:
    """Overdue evaluator transitions due loans, writes outbox events, and updates job records."""
    org_id = UUID(clean_database_urls["ORGANIZATION_A"])
    user_id = UUID(clean_database_urls["USER_A"])
    runtime_url = clean_database_urls["DATABASE_RUNTIME_URL"]

    now = datetime.now(timezone.utc)
    book_id, copy_id = _seed_book_and_copy(
        clean_database_urls["DATABASE_BOOTSTRAP_URL"], org_id
    )

    # 1. Seed loan that became due 2 days ago
    loan_id = _seed_checked_out_loan(
        runtime_url,
        organization_id=org_id,
        borrower_user_id=user_id,
        copy_id=copy_id,
        due_at=now - timedelta(days=2),
    )

    # 2. Setup services
    loan_store = SqlServerLoanStore(runtime_url)
    claim_store = SqlServerOutboxClaimStore(runtime_url)
    dedup_store = SqlServerConsumerDeduplicationStore()
    tenant_context = SqlServerTenantContext(runtime_url)
    audited_tx = SqlServerAuditedTransaction()

    evaluator = OverdueEvaluator(
        loan_store=loan_store,
        transaction=audited_tx,
        clock=lambda: now,
    )

    # 3. Enqueue scheduled job in tenant outbox
    engine = create_engine(runtime_url)
    with engine.connect() as conn:
        set_tenant_context(conn, org_id)
        event = enqueue_scheduled_circulation_job(
            conn,
            organization_id=org_id,
            job_type=CIRCULATION_SCHEDULED_OVERDUE_EVENT,
        )
        conn.commit()
    engine.dispose()

    # 4. Dispatch job through generic worker dispatcher
    dispatcher = OutboxDispatcherService(
        claim_store=claim_store,
        deduplication_port=dedup_store,
        tenant_context=tenant_context,
        lease_duration_seconds=30,
    )

    dummy_res_service = ReservationService(
        reservation_store=SqlServerReservationStore(runtime_url),
        copy_store=SqlServerCopyStatusStore(runtime_url),
        authorizer=None,  # type: ignore[arg-type]
    )

    register_circulation_scheduled_jobs(
        dispatcher,
        overdue_evaluator=evaluator,
        reservation_service=dummy_res_service,
        deduplication_port=dedup_store,
        clock=lambda: now,
    )

    assert dispatcher.dispatch_one() is True

    # 5. Verify loan status is now 'overdue'
    with engine.connect() as conn:
        set_tenant_context(conn, org_id)
        row = conn.execute(
            text("SELECT status, loan_status FROM core.loans WHERE loan_id = :loan_id"),
            {"loan_id": str(loan_id)},
        ).fetchone()
        assert row is not None
        assert row.status == LoanStatus.OVERDUE
        assert row.loan_status == LoanStatus.OVERDUE

        # Verify outbox event 'circulation.loan_overdue' emitted
        outbox_row = conn.execute(
            text(
                "SELECT event_type, aggregate_id, idempotency_key "
                "FROM ops.outbox_events "
                "WHERE organization_id = :org_id AND aggregate_id = :loan_id"
            ),
            {"org_id": str(org_id), "loan_id": str(loan_id)},
        ).fetchone()
        assert outbox_row is not None
        assert outbox_row.event_type == "circulation.loan_overdue"
        assert outbox_row.idempotency_key == f"loan:{loan_id}:overdue"

        # Verify scheduled job recorded in ops.job_records as completed
        job_row = conn.execute(
            text(
                "SELECT status, attempts FROM ops.job_records "
                "WHERE organization_id = :org_id AND outbox_event_id = :event_id"
            ),
            {"org_id": str(org_id), "event_id": str(event.event_id)},
        ).fetchone()
        assert job_row is not None
        assert job_row.status == "completed"
        assert job_row.attempts == 1
    engine.dispose()


def test_repeat_overdue_job_execution_does_not_duplicate_state_or_events(
    clean_database_urls: SqlServerUrls,
) -> None:
    """Re-running one due job does not duplicate state changes or outbox events."""
    org_id = UUID(clean_database_urls["ORGANIZATION_A"])
    user_id = UUID(clean_database_urls["USER_A"])
    runtime_url = clean_database_urls["DATABASE_RUNTIME_URL"]

    now = datetime.now(timezone.utc)
    book_id, copy_id = _seed_book_and_copy(
        clean_database_urls["DATABASE_BOOTSTRAP_URL"], org_id
    )
    loan_id = _seed_checked_out_loan(
        runtime_url,
        organization_id=org_id,
        borrower_user_id=user_id,
        copy_id=copy_id,
        due_at=now - timedelta(days=1),
    )

    loan_store = SqlServerLoanStore(runtime_url)
    claim_store = SqlServerOutboxClaimStore(runtime_url)
    dedup_store = SqlServerConsumerDeduplicationStore()
    tenant_context = SqlServerTenantContext(runtime_url)
    audited_tx = SqlServerAuditedTransaction()

    evaluator = OverdueEvaluator(
        loan_store=loan_store,
        transaction=audited_tx,
        clock=lambda: now,
    )

    dispatcher = OutboxDispatcherService(
        claim_store=claim_store,
        deduplication_port=dedup_store,
        tenant_context=tenant_context,
        lease_duration_seconds=30,
    )
    dummy_res_service = ReservationService(
        reservation_store=SqlServerReservationStore(runtime_url),
        copy_store=SqlServerCopyStatusStore(runtime_url),
        authorizer=None,  # type: ignore[arg-type]
    )
    register_circulation_scheduled_jobs(
        dispatcher,
        overdue_evaluator=evaluator,
        reservation_service=dummy_res_service,
        deduplication_port=dedup_store,
        clock=lambda: now,
    )

    # Enqueue job 1
    engine = create_engine(runtime_url)
    with engine.connect() as conn:
        set_tenant_context(conn, org_id)
        event_1 = enqueue_scheduled_circulation_job(
            conn,
            organization_id=org_id,
            job_type=CIRCULATION_SCHEDULED_OVERDUE_EVENT,
        )
        conn.commit()
    engine.dispose()

    # First execution: transitions loan
    assert dispatcher.dispatch_one() is True

    # Count outbox events for this loan
    with engine.connect() as conn:
        set_tenant_context(conn, org_id)
        count_1 = conn.execute(
            text(
                "SELECT COUNT(*) FROM ops.outbox_events "
                "WHERE aggregate_id = :loan_id AND event_type = 'circulation.loan_overdue'"
            ),
            {"loan_id": str(loan_id)},
        ).scalar_one()
        assert count_1 == 1

    # Simulate repeat execution: clear delivered_at so event 1 re-runs
    with engine.connect() as conn:
        set_tenant_context(conn, org_id)
        conn.execute(
            text(
                "UPDATE ops.outbox_events "
                "SET delivered_at = NULL, lease_token = NULL, lease_expires_at = NULL, "
                "available_at = SYSUTCDATETIME() "
                "WHERE event_id = :event_id"
            ),
            {"event_id": str(event_1.event_id)},
        )
        conn.commit()

    # Replayed execution
    assert dispatcher.dispatch_one() is True

    # Crucial assertion: outbox event count is STILL 1
    with engine.connect() as conn:
        set_tenant_context(conn, org_id)
        count_2 = conn.execute(
            text(
                "SELECT COUNT(*) FROM ops.outbox_events "
                "WHERE aggregate_id = :loan_id AND event_type = 'circulation.loan_overdue'"
            ),
            {"loan_id": str(loan_id)},
        ).scalar_one()
        assert count_2 == 1
    engine.dispose()


def test_overdue_evaluation_tenant_isolation(
    clean_database_urls: SqlServerUrls,
) -> None:
    """Overdue worker receives tenant context solely from persisted work; no cross-tenant scanning."""
    org_a = UUID(clean_database_urls["ORGANIZATION_A"])
    org_b = UUID(clean_database_urls["ORGANIZATION_B"])
    user_a = UUID(clean_database_urls["USER_A"])
    user_b = UUID(clean_database_urls["USER_B"])
    runtime_url = clean_database_urls["DATABASE_RUNTIME_URL"]

    now = datetime.now(timezone.utc)
    _, copy_a = _seed_book_and_copy(
        clean_database_urls["DATABASE_BOOTSTRAP_URL"], org_a
    )
    _, copy_b = _seed_book_and_copy(
        clean_database_urls["DATABASE_BOOTSTRAP_URL"], org_b
    )

    # Both org A and org B have overdue loans
    loan_a = _seed_checked_out_loan(
        runtime_url,
        organization_id=org_a,
        borrower_user_id=user_a,
        copy_id=copy_a,
        due_at=now - timedelta(days=3),
    )
    loan_b = _seed_checked_out_loan(
        runtime_url,
        organization_id=org_b,
        borrower_user_id=user_b,
        copy_id=copy_b,
        due_at=now - timedelta(days=3),
    )

    loan_store = SqlServerLoanStore(runtime_url)
    claim_store = SqlServerOutboxClaimStore(runtime_url)
    dedup_store = SqlServerConsumerDeduplicationStore()
    tenant_context = SqlServerTenantContext(runtime_url)
    audited_tx = SqlServerAuditedTransaction()

    evaluator = OverdueEvaluator(
        loan_store=loan_store,
        transaction=audited_tx,
        clock=lambda: now,
    )
    dispatcher = OutboxDispatcherService(
        claim_store=claim_store,
        deduplication_port=dedup_store,
        tenant_context=tenant_context,
        lease_duration_seconds=30,
    )
    dummy_res_service = ReservationService(
        reservation_store=SqlServerReservationStore(runtime_url),
        copy_store=SqlServerCopyStatusStore(runtime_url),
        authorizer=None,  # type: ignore[arg-type]
    )
    register_circulation_scheduled_jobs(
        dispatcher,
        overdue_evaluator=evaluator,
        reservation_service=dummy_res_service,
        deduplication_port=dedup_store,
        clock=lambda: now,
    )

    # Enqueue scheduled job ONLY for Org A
    engine = create_engine(runtime_url)
    with engine.connect() as conn:
        set_tenant_context(conn, org_a)
        enqueue_scheduled_circulation_job(
            conn,
            organization_id=org_a,
            job_type=CIRCULATION_SCHEDULED_OVERDUE_EVENT,
        )
        conn.commit()

    # Dispatch Org A job
    assert dispatcher.dispatch_one() is True

    # Verify: Loan A is overdue
    with engine.connect() as conn:
        set_tenant_context(conn, org_a)
        row_a = conn.execute(
            text("SELECT status FROM core.loans WHERE loan_id = :loan_id"),
            {"loan_id": str(loan_a)},
        ).fetchone()
        assert row_a is not None
        assert row_a.status == LoanStatus.OVERDUE

    # Verify: Loan B remains checked_out (RLS prevented Org A job from touching Org B!)
    with engine.connect() as conn:
        set_tenant_context(conn, org_b)
        row_b = conn.execute(
            text("SELECT status FROM core.loans WHERE loan_id = :loan_id"),
            {"loan_id": str(loan_b)},
        ).fetchone()
        assert row_b is not None
        assert row_b.status == LoanStatus.CHECKED_OUT
    engine.dispose()
