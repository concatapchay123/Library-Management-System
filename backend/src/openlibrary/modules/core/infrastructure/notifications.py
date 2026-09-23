"""SQL Server persistence for in-app notifications under tenant context."""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime
import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from openlibrary.modules.core.application.notifications import (
    Notification,
    NotificationStore,
)
from openlibrary.modules.core.infrastructure.tenancy import SqlServerTenantContext


def _parse_dt(val: object) -> datetime:
    if isinstance(val, datetime):
        return val
    return datetime.fromisoformat(str(val))


def _parse_opt_dt(val: object) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    return datetime.fromisoformat(str(val))


def _notification_from_row(row: RowMapping) -> Notification:
    payload_val = row["payload_json"]
    if isinstance(payload_val, str):
        try:
            payload = json.loads(payload_val)
        except Exception:
            payload = {}
    elif isinstance(payload_val, dict):
        payload = payload_val
    else:
        payload = {}

    return Notification(
        notification_id=UUID(str(row["notification_id"])),
        organization_id=UUID(str(row["organization_id"])),
        user_id=UUID(str(row["user_id"])),
        channel=str(row["channel"]),
        type=str(row["type"]),
        payload=payload,
        status=str(row["status"]),
        read_at=_parse_opt_dt(row["read_at"]),
        created_at=_parse_dt(row["created_at"]),
        outbox_event_id=UUID(str(row["outbox_event_id"]))
        if row["outbox_event_id"] is not None
        else None,
    )


class SqlServerNotificationStore(NotificationStore):
    """Execute parameterized notification queries and mutations under tenant context."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._tenant_context: SqlServerTenantContext | None = None

    def _tenant_connection(
        self, organization_id: UUID
    ) -> AbstractContextManager[Connection]:
        if self._tenant_context is None:
            self._tenant_context = SqlServerTenantContext(self._database_url)
        return self._tenant_context.connection(organization_id)

    def create_notification(
        self,
        notification: Notification,
        *,
        outbox_event_id: UUID | None = None,
    ) -> Notification:
        with self._tenant_connection(notification.organization_id) as connection:
            result = self.create_notification_in_connection(
                connection, notification, outbox_event_id=outbox_event_id
            )
            connection.commit()
            return result

    def create_notification_in_connection(
        self,
        connection: Connection,
        notification: Notification,
        *,
        outbox_event_id: UUID | None = None,
    ) -> Notification:
        ev_id = outbox_event_id or notification.outbox_event_id
        payload_str = json.dumps(
            notification.payload, separators=(",", ":"), sort_keys=True
        )

        if ev_id is not None:
            connection.execute(
                text(
                    "IF NOT EXISTS ("
                    "  SELECT 1 FROM core.notifications "
                    "  WHERE organization_id = :organization_id "
                    "  AND outbox_event_id = :outbox_event_id "
                    "  AND user_id = :user_id"
                    ") "
                    "BEGIN "
                    "  INSERT INTO core.notifications ("
                    "    notification_id, organization_id, user_id, channel, type, "
                    "    payload_json, status, read_at, outbox_event_id, created_at"
                    "  ) VALUES ("
                    "    :notification_id, :organization_id, :user_id, :channel, :type, "
                    "    :payload_json, :status, :read_at, :outbox_event_id, :created_at"
                    "  ); "
                    "END"
                ),
                {
                    "notification_id": str(notification.notification_id),
                    "organization_id": str(notification.organization_id),
                    "user_id": str(notification.user_id),
                    "channel": notification.channel,
                    "type": notification.type,
                    "payload_json": payload_str,
                    "status": notification.status,
                    "read_at": notification.read_at,
                    "outbox_event_id": str(ev_id),
                    "created_at": notification.created_at,
                },
            )
        else:
            connection.execute(
                text(
                    "INSERT INTO core.notifications ("
                    "  notification_id, organization_id, user_id, channel, type, "
                    "  payload_json, status, read_at, outbox_event_id, created_at"
                    ") VALUES ("
                    "  :notification_id, :organization_id, :user_id, :channel, :type, "
                    "  :payload_json, :status, :read_at, NULL, :created_at"
                    ")"
                ),
                {
                    "notification_id": str(notification.notification_id),
                    "organization_id": str(notification.organization_id),
                    "user_id": str(notification.user_id),
                    "channel": notification.channel,
                    "type": notification.type,
                    "payload_json": payload_str,
                    "status": notification.status,
                    "read_at": notification.read_at,
                    "created_at": notification.created_at,
                },
            )

        return notification

    def list_notifications(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        status: str | None = None,
        limit: int = 50,
    ) -> list[Notification]:
        with self._tenant_connection(organization_id) as connection:
            if status is not None:
                query = text(
                    "SELECT TOP (:limit) notification_id, organization_id, user_id, channel, type, "
                    "payload_json, status, read_at, outbox_event_id, created_at "
                    "FROM core.notifications "
                    "WHERE organization_id = :organization_id AND user_id = :user_id AND status = :status "
                    "ORDER BY created_at DESC"
                )
                params: dict[str, object] = {
                    "limit": limit,
                    "organization_id": str(organization_id),
                    "user_id": str(user_id),
                    "status": status,
                }
            else:
                query = text(
                    "SELECT TOP (:limit) notification_id, organization_id, user_id, channel, type, "
                    "payload_json, status, read_at, outbox_event_id, created_at "
                    "FROM core.notifications "
                    "WHERE organization_id = :organization_id AND user_id = :user_id "
                    "ORDER BY created_at DESC"
                )
                params = {
                    "limit": limit,
                    "organization_id": str(organization_id),
                    "user_id": str(user_id),
                }

            rows = connection.execute(query, params).mappings().all()
            return [_notification_from_row(row) for row in rows]

    def get_notification(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        notification_id: UUID,
    ) -> Notification | None:
        with self._tenant_connection(organization_id) as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT notification_id, organization_id, user_id, channel, type, "
                        "payload_json, status, read_at, outbox_event_id, created_at "
                        "FROM core.notifications "
                        "WHERE organization_id = :organization_id "
                        "AND user_id = :user_id "
                        "AND notification_id = :notification_id"
                    ),
                    {
                        "organization_id": str(organization_id),
                        "user_id": str(user_id),
                        "notification_id": str(notification_id),
                    },
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            return _notification_from_row(row)

    def mark_as_read(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        notification_id: UUID,
        read_at: datetime,
    ) -> Notification | None:
        with self._tenant_connection(organization_id) as connection:
            row = (
                connection.execute(
                    text(
                        "UPDATE core.notifications "
                        "SET status = 'read', read_at = COALESCE(read_at, :read_at) "
                        "OUTPUT INSERTED.notification_id, INSERTED.organization_id, "
                        "INSERTED.user_id, INSERTED.channel, INSERTED.type, "
                        "INSERTED.payload_json, INSERTED.status, INSERTED.read_at, "
                        "INSERTED.outbox_event_id, INSERTED.created_at "
                        "WHERE organization_id = :organization_id "
                        "AND user_id = :user_id "
                        "AND notification_id = :notification_id"
                    ),
                    {
                        "organization_id": str(organization_id),
                        "user_id": str(user_id),
                        "notification_id": str(notification_id),
                        "read_at": read_at,
                    },
                )
                .mappings()
                .one_or_none()
            )
            connection.commit()
            if row is None:
                return None
            return _notification_from_row(row)
