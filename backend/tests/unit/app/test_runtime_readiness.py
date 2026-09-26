"""Tests for runtime dependency readiness probe (H-01)."""

from unittest.mock import MagicMock, patch
from openlibrary.app.runtime import create_runtime_readiness_probe


def test_readiness_probe_returns_true_when_all_dependencies_succeed() -> None:
    probe = create_runtime_readiness_probe(
        database_url="mssql+pyodbc://mock",
        redis_url="redis://mock:6379/0",
    )

    with (
        patch("sqlalchemy.create_engine") as mock_engine,
        patch("redis.Redis.from_url") as mock_redis_cls,
    ):
        # Mock engine connect
        conn = MagicMock()
        mock_engine.return_value.connect.return_value.__enter__.return_value = conn

        # Mock redis ping
        redis_client = MagicMock()
        redis_client.ping.return_value = True
        mock_redis_cls.return_value = redis_client

        assert probe() is True


def test_readiness_probe_returns_false_when_database_fails() -> None:
    probe = create_runtime_readiness_probe(
        database_url="mssql+pyodbc://mock",
        redis_url="redis://mock:6379/0",
    )

    with (
        patch(
            "sqlalchemy.create_engine",
            side_effect=Exception("Database connection timeout"),
        ),
        patch("redis.Redis.from_url") as mock_redis_cls,
    ):
        redis_client = MagicMock()
        redis_client.ping.return_value = True
        mock_redis_cls.return_value = redis_client

        assert probe() is False


def test_readiness_probe_returns_false_when_redis_fails() -> None:
    probe = create_runtime_readiness_probe(
        database_url="mssql+pyodbc://mock",
        redis_url="redis://mock:6379/0",
    )

    with (
        patch("sqlalchemy.create_engine") as mock_engine,
        patch(
            "redis.Redis.from_url", side_effect=Exception("Redis connection refused")
        ),
    ):
        conn = MagicMock()
        mock_engine.return_value.connect.return_value.__enter__.return_value = conn

        assert probe() is False
