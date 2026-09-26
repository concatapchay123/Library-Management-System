"""Unit tests for distributed Redis rate limiter and fail-closed security policy (H-04)."""

from unittest.mock import MagicMock
import pytest
from openlibrary.modules.core.infrastructure.rate_limiter import (
    RedisRateLimiter,
    RateLimiterUnavailableError,
)


def test_rate_limiter_allows_requests_within_limit() -> None:
    mock_redis = MagicMock()
    # pipeline returns [current_count=1, ttl=60]
    pipeline = MagicMock()
    mock_redis.pipeline.return_value.__enter__.return_value = pipeline
    pipeline.execute.return_value = [1, True]
    mock_redis.ttl.return_value = 60

    limiter = RedisRateLimiter(redis_client=mock_redis)
    allowed, remaining, retry_after = limiter.check_rate_limit(
        key="login:127.0.0.1",
        limit=5,
        window_seconds=60,
        fail_closed=True,
    )

    assert allowed is True
    assert remaining == 4
    assert retry_after == 0


def test_rate_limiter_blocks_requests_exceeding_limit() -> None:
    mock_redis = MagicMock()
    pipeline = MagicMock()
    mock_redis.pipeline.return_value.__enter__.return_value = pipeline
    pipeline.execute.return_value = [6, True]
    mock_redis.ttl.return_value = 45

    limiter = RedisRateLimiter(redis_client=mock_redis)
    allowed, remaining, retry_after = limiter.check_rate_limit(
        key="login:127.0.0.1",
        limit=5,
        window_seconds=60,
        fail_closed=True,
    )

    assert allowed is False
    assert remaining == 0
    assert retry_after == 45


def test_rate_limiter_fail_closed_on_redis_error() -> None:
    mock_redis = MagicMock()
    mock_redis.pipeline.side_effect = Exception("Redis connection refused")

    limiter = RedisRateLimiter(redis_client=mock_redis)

    with pytest.raises(RateLimiterUnavailableError):
        limiter.check_rate_limit(
            key="login:127.0.0.1",
            limit=5,
            window_seconds=60,
            fail_closed=True,
        )


def test_rate_limiter_fail_open_when_configured() -> None:
    mock_redis = MagicMock()
    mock_redis.pipeline.side_effect = Exception("Redis connection refused")

    limiter = RedisRateLimiter(redis_client=mock_redis)
    allowed, remaining, retry_after = limiter.check_rate_limit(
        key="public:127.0.0.1",
        limit=10,
        window_seconds=60,
        fail_closed=False,
    )

    assert allowed is True
    assert remaining == 1
    assert retry_after == 0
