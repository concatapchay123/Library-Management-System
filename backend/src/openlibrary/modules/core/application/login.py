"""Tenant-resolved credential validation without credential disclosure."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy.engine import Connection

from openlibrary.modules.core.domain.passwords import PasswordService
from openlibrary.modules.core.infrastructure.organizations import LoginTenant
from openlibrary.modules.ops.application.persistence import (
    AuditEvent,
    AuditedTransaction,
)


@dataclass(frozen=True, slots=True)
class LoginResult:
    """Authenticated principal data, deliberately excluding credentials and tokens."""

    user_id: UUID
    organization_id: UUID


@dataclass(frozen=True, slots=True)
class UserCredentials:
    """Tenant-scoped data required only during password verification."""

    user_id: UUID
    password_hash: str
    status: str


class UserCredentialsRepository(Protocol):
    """Persistence operations permitted after a tenant was resolved."""

    def find_by_email(
        self, connection: Connection, *, organization_id: UUID, email: str
    ) -> UserCredentials | None:
        """Find one tenant-local credential record."""

    def update_last_login(self, connection: Connection, *, user_id: UUID) -> None:
        """Record a successful login without writing credential data."""


class PreloginSecurityAudit(Protocol):
    """Narrow system-scope audit path for an unresolved public login."""

    def record_unknown_tenant_failure(
        self, connection: Connection, *, correlation_id: UUID
    ) -> None:
        """Persist a canonical event without accepting user-supplied identity data."""


ConnectionFactory = Callable[[], AbstractContextManager[Connection]]
TenantResolver = Callable[[Connection, str], LoginTenant | None]
TenantContextSetter = Callable[[Connection, UUID], None]
TenantContextClearer = Callable[[Connection], None]


class LoginService:
    """Perform uniform, tenant-safe credential validation for public login."""

    def __init__(
        self,
        *,
        connection_factory: ConnectionFactory,
        tenant_resolver: TenantResolver,
        set_tenant_context: TenantContextSetter,
        clear_tenant_context: TenantContextClearer,
        user_credentials: UserCredentialsRepository,
        password_service: PasswordService,
        dummy_password_hash: str,
        audited_transaction: AuditedTransaction,
        prelogin_security_audit: PreloginSecurityAudit,
    ) -> None:
        self._connection_factory = connection_factory
        self._tenant_resolver = tenant_resolver
        self._set_tenant_context = set_tenant_context
        self._clear_tenant_context = clear_tenant_context
        self._user_credentials = user_credentials
        self._password_service = password_service
        self._dummy_password_hash = dummy_password_hash
        self._audited_transaction = audited_transaction
        self._prelogin_security_audit = prelogin_security_audit

    def login(
        self,
        *,
        organization_slug: str,
        email: str,
        password: str,
        correlation_id: str,
    ) -> LoginResult | None:
        """Authenticate only after resolver-derived tenant context is established."""
        audit_correlation_id = uuid5(
            NAMESPACE_URL, f"openlibraryos:login:{correlation_id}"
        )
        with self._connection_factory() as connection:
            tenant = self._tenant_resolver(connection, organization_slug)
            if tenant is None:
                self._password_service.verify(password, self._dummy_password_hash)
                self._prelogin_security_audit.record_unknown_tenant_failure(
                    connection, correlation_id=audit_correlation_id
                )
                connection.commit()
                return None

            try:
                self._set_tenant_context(connection, tenant.organization_id)
                connection.commit()
                if tenant.status != "active":
                    self._password_service.verify(password, self._dummy_password_hash)
                    self._record_failure(
                        connection, tenant.organization_id, audit_correlation_id
                    )
                    return None

                user = self._user_credentials.find_by_email(
                    connection, organization_id=tenant.organization_id, email=email
                )
                verified = (
                    user is not None
                    and user.status == "active"
                    and self._password_service.verify(password, user.password_hash)
                )
                if not verified:
                    if user is None or user.status != "active":
                        self._password_service.verify(
                            password, self._dummy_password_hash
                        )
                    self._record_failure(
                        connection,
                        tenant.organization_id,
                        audit_correlation_id,
                        user_id=None if user is None else user.user_id,
                    )
                    return None

                assert user is not None
                self._record_success(connection, user.user_id, audit_correlation_id)
                return LoginResult(
                    user_id=user.user_id, organization_id=tenant.organization_id
                )
            finally:
                self._clear_tenant_context(connection)
                connection.commit()

    def _record_failure(
        self,
        connection: Connection,
        organization_id: UUID,
        correlation_id: UUID,
        *,
        user_id: UUID | None = None,
    ) -> None:
        self._audited_transaction.run(
            connection,
            lambda _: None,
            AuditEvent(
                action="authentication.login_failed",
                entity_type="user" if user_id is not None else "organization",
                entity_id=user_id or organization_id,
                actor_user_id=None,
                actor_type="anonymous",
                payload={"result": "failed"},
                correlation_id=correlation_id,
            ),
            (),
        )

    def _record_success(
        self, connection: Connection, user_id: UUID, correlation_id: UUID
    ) -> None:
        self._audited_transaction.run(
            connection,
            lambda active_connection: self._user_credentials.update_last_login(
                active_connection, user_id=user_id
            ),
            AuditEvent(
                action="authentication.login_succeeded",
                entity_type="user",
                entity_id=user_id,
                actor_user_id=user_id,
                actor_type="user",
                payload={"result": "succeeded"},
                correlation_id=correlation_id,
            ),
            (),
        )
