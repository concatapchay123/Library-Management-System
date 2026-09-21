"""SQL Server persistence adapter for tenant-scoped RBAC."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator
from uuid import UUID, uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.authorization import RbacStore
from openlibrary.modules.core.infrastructure.organizations import (
    clear_tenant_context,
    set_tenant_context,
)
from openlibrary.modules.ops.application.persistence import AuditEvent
from openlibrary.modules.ops.infrastructure.sqlserver import SqlServerAuditedTransaction


class SqlServerRbacStore(RbacStore):
    """Read permission joins live and write assignments with immutable audit evidence."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._engine: Engine | None = None
        self._writer = SqlServerAuditedTransaction()

    def effective_permissions(self, principal: Principal) -> set[str]:
        with self._tenant_connection(principal.organization_id) as connection:
            rows = connection.execute(
                text(
                    "SELECT DISTINCT permission.code FROM core.permissions AS permission "
                    "JOIN core.role_permissions AS role_permission "
                    "ON role_permission.organization_id = permission.organization_id "
                    "AND role_permission.permission_id = permission.permission_id "
                    "JOIN core.user_roles AS user_role "
                    "ON user_role.organization_id = role_permission.organization_id "
                    "AND user_role.role_id = role_permission.role_id "
                    "WHERE user_role.user_id = :user_id"
                ),
                {"user_id": str(principal.user_id)},
            )
            return {str(row.code) for row in rows}

    def assign_role(
        self, *, user_id: UUID, role_id: UUID, organization_id: UUID, actor: Principal
    ) -> None:
        self._mutate_assignment(
            user_id=user_id,
            role_id=role_id,
            organization_id=organization_id,
            actor=actor,
            action="rbac.role_assigned",
            statement=(
                "INSERT INTO core.user_roles (organization_id, user_id, role_id) "
                "SELECT :organization_id, user_record.user_id, role.role_id "
                "FROM core.users AS user_record JOIN core.roles AS role "
                "ON role.organization_id = user_record.organization_id "
                "WHERE user_record.organization_id = :organization_id "
                "AND user_record.user_id = :user_id AND role.role_id = :role_id"
            ),
        )

    def revoke_role(
        self, *, user_id: UUID, role_id: UUID, organization_id: UUID, actor: Principal
    ) -> None:
        self._mutate_assignment(
            user_id=user_id,
            role_id=role_id,
            organization_id=organization_id,
            actor=actor,
            action="rbac.role_revoked",
            statement=(
                "DELETE FROM core.user_roles WHERE organization_id = :organization_id "
                "AND user_id = :user_id AND role_id = :role_id"
            ),
        )

    def _mutate_assignment(
        self,
        *,
        user_id: UUID,
        role_id: UUID,
        organization_id: UUID,
        actor: Principal,
        action: str,
        statement: str,
    ) -> None:
        with self._tenant_connection(organization_id) as connection:

            def mutation(active_connection: Connection) -> None:
                result = active_connection.execute(
                    text(statement),
                    {
                        "organization_id": str(organization_id),
                        "user_id": str(user_id),
                        "role_id": str(role_id),
                    },
                )
                if result.rowcount != 1:
                    raise ValueError("RBAC assignment does not exist in this tenant")

            self._writer.run(
                connection,
                mutation,
                AuditEvent(
                    action=action,
                    entity_type="user_role",
                    entity_id=role_id,
                    actor_user_id=actor.user_id,
                    actor_type="user",
                    payload={"user_id": str(user_id), "role_id": str(role_id)},
                    correlation_id=uuid4(),
                ),
                (),
            )

    @contextmanager
    def _tenant_connection(self, organization_id: UUID) -> Iterator[Connection]:
        if self._engine is None:
            self._engine = create_engine(self._database_url)
        with self._engine.connect() as connection:
            try:
                set_tenant_context(connection, organization_id)
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
            finally:
                clear_tenant_context(connection)
                connection.commit()
