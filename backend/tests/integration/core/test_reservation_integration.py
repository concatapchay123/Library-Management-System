"""Integration coverage for BE-018: deterministic reservation queue, hold expiry, and replayed allocation."""

from __future__ import annotations

from collections.abc import Iterator
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
from openlibrary.modules.core.application.reservations import (
    ReservationAllocator,
    ReservationService,
    handle_loan_returned_allocation,
)
from openlibrary.modules.core.domain.reservations import (
    ReservationStatus,
)
from openlibrary.modules.core.infrastructure.copy_status import SqlServerCopyStatusStore
from openlibrary.modules.core.infrastructure.reservations import (
    SqlServerReservationStore,
)
from openlibrary.modules.ops.application.persistence import (
    ClaimedOutboxEvent,
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


@pytest.fixture(scope="module")
def seeded_database_urls(database_urls: SqlServerUrls) -> Iterator[SqlServerUrls]:
    """Create a disposable database, run migrations, and seed initial tenant entities."""
    database_name = f"openlibrary_be018_{uuid4().hex}"
    bootstrap_url = database_urls["DATABASE_BOOTSTRAP_URL"]
    with connect(bootstrap_url, database="master") as connection:
        connection.execute(f"CREATE DATABASE [{database_name}]")

    urls = SqlServerUrls(
        {
            name: database_url_for(url, database_name)
            for name, url in database_urls.items()
        }
    )
    migration_login = f"be018_migrator_{uuid4().hex}"
    runtime_login = f"be018_runtime_{uuid4().hex}"
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
    user_1_id = uuid4()
    user_2_id = uuid4()
    user_3_id = uuid4()
    librarian_id = uuid4()
    with connect(urls["DATABASE_BOOTSTRAP_URL"]) as connection:
        connection.execute(
            "INSERT INTO core.organizations "
            "(organization_id, name, slug, organization_type, status, timezone, settings_json) "
            f"VALUES ('{org_id}', N'Campus BE018', 'campus-be018', 'education', 'active', 'UTC', N'{{}}')"
        )
        connection.execute(
            "INSERT INTO core.users "
            "(user_id, organization_id, email, full_name, user_type, status, password_hash) "
            f"VALUES ('{user_1_id}', '{org_id}', 'user1@example.com', N'Patron One', 'member', 'active', 'hash'), "
            f"('{user_2_id}', '{org_id}', 'user2@example.com', N'Patron Two', 'member', 'active', 'hash'), "
            f"('{user_3_id}', '{org_id}', 'user3@example.com', N'Patron Three', 'member', 'active', 'hash'), "
            f"('{librarian_id}', '{org_id}', 'librarian@example.com', N'Librarian Desk', 'staff', 'active', 'hash')"
        )

    urls["ORGANIZATION_ID"] = str(org_id)
    urls["USER_1_ID"] = str(user_1_id)
    urls["USER_2_ID"] = str(user_2_id)
    urls["USER_3_ID"] = str(user_3_id)
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


def _seed_book_and_copies(
    database_url: str, org_id: UUID, num_copies: int = 1
) -> tuple[UUID, list[UUID]]:
    book_id = uuid4()
    loc_id = uuid4()
    copy_ids: list[UUID] = []
    with connect(database_url) as connection:
        connection.execute(
            "INSERT INTO core.locations (location_id, organization_id, code, name, location_type, status) "
            f"VALUES ('{loc_id}', '{org_id}', 'LOC-BE018-{uuid4().hex[:4]}', N'Main Shelf', 'shelf', 'active')"
        )
        connection.execute(
            "INSERT INTO core.books (book_id, organization_id, isbn, title, author, status) "
            f"VALUES ('{book_id}', '{org_id}', '9780123456{uuid4().hex[:3]}', N'Distributed Algorithms', N'Nancy Lynch', 'active')"
        )
        for i in range(num_copies):
            copy_id = uuid4()
            copy_ids.append(copy_id)
            connection.execute(
                "INSERT INTO core.book_copies "
                "(copy_id, organization_id, book_id, barcode, location_id, status, condition_code, acquired_at) "
                f"VALUES ('{copy_id}', '{org_id}', '{book_id}', 'BC-{uuid4().hex[:6]}', '{loc_id}', 'available', 'good', SYSUTCDATETIME())"
            )
    return book_id, copy_ids


def test_deterministic_queue_ordering_within_copy_scope(
    seeded_database_urls: SqlServerUrls,
) -> None:
    """Queue ordering is deterministic and server-assigned within one book/copy scope."""
    org_id = UUID(seeded_database_urls["ORGANIZATION_ID"])
    user_1 = UUID(seeded_database_urls["USER_1_ID"])
    user_2 = UUID(seeded_database_urls["USER_2_ID"])
    user_3 = UUID(seeded_database_urls["USER_3_ID"])

    book_id, copy_ids = _seed_book_and_copies(
        seeded_database_urls["DATABASE_BOOTSTRAP_URL"], org_id, num_copies=0
    )
    db_url = seeded_database_urls["DATABASE_RUNTIME_URL"]
    reservation_store = SqlServerReservationStore(db_url)
    copy_store = SqlServerCopyStatusStore(db_url)
    tx = SqlServerAuditedTransaction()

    service = ReservationService(
        reservation_store=reservation_store,
        copy_store=copy_store,
        authorizer=_AllowAllAuthorizer(),
        transaction=tx,
        connection_provider=lambda o_id: copy_store._tenant_connection(o_id),
    )

    actor_1 = Principal(user_1, org_id, uuid4())
    actor_2 = Principal(user_2, org_id, uuid4())
    actor_3 = Principal(user_3, org_id, uuid4())

    # Create 3 reservations sequentially
    r1 = service.create_reservation(actor=actor_1, book_id=book_id)
    r2 = service.create_reservation(actor=actor_2, book_id=book_id)
    r3 = service.create_reservation(actor=actor_3, book_id=book_id)

    # Server-assigned deterministic positions: 1, 2, 3
    assert r1.queue_position == 1
    assert r2.queue_position == 2
    assert r3.queue_position == 3
    assert r1.status == ReservationStatus.PENDING
    assert r2.status == ReservationStatus.PENDING
    assert r3.status == ReservationStatus.PENDING

    # Verify query returns them deterministically ordered
    items = service.list_reservations(actor=actor_1, book_id=book_id)
    assert [item.reservation_id for item in items] == [
        r1.reservation_id,
        r2.reservation_id,
        r3.reservation_id,
    ]


def test_cancellation_does_not_reorder_unrelated_reservations(
    seeded_database_urls: SqlServerUrls,
) -> None:
    """Cancellation cannot reorder unrelated reservations."""
    org_id = UUID(seeded_database_urls["ORGANIZATION_ID"])
    user_1 = UUID(seeded_database_urls["USER_1_ID"])
    user_2 = UUID(seeded_database_urls["USER_2_ID"])
    user_3 = UUID(seeded_database_urls["USER_3_ID"])

    book_id, _ = _seed_book_and_copies(
        seeded_database_urls["DATABASE_BOOTSTRAP_URL"], org_id, num_copies=0
    )
    db_url = seeded_database_urls["DATABASE_RUNTIME_URL"]
    reservation_store = SqlServerReservationStore(db_url)
    copy_store = SqlServerCopyStatusStore(db_url)
    tx = SqlServerAuditedTransaction()

    service = ReservationService(
        reservation_store=reservation_store,
        copy_store=copy_store,
        authorizer=_AllowAllAuthorizer(),
        transaction=tx,
        connection_provider=lambda o_id: copy_store._tenant_connection(o_id),
    )

    actor_1 = Principal(user_1, org_id, uuid4())
    actor_2 = Principal(user_2, org_id, uuid4())
    actor_3 = Principal(user_3, org_id, uuid4())

    r1 = service.create_reservation(actor=actor_1, book_id=book_id)
    r2 = service.create_reservation(actor=actor_2, book_id=book_id)
    r3 = service.create_reservation(actor=actor_3, book_id=book_id)

    # Cancel middle reservation (r2)
    cancelled_r2 = service.cancel_reservation(
        actor=actor_2, reservation_id=r2.reservation_id
    )
    assert cancelled_r2.status == ReservationStatus.CANCELLED

    # Unrelated reservations r1 and r3 retain their relative order and server positions
    active_items = service.list_reservations(
        actor=actor_1, book_id=book_id, status=ReservationStatus.PENDING
    )
    assert len(active_items) == 2
    assert active_items[0].reservation_id == r1.reservation_id
    assert active_items[0].queue_position == 1
    assert active_items[1].reservation_id == r3.reservation_id
    assert active_items[1].queue_position == 3


def test_expired_hold_advances_exactly_one_eligible_next_reservation(
    seeded_database_urls: SqlServerUrls,
) -> None:
    """Expired hold advances exactly one eligible next reservation."""
    org_id = UUID(seeded_database_urls["ORGANIZATION_ID"])
    user_1 = UUID(seeded_database_urls["USER_1_ID"])
    user_2 = UUID(seeded_database_urls["USER_2_ID"])
    user_3 = UUID(seeded_database_urls["USER_3_ID"])

    book_id, copy_ids = _seed_book_and_copies(
        seeded_database_urls["DATABASE_BOOTSTRAP_URL"], org_id, num_copies=1
    )
    copy_id = copy_ids[0]
    db_url = seeded_database_urls["DATABASE_RUNTIME_URL"]
    reservation_store = SqlServerReservationStore(db_url)
    copy_store = SqlServerCopyStatusStore(db_url)
    tx = SqlServerAuditedTransaction()

    service = ReservationService(
        reservation_store=reservation_store,
        copy_store=copy_store,
        authorizer=_AllowAllAuthorizer(),
        transaction=tx,
        connection_provider=lambda o_id: copy_store._tenant_connection(o_id),
    )

    actor_1 = Principal(user_1, org_id, uuid4())
    actor_2 = Principal(user_2, org_id, uuid4())
    actor_3 = Principal(user_3, org_id, uuid4())

    # Create 3 reservations: r1 will be held immediately because copy is available
    r1 = service.create_reservation(actor=actor_1, book_id=book_id)
    r2 = service.create_reservation(actor=actor_2, book_id=book_id)
    r3 = service.create_reservation(actor=actor_3, book_id=book_id)

    assert r1.status == ReservationStatus.HELD
    assert r1.copy_id == copy_id
    assert r2.status == ReservationStatus.PENDING
    assert r3.status == ReservationStatus.PENDING

    # Simulate hold expiration: set hold_expires_at to 1 hour in the past
    past_time = datetime.now(timezone.utc) - timedelta(hours=1)
    with connect(seeded_database_urls["DATABASE_BOOTSTRAP_URL"]) as connection:
        connection.execute(
            f"UPDATE core.reservations SET hold_expires_at = '{past_time.strftime('%Y-%m-%d %H:%M:%S')}' "
            f"WHERE reservation_id = '{r1.reservation_id}'"
        )

    # Run durable hold expiry sweep
    expired_count = service.expire_holds(actor=Principal(uuid4(), org_id, uuid4()))
    assert expired_count == 1

    # Verify r1 is now expired
    updated_r1 = service.get_reservation(
        actor=actor_1, reservation_id=r1.reservation_id
    )
    assert updated_r1.status == ReservationStatus.EXPIRED

    # Checkpoint: Expired hold advances exactly ONE eligible next reservation (r2)
    updated_r2 = service.get_reservation(
        actor=actor_2, reservation_id=r2.reservation_id
    )
    assert updated_r2.status == ReservationStatus.HELD
    assert updated_r2.copy_id == copy_id
    assert updated_r2.hold_expires_at is not None
    assert updated_r2.hold_expires_at > datetime.now(timezone.utc)

    # Reservation 3 remains pending
    updated_r3 = service.get_reservation(
        actor=actor_3, reservation_id=r3.reservation_id
    )
    assert updated_r3.status == ReservationStatus.PENDING
    assert updated_r3.copy_id is None


def test_consumer_replay_cannot_skip_or_allocate_queue_entry_twice(
    seeded_database_urls: SqlServerUrls,
) -> None:
    """Consumer replay cannot skip or allocate one queue entry twice."""
    org_id = UUID(seeded_database_urls["ORGANIZATION_ID"])
    user_1 = UUID(seeded_database_urls["USER_1_ID"])
    user_2 = UUID(seeded_database_urls["USER_2_ID"])

    # Seed book with 1 copy that starts borrowed
    book_id, copy_ids = _seed_book_and_copies(
        seeded_database_urls["DATABASE_BOOTSTRAP_URL"], org_id, num_copies=1
    )
    copy_id = copy_ids[0]
    with connect(seeded_database_urls["DATABASE_BOOTSTRAP_URL"]) as connection:
        connection.execute(
            f"UPDATE core.book_copies SET status = 'available' WHERE copy_id = '{copy_id}'"
        )

    db_url = seeded_database_urls["DATABASE_RUNTIME_URL"]
    reservation_store = SqlServerReservationStore(db_url)
    copy_store = SqlServerCopyStatusStore(db_url)
    tx = SqlServerAuditedTransaction()

    service = ReservationService(
        reservation_store=reservation_store,
        copy_store=copy_store,
        authorizer=_AllowAllAuthorizer(),
        transaction=tx,
        connection_provider=lambda o_id: copy_store._tenant_connection(o_id),
    )

    actor_1 = Principal(user_1, org_id, uuid4())
    actor_2 = Principal(user_2, org_id, uuid4())

    # Create 2 pending reservations
    r1 = service.create_reservation(actor=actor_1, book_id=book_id)
    r2 = service.create_reservation(actor=actor_2, book_id=book_id)

    # Simulate an outbox event for loan return
    event_id = uuid4()
    claimed_event = ClaimedOutboxEvent(
        event_id=event_id,
        organization_id=org_id,
        event_type="circulation.loan_returned",
        aggregate_type="loan",
        aggregate_id=uuid4(),
        payload_version=1,
        payload_json=json.dumps(
            {
                "loan_id": str(uuid4()),
                "organization_id": str(org_id),
                "copy_id": str(copy_id),
                "borrower_user_id": str(uuid4()),
                "returned_at": datetime.now(timezone.utc).isoformat(),
            }
        ),
        correlation_id=uuid4(),
        idempotency_key=f"loan-returned-{event_id}",
        attempts=1,
        lease_token=uuid4(),
        lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        created_at=datetime.now(timezone.utc),
    )

    with copy_store._tenant_connection(org_id) as conn:
        # First execution of the allocation consumer handler
        allocator = ReservationAllocator(
            reservation_store=reservation_store,
            copy_store=copy_store,
            transaction=tx,
        )
        allocated_1 = handle_loan_returned_allocation(
            claimed_event,
            reservation_allocator=allocator,
            connection=conn,
        )
        conn.commit()

    assert allocated_1 is not None
    assert allocated_1.reservation_id == r1.reservation_id
    assert allocated_1.status == ReservationStatus.HELD

    # Second execution (replay of the same event with same copy_id):
    with copy_store._tenant_connection(org_id) as conn:
        allocated_replay = handle_loan_returned_allocation(
            claimed_event,
            reservation_allocator=allocator,
            connection=conn,
        )
        conn.commit()

    # Replay cannot allocate again or skip to r2 because copy is already held!
    assert allocated_replay is None

    # Check reservation 2 is still pending, not double allocated or skipped
    updated_r2 = service.get_reservation(
        actor=actor_2, reservation_id=r2.reservation_id
    )
    assert updated_r2.status == ReservationStatus.PENDING
    assert updated_r2.copy_id is None
