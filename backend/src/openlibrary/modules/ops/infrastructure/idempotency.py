"""SQL Server persistence for tenant-scoped idempotency keys."""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from openlibrary.modules.core.infrastructure.tenancy import SqlServerTenantContext
from openlibrary.modules.ops.application.idempotency import (
    IdempotencyRecord,
    IdempotencyStore,
)


class SqlServerIdempotencyStore(IdempotencyStore):
    """Execute parameterized idempotency key queries and mutations under tenant context."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._tenant_context: SqlServerTenantContext | None = None

    def get_record(
        self, organization_id: UUID, key: str, method: str, endpoint: str
    ) -> IdempotencyRecord | None:
        with self._tenant_connection(organization_id) as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT key_id, organization_id, idempotency_key, method, "
                        "endpoint, request_hash, resource_reference, status_code, "
                        "safe_response_json, created_at, expires_at "
                        "FROM ops.idempotency_keys "
                        "WHERE idempotency_key = :key AND method = :method AND endpoint = :endpoint"
                    ),
                    {"key": key, "method": method, "endpoint": endpoint},
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            return _record_from_row(row)

    def save_record(
        self,
        *,
        key_id: UUID,
        organization_id: UUID,
        key: str,
        method: str,
        endpoint: str,
        request_hash: str,
        resource_reference: str | None,
        status_code: int,
        safe_response_json: str,
        created_at: datetime,
        expires_at: datetime,
    ) -> IdempotencyRecord:
        with self._tenant_connection(organization_id) as connection:
            # Delete any existing/expired record for this key to prevent unique collisions
            connection.execute(
                text(
                    "DELETE FROM ops.idempotency_keys "
                    "WHERE idempotency_key = :key AND method = :method AND endpoint = :endpoint"
                ),
                {"key": key, "method": method, "endpoint": endpoint},
            )
            connection.execute(
                text(
                    "INSERT INTO ops.idempotency_keys "
                    "(key_id, organization_id, idempotency_key, method, endpoint, "
                    "request_hash, resource_reference, status_code, safe_response_json, "
                    "created_at, expires_at) "
                    "VALUES (:key_id, :organization_id, :key, :method, :endpoint, "
                    ":request_hash, :resource_reference, :status_code, :safe_response_json, "
                    ":created_at, :expires_at)"
                ),
                {
                    "key_id": str(key_id),
                    "organization_id": str(organization_id),
                    "key": key,
                    "method": method,
                    "endpoint": endpoint,
                    "request_hash": request_hash,
                    "resource_reference": resource_reference,
                    "status_code": status_code,
                    "safe_response_json": safe_response_json,
                    "created_at": created_at,
                    "expires_at": expires_at,
                },
            )
            connection.commit()
            return IdempotencyRecord(
                key_id=key_id,
                organization_id=organization_id,
                key=key,
                method=method,
                endpoint=endpoint,
                request_hash=request_hash,
                resource_reference=resource_reference,
                status_code=status_code,
                safe_response_json=safe_response_json,
                created_at=created_at,
                expires_at=expires_at,
            )

    def delete_record(self, organization_id: UUID, key_id: UUID) -> None:
        with self._tenant_connection(organization_id) as connection:
            connection.execute(
                text("DELETE FROM ops.idempotency_keys WHERE key_id = :key_id"),
                {"key_id": str(key_id)},
            )
            connection.commit()

    def _tenant_connection(
        self, organization_id: UUID
    ) -> AbstractContextManager[Connection]:
        if self._tenant_context is None:
            self._tenant_context = SqlServerTenantContext(self._database_url)
        return self._tenant_context.connection(organization_id)


def _record_from_row(row: RowMapping) -> IdempotencyRecord:
    return IdempotencyRecord(
        key_id=UUID(str(row["key_id"])),
        organization_id=UUID(str(row["organization_id"])),
        key=str(row["idempotency_key"]),
        method=str(row["method"]),
        endpoint=str(row["endpoint"]),
        request_hash=str(row["request_hash"]),
        resource_reference=str(row["resource_reference"])
        if row["resource_reference"] is not None
        else None,
        status_code=int(row["status_code"]),
        safe_response_json=str(row["safe_response_json"]),
        created_at=_parse_dt(row["created_at"]),
        expires_at=_parse_dt(row["expires_at"]),
    )


def _parse_dt(val: object) -> datetime:
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val
    dt = datetime.fromisoformat(str(val))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
