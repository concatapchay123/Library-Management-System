"""Distributed Redis rate limiter with fail-closed policy for sensitive endpoints (H-04)."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
import logging
from typing import Any, TypeVar

from flask import Response, current_app, jsonify, request

_LOGGER = logging.getLogger(__name__)
F = TypeVar("F", bound=Callable[..., Any])


class RateLimiterUnavailableError(RuntimeError):
    """Raised when the rate limiter backend is unavailable and fail_closed=True."""


class RedisRateLimiter:
    """Distributed rate limiter backed by Redis with atomic window tracking."""

    def __init__(
        self,
        redis_url: str | None = None,
        redis_client: Any | None = None,
    ) -> None:
        self._redis_url = redis_url
        self._client = redis_client

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._redis_url:
            raise RateLimiterUnavailableError(
                "No Redis URL configured for rate limiter"
            )
        import redis

        self._client = redis.Redis.from_url(
            self._redis_url,
            socket_timeout=1.0,
            socket_connect_timeout=1.0,
        )
        return self._client

    def check_rate_limit(
        self,
        *,
        key: str,
        limit: int,
        window_seconds: int,
        fail_closed: bool = True,
    ) -> tuple[bool, int, int]:
        """Check whether key has exceeded limit within the sliding/fixed window.

        Returns:
            (allowed: bool, remaining: int, retry_after_seconds: int)
        """
        redis_key = f"openlibrary:ratelimit:{key}"
        try:
            client = self._get_client()
            with client.pipeline() as pipe:
                pipe.incr(redis_key)
                pipe.expire(redis_key, window_seconds, nx=True)
                results = pipe.execute()

            current_count = int(results[0])
            ttl = int(client.ttl(redis_key))
            if ttl < 0:
                ttl = window_seconds

            if current_count > limit:
                _LOGGER.warning(
                    "Rate limit exceeded for key %s (%d/%d, retry in %ds)",
                    key,
                    current_count,
                    limit,
                    ttl,
                )
                return False, 0, ttl

            remaining = max(0, limit - current_count)
            return True, remaining, 0

        except Exception as exc:
            _LOGGER.error("Rate limiter Redis failure on key %s: %s", key, exc)
            if fail_closed:
                raise RateLimiterUnavailableError(
                    f"Rate limiter backend unavailable: {exc}"
                ) from exc
            return True, 1, 0


def rate_limit(
    *,
    limit: int,
    window_seconds: int,
    key_prefix: str = "endpoint",
    fail_closed: bool = True,
    limiter_provider: Callable[[], RedisRateLimiter | None] | None = None,
) -> Callable[[F], F]:
    """Flask decorator enforcing rate limiting per IP / account identifier."""

    def decorator(fn: F) -> F:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Response:
            limiter = limiter_provider() if limiter_provider else _default_limiter()
            if limiter is None:
                return fn(*args, **kwargs)

            # Build rate limit key: prefix + IP + optional user/account
            client_ip = (
                request.headers.get(
                    "X-Forwarded-For", request.remote_addr or "127.0.0.1"
                )
                .split(",")[0]
                .strip()
            )
            key = f"{key_prefix}:{client_ip}"

            try:
                allowed, remaining, retry_after = limiter.check_rate_limit(
                    key=key,
                    limit=limit,
                    window_seconds=window_seconds,
                    fail_closed=fail_closed,
                )
            except RateLimiterUnavailableError:
                # Sensitive fail-closed response: 503 RFC Problem Details
                resp = jsonify(
                    {
                        "type": "https://tools.ietf.org/html/rfc9110#section-15.6.4",
                        "title": "Service Unavailable",
                        "status": 503,
                        "detail": "Rate limiting backend unavailable. Request rejected fail-closed for security.",
                    }
                )
                resp.status_code = 503
                resp.content_type = "application/problem+json"
                return resp

            if not allowed:
                resp = jsonify(
                    {
                        "type": "https://tools.ietf.org/html/rfc6585#section-4",
                        "title": "Too Many Requests",
                        "status": 429,
                        "detail": f"Rate limit exceeded. Try again in {retry_after} seconds.",
                    }
                )
                resp.status_code = 429
                resp.content_type = "application/problem+json"
                resp.headers["Retry-After"] = str(retry_after)
                return resp

            response: Response = fn(*args, **kwargs)
            if hasattr(response, "headers"):
                response.headers["X-RateLimit-Limit"] = str(limit)
                response.headers["X-RateLimit-Remaining"] = str(remaining)
            return response

        return wrapper  # type: ignore[return-value]

    return decorator


def _default_limiter() -> RedisRateLimiter | None:
    redis_url = current_app.config.get("REDIS_URL") if current_app else None
    if not redis_url:
        return None
    return RedisRateLimiter(redis_url=redis_url)
