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


def test_rate_limiter_extracts_sanitized_client_ip_from_request() -> None:
    """Verifies that rate_limit extracts X-Real-IP or rightmost forwarded IP, preventing spoofing."""
    from openlibrary.modules.core.infrastructure.rate_limiter import get_client_ip

    # Case 1: X-Real-IP set by trusted edge reverse proxy
    req1 = MagicMock()
    req1.headers = {
        "X-Real-IP": "203.0.113.195",
        "X-Forwarded-For": "1.2.3.4, 203.0.113.195",
    }
    req1.remote_addr = "10.0.0.2"
    assert get_client_ip(req1) == "203.0.113.195"

    # Case 2: Multi-hop X-Forwarded-For without X-Real-IP takes the trusted rightmost client hop
    req2 = MagicMock()
    req2.headers = {"X-Forwarded-For": "198.51.100.1, 203.0.113.50"}
    req2.remote_addr = "10.0.0.2"
    assert get_client_ip(req2) == "203.0.113.50"

    # Case 3: No headers falls back to remote_addr
    req3 = MagicMock()
    req3.headers = {}
    req3.remote_addr = "192.168.1.100"
    assert get_client_ip(req3) == "192.168.1.100"
