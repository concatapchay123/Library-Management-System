"""Named-permission authorization at the application-service boundary."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from openlibrary.modules.core.application.access_tokens import Principal


class AuthorizationDenied(PermissionError):
    """Raised without resource detail when the caller lacks a named permission."""


class AuthorizationPort(Protocol):
    """The only authorization dependency application services need."""

    def require(self, principal: Principal, permission: str) -> None:
        """Fail closed unless this principal currently holds the permission."""


class RbacStore(Protocol):
    """Tenant-enforced persistence needed for live permission decisions."""

    def effective_permissions(self, principal: Principal) -> set[str]:
        """Return permissions obtained from the principal's current tenant roles."""

    def assign_role(
        self, *, user_id: UUID, role_id: UUID, organization_id: UUID, actor: Principal
    ) -> None:
        """Persist one tenant-local assignment and its audit evidence atomically."""

    def revoke_role(
        self, *, user_id: UUID, role_id: UUID, organization_id: UUID, actor: Principal
    ) -> None:
        """Remove one tenant-local assignment and audit the mutation atomically."""


class AuthorizationService:
    """Resolve permissions for every decision so revocations take effect immediately."""

    def __init__(self, store: RbacStore) -> None:
        self._store = store

    def allows(self, principal: Principal, permission: str) -> bool:
        """Check one named permission without turning role labels into code policy."""
        return bool(permission) and permission in self._store.effective_permissions(
            principal
        )

    def permissions(self, principal: Principal) -> tuple[str, ...]:
        """Return a stable representation of the principal's current permissions."""
        return tuple(sorted(self._store.effective_permissions(principal)))

    def require(self, principal: Principal, permission: str) -> None:
        """Enforce a named permission at the owning application-service boundary."""
        if not self.allows(principal, permission):
            raise AuthorizationDenied("Authorization denied")


class RbacService:
    """Assign and revoke roles only through current permission data."""

    _MANAGE_PERMISSION = "role.manage"

    def __init__(self, store: RbacStore, authorizer: AuthorizationPort) -> None:
        self._store = store
        self._authorizer = authorizer

    def assign_role(self, *, user_id: UUID, role_id: UUID, actor: Principal) -> None:
        self._authorizer.require(actor, self._MANAGE_PERMISSION)
        self._store.assign_role(
            user_id=user_id,
            role_id=role_id,
            organization_id=actor.organization_id,
            actor=actor,
        )

    def revoke_role(self, *, user_id: UUID, role_id: UUID, actor: Principal) -> None:
        self._authorizer.require(actor, self._MANAGE_PERMISSION)
        self._store.revoke_role(
            user_id=user_id,
            role_id=role_id,
            organization_id=actor.organization_id,
            actor=actor,
        )
