"""Application authorization contracts for tenant-scoped RBAC."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest
from flask import Response

from openlibrary.app.config import AppConfig
from openlibrary.app.factory import create_app

from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.authorization import (
    AuthorizationDenied,
    AuthorizationService,
    RbacService,
)


ORGANIZATION_ID = uuid4()
OTHER_ORGANIZATION_ID = uuid4()
ACTOR = Principal(uuid4(), ORGANIZATION_ID, uuid4())
USER_ID = uuid4()
ROLE_ID = uuid4()
PERMISSION = "role.manage"


@dataclass
class InMemoryRbacStore:
    """A stateful port double that makes revocation semantics observable."""

    permissions: dict[UUID, set[str]] = field(default_factory=dict)
    assignments: dict[tuple[UUID, UUID], UUID] = field(default_factory=dict)
    audit_actions: list[str] = field(default_factory=list)

    def effective_permissions(self, principal: Principal) -> set[str]:
        return self.permissions.get(principal.user_id, set())

    def assign_role(
        self, *, user_id: UUID, role_id: UUID, organization_id: UUID, actor: Principal
    ) -> None:
        assert organization_id == actor.organization_id
        self.assignments[(user_id, role_id)] = organization_id
        self.permissions.setdefault(user_id, set()).add(PERMISSION)
        self.audit_actions.append("rbac.role_assigned")

    def revoke_role(
        self, *, user_id: UUID, role_id: UUID, organization_id: UUID, actor: Principal
    ) -> None:
        assert organization_id == actor.organization_id
        self.assignments.pop((user_id, role_id))
        self.permissions.setdefault(user_id, set()).discard(PERMISSION)
        self.audit_actions.append("rbac.role_revoked")


@pytest.fixture
def store() -> InMemoryRbacStore:
    return InMemoryRbacStore(permissions={ACTOR.user_id: {PERMISSION}})


def test_revocation_changes_effective_permission_without_deployment(
    store: InMemoryRbacStore,
) -> None:
    """Each decision reads durable role data; no role name is embedded in code."""
    principal = Principal(USER_ID, ORGANIZATION_ID, uuid4())
    authorizer = AuthorizationService(store)
    rbac = RbacService(store, authorizer)

    rbac.assign_role(user_id=USER_ID, role_id=ROLE_ID, actor=ACTOR)
    assert authorizer.allows(principal, PERMISSION)

    rbac.revoke_role(user_id=USER_ID, role_id=ROLE_ID, actor=ACTOR)

    assert not authorizer.allows(principal, PERMISSION)
    with pytest.raises(AuthorizationDenied):
        authorizer.require(principal, PERMISSION)
    assert store.audit_actions == ["rbac.role_assigned", "rbac.role_revoked"]


def test_authorization_denial_is_a_stable_non_leaking_problem_response() -> None:
    """The HTTP boundary must not expose SQL, roles, or tenant facts on denial."""
    app = create_app(AppConfig(readiness_probe=lambda: True))

    @app.get("/api/v1/protected")
    def protected() -> Response:
        raise AuthorizationDenied("role.manage missing for user in tenant")

    response = app.test_client().get("/api/v1/protected")

    assert response.status_code == 403
    assert response.mimetype == "application/problem+json"
    assert response.get_json()["detail"] == "Authorization denied."
    assert "role.manage" not in response.get_data(as_text=True)
