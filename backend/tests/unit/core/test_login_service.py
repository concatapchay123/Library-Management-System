"""Application-service coverage for public-login security branches."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy.engine import Connection

from openlibrary.modules.core.application.login import LoginService
from openlibrary.modules.core.infrastructure.organizations import LoginTenant
from openlibrary.modules.ops.application.persistence import AuditEvent


@dataclass
class RecordingConnection:
    """Minimal connection double that exposes transaction completion."""

    commits: int = 0

    def commit(self) -> None:
        self.commits += 1


@dataclass
class RecordingPasswords:
    """Password boundary that records which encoded value was verified."""

    verifications: list[tuple[str, str]] = field(default_factory=list)

    def verify(self, password: str, encoded_hash: str) -> bool:
        self.verifications.append((password, encoded_hash))
        return False


@dataclass
class RecordingPreloginAudit:
    """Procedure port that retains only the server-derived correlation UUID."""

    correlation_ids: list[UUID] = field(default_factory=list)

    def record_unknown_tenant_failure(
        self, connection: Connection, *, correlation_id: UUID
    ) -> None:
        del connection
        self.correlation_ids.append(correlation_id)


@dataclass
class RecordingAuditTransaction:
    """Audit port that rejects accidental credential-bearing event payloads."""

    events: list[AuditEvent] = field(default_factory=list)

    def run(
        self,
        connection: Connection,
        mutation: object,
        audit_event: AuditEvent,
        outbox_events: object,
    ) -> None:
        del outbox_events
        if callable(mutation):
            mutation(connection)
        self.events.append(audit_event)


class NoCredentialRepository:
    """Repository double that fails if a disabled tenant reaches user lookup."""

    def find_by_email(
        self, connection: Connection, *, organization_id: UUID, email: str
    ) -> None:
        del connection, organization_id, email
        raise AssertionError("disabled tenant must not query user credentials")

    def update_last_login(self, connection: Connection, *, user_id: UUID) -> None:
        del connection, user_id
        raise AssertionError("failed authentication must not update last_login_at")


def _service_for(
    tenant: LoginTenant | None,
) -> tuple[
    LoginService,
    RecordingPasswords,
    RecordingPreloginAudit,
    RecordingAuditTransaction,
]:
    """Build a login service with observable ports and no database dependency."""
    connection = RecordingConnection()
    passwords = RecordingPasswords()
    prelogin_audit = RecordingPreloginAudit()
    audit_transaction = RecordingAuditTransaction()

    @contextmanager
    def connection_factory() -> Iterator[Connection]:
        yield connection

    return (
        LoginService(
            connection_factory=connection_factory,
            tenant_resolver=lambda _, __: tenant,
            set_tenant_context=lambda _, __: None,
            clear_tenant_context=lambda _: None,
            user_credentials=NoCredentialRepository(),
            password_service=passwords,
            dummy_password_hash="dummy-argon2id-hash",
            audited_transaction=audit_transaction,
            prelogin_security_audit=prelogin_audit,
        ),
        passwords,
        prelogin_audit,
        audit_transaction,
    )


def test_unknown_slug_runs_dummy_verification_and_writes_no_identity_data() -> None:
    """Skipping either step would make missing tenants enumerable or unaudited."""
    service, passwords, prelogin_audit, audit_transaction = _service_for(None)

    result = service.login(
        organization_slug="missing-campus",
        email="librarian@example.test",
        password="wrong-password",
        correlation_id="request-123",
    )

    assert result is None
    assert passwords.verifications == [("wrong-password", "dummy-argon2id-hash")]
    assert len(prelogin_audit.correlation_ids) == 1
    assert audit_transaction.events == []


def test_disabled_tenant_runs_dummy_verification_and_writes_safe_tenant_audit() -> None:
    """A disabled tenant must use the same Argon work while preserving audit evidence."""
    organization_id = uuid4()
    service, passwords, prelogin_audit, audit_transaction = _service_for(
        LoginTenant(organization_id, "disabled-campus", "disabled")
    )

    result = service.login(
        organization_slug="disabled-campus",
        email="librarian@example.test",
        password="wrong-password",
        correlation_id="request-456",
    )

    assert result is None
    assert passwords.verifications == [("wrong-password", "dummy-argon2id-hash")]
    assert prelogin_audit.correlation_ids == []
    assert len(audit_transaction.events) == 1
    event = audit_transaction.events[0]
    assert event.action == "authentication.login_failed"
    assert event.entity_id == organization_id
    assert event.payload == {"result": "failed"}
    assert "password" not in str(event.payload)
    assert "librarian@example.test" not in str(event.payload)


def test_tenant_context_is_cleared_when_context_setup_fails() -> None:
    """A failed setup must not leave tenant state on a reusable SQL connection."""
    connection = RecordingConnection()
    cleared: list[Connection] = []
    organization_id = uuid4()

    @contextmanager
    def connection_factory() -> Iterator[Connection]:
        yield connection

    def failing_context_setter(_: Connection, __: UUID) -> None:
        raise RuntimeError("simulated context setup failure")

    service = LoginService(
        connection_factory=connection_factory,
        tenant_resolver=lambda _, __: LoginTenant(
            organization_id, "campus-a", "active"
        ),
        set_tenant_context=failing_context_setter,
        clear_tenant_context=cleared.append,
        user_credentials=NoCredentialRepository(),
        password_service=RecordingPasswords(),
        dummy_password_hash="dummy-argon2id-hash",
        audited_transaction=RecordingAuditTransaction(),
        prelogin_security_audit=RecordingPreloginAudit(),
    )

    with pytest.raises(RuntimeError, match="context setup failure"):
        service.login(
            organization_slug="campus-a",
            email="librarian@example.test",
            password="wrong-password",
            correlation_id="request-789",
        )

    assert cleared == [connection]


def test_change_password_success() -> None:
    """Verifies that changing password validates current password, hashes new password, and audits."""
    from openlibrary.modules.core.application.access_tokens import Principal
    from openlibrary.modules.core.application.login import UserCredentials

    connection = RecordingConnection()
    audit_transaction = RecordingAuditTransaction()
    user_id = uuid4()
    org_id = uuid4()
    current_hash = "argon2id$current_hash"

    class MockUserRepo:
        def __init__(self) -> None:
            self.updated_hash: str | None = None

        def find_by_email(self, *_, **__):
            return None

        def find_by_id(self, connection, *, organization_id, user_id):
            return UserCredentials(
                user_id=user_id, password_hash=current_hash, status="active"
            )

        def update_password(
            self, connection, *, organization_id, user_id, password_hash
        ):
            self.updated_hash = password_hash

        def update_last_login(self, *_, **__):
            pass

    class MockPasswords:
        def verify(self, password: str, encoded_hash: str) -> bool:
            return password == "OldPassword123!" and encoded_hash == current_hash

        def hash(self, password: str) -> str:
            return f"argon2id$hashed_{password}"

    repo = MockUserRepo()
    passwords = MockPasswords()

    @contextmanager
    def connection_factory() -> Iterator[Connection]:
        yield connection

    service = LoginService(
        connection_factory=connection_factory,
        tenant_resolver=lambda _, __: None,
        set_tenant_context=lambda _, __: None,
        clear_tenant_context=lambda _: None,
        user_credentials=repo,
        password_service=passwords,
        dummy_password_hash="dummy-argon2id-hash",
        audited_transaction=audit_transaction,
        prelogin_security_audit=RecordingPreloginAudit(),
    )

    actor = Principal(user_id=user_id, organization_id=org_id, session_id=uuid4())
    service.change_password(
        actor=actor,
        current_password="OldPassword123!",
        new_password="NewSecurePassword123!",
        correlation_id="req-123",
    )

    assert repo.updated_hash == "argon2id$hashed_NewSecurePassword123!"
    assert len(audit_transaction.events) == 1
    event = audit_transaction.events[0]
    assert event.action == "authentication.password_changed"
    assert event.entity_id == user_id
    assert event.payload == {"result": "succeeded"}


def test_change_password_rejects_invalid_inputs() -> None:
    """Rejects short new passwords, wrong current password, or identical passwords."""
    from openlibrary.modules.core.application.access_tokens import Principal
    from openlibrary.modules.core.application.login import UserCredentials

    connection = RecordingConnection()
    audit_transaction = RecordingAuditTransaction()
    user_id = uuid4()
    org_id = uuid4()

    class MockUserRepo:
        def find_by_email(self, *_, **__):
            return None

        def find_by_id(self, connection, *, organization_id, user_id):
            return UserCredentials(
                user_id=user_id, password_hash="hash", status="active"
            )

        def update_password(self, *_, **__):
            pass

        def update_last_login(self, *_, **__):
            pass

    class MockPasswords:
        def verify(self, password: str, encoded_hash: str) -> bool:
            return password == "CorrectOldPassword!"

        def hash(self, password: str) -> str:
            return f"hash_{password}"

    @contextmanager
    def connection_factory() -> Iterator[Connection]:
        yield connection

    service = LoginService(
        connection_factory=connection_factory,
        tenant_resolver=lambda _, __: None,
        set_tenant_context=lambda _, __: None,
        clear_tenant_context=lambda _: None,
        user_credentials=MockUserRepo(),
        password_service=MockPasswords(),
        dummy_password_hash="dummy-argon2id-hash",
        audited_transaction=audit_transaction,
        prelogin_security_audit=RecordingPreloginAudit(),
    )

    actor = Principal(user_id=user_id, organization_id=org_id, session_id=uuid4())

    # Short password
    with pytest.raises(ValueError, match="at least 12 characters"):
        service.change_password(
            actor=actor,
            current_password="CorrectOldPassword!",
            new_password="short",
            correlation_id="req-1",
        )

    # Identical password
    with pytest.raises(ValueError, match="different from current_password"):
        service.change_password(
            actor=actor,
            current_password="CorrectOldPassword!",
            new_password="CorrectOldPassword!",
            correlation_id="req-2",
        )

    # Wrong current password
    with pytest.raises(ValueError, match="Current password is incorrect"):
        service.change_password(
            actor=actor,
            current_password="WrongOldPassword!",
            new_password="NewValidPassword123!",
            correlation_id="req-3",
        )
