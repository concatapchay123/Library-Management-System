"""SQL Server implementation of the audited transaction port."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TypeVar

from sqlalchemy import text
from sqlalchemy.engine import Connection

from openlibrary.modules.ops.application.persistence import (
    AuditEvent,
    OutboxEvent,
    serialize_event_payload,
)


T = TypeVar("T")


class SqlServerAuditedTransaction:
    """Commit a business mutation with its audit and durable outbox effects."""

    def run(
        self,
        connection: Connection,
        mutation: Callable[[Connection], T],
        audit_event: AuditEvent,
        outbox_events: Sequence[OutboxEvent],
    ) -> T:
        """Write atomically in a new transaction or the caller's savepoint."""
        transaction = (
            connection.begin_nested() if connection.in_transaction() else connection.begin()
        )
        with transaction:
            result = mutation(connection)
            self._insert_audit(connection, audit_event)
            for outbox_event in outbox_events:
                self._insert_outbox(connection, outbox_event)
        return result

    def _insert_audit(self, connection: Connection, event: AuditEvent) -> None:
        connection.execute(
            text(
                "INSERT INTO ops.audit_events "
                "(audit_id, organization_id, actor_user_id, actor_type, action, "
                "entity_type, entity_id, payload_version, payload_json, correlation_id) "
                "VALUES (:audit_id, CONVERT(uniqueidentifier, "
                "SESSION_CONTEXT(N'organization_id')), :actor_user_id, :actor_type, "
                ":action, :entity_type, :entity_id, :payload_version, :payload_json, "
                ":correlation_id)"
            ),
            {
                "audit_id": str(event.audit_id),
                "actor_user_id": _uuid_parameter(event.actor_user_id),
                "actor_type": event.actor_type,
                "action": event.action,
                "entity_type": event.entity_type,
                "entity_id": str(event.entity_id),
                "payload_version": event.payload_version,
                "payload_json": serialize_event_payload(event.payload),
                "correlation_id": str(event.correlation_id),
            },
        )

    def _insert_outbox(self, connection: Connection, event: OutboxEvent) -> None:
        connection.execute(
            text(
                "INSERT INTO ops.outbox_events "
                "(event_id, organization_id, event_type, aggregate_type, aggregate_id, "
                "payload_version, payload_json, correlation_id, idempotency_key) "
                "VALUES (:event_id, CONVERT(uniqueidentifier, "
                "SESSION_CONTEXT(N'organization_id')), :event_type, :aggregate_type, "
                ":aggregate_id, :payload_version, :payload_json, :correlation_id, "
                ":idempotency_key)"
            ),
            {
                "event_id": str(event.event_id),
                "event_type": event.event_type,
                "aggregate_type": event.aggregate_type,
                "aggregate_id": str(event.aggregate_id),
                "payload_version": event.payload_version,
                "payload_json": serialize_event_payload(event.payload),
                "correlation_id": str(event.correlation_id),
                "idempotency_key": event.idempotency_key,
            },
        )


def _uuid_parameter(value: object) -> str | None:
    """Render optional UUIDs for pyodbc without changing their SQL type."""
    return None if value is None else str(value)
