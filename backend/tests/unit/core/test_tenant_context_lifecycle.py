"""Failure handling for a pooled tenant-context connection."""

from __future__ import annotations

from uuid import uuid4

import pytest

from openlibrary.modules.core.infrastructure.tenancy import SqlServerTenantContext


class _Connection:
    def __init__(self) -> None:
        self.invalidated = False
        self.commits = 0

    def __enter__(self) -> "_Connection":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, statement: object, _: object = None) -> None:
        if "@value=NULL" in str(statement):
            raise RuntimeError("cleanup failed")

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        return None

    def invalidate(self) -> None:
        self.invalidated = True


class _Engine:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    def connect(self) -> _Connection:
        return self.connection

    def dispose(self) -> None:
        return None


def test_cleanup_failure_invalidates_the_physical_connection() -> None:
    connection = _Connection()
    context = SqlServerTenantContext("unused", engine=_Engine(connection))  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="cleanup failed"):
        with context.connection(uuid4()):
            pass

    assert connection.invalidated
