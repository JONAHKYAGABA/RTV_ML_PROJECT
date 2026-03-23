"""
Token-bucket rate limiter for API requests.

Enforces per-user request limits to prevent LLM cost explosion.
State is stored in Redis when available, with in-memory fallback.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from threading import Lock

logger = logging.getLogger(__name__)


class TokenBucketLimiter:
    """In-memory token-bucket rate limiter.

    Args:
        max_tokens: Maximum tokens (requests) in the bucket.
        refill_rate: Tokens added per second.
    """

    def __init__(self, max_tokens: int = 60, refill_rate: float = 1.0) -> None:
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate
        self._buckets: dict[str, dict] = defaultdict(
            lambda: {"tokens": max_tokens, "last_refill": time.time()}
        )
        self._lock = Lock()

    def allow(self, key: str, cost: int = 1) -> bool:
        """Check if the request is allowed for the given key.

        Returns True if allowed, False if rate-limited.
        """
        with self._lock:
            bucket = self._buckets[key]
            now = time.time()

            # Refill tokens based on elapsed time
            elapsed = now - bucket["last_refill"]
            bucket["tokens"] = min(
                self.max_tokens,
                bucket["tokens"] + elapsed * self.refill_rate,
            )
            bucket["last_refill"] = now

            if bucket["tokens"] >= cost:
                bucket["tokens"] -= cost
                return True

            logger.warning(
                "Rate limit exceeded for key=%s (tokens=%.1f, cost=%d)",
                key,
                bucket["tokens"],
                cost,
            )
            return False

    def remaining(self, key: str) -> float:
        """Return remaining tokens for the given key."""
        with self._lock:
            bucket = self._buckets[key]
            now = time.time()
            elapsed = now - bucket["last_refill"]
            return min(
                self.max_tokens,
                bucket["tokens"] + elapsed * self.refill_rate,
            )

    def reset(self, key: str) -> None:
        """Reset the bucket for a given key."""
        with self._lock:
            self._buckets[key] = {
                "tokens": self.max_tokens,
                "last_refill": time.time(),
            }


class RedisRateLimiter:
    """Redis-backed rate limiter using sliding window counters.

    Falls back to in-memory limiter if Redis is unavailable.
    """

    def __init__(
        self,
        redis_client=None,
        max_requests: int = 60,
        window_seconds: int = 60,
    ) -> None:
        self.redis = redis_client
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._fallback = TokenBucketLimiter(
            max_tokens=max_requests,
            refill_rate=max_requests / window_seconds,
        )

    def allow(self, key: str) -> bool:
        """Check if request is allowed using Redis sliding window."""
        if self.redis is None:
            return self._fallback.allow(key)

        try:
            redis_key = f"ratelimit:{key}"
            now = time.time()
            window_start = now - self.window_seconds

            pipe = self.redis.pipeline()
            pipe.zremrangebyscore(redis_key, 0, window_start)
            pipe.zadd(redis_key, {str(now): now})
            pipe.zcard(redis_key)
            pipe.expire(redis_key, self.window_seconds)
            results = pipe.execute()

            current_count = results[2]
            if current_count > self.max_requests:
                logger.warning(
                    "Redis rate limit exceeded for key=%s (%d/%d)",
                    key,
                    current_count,
                    self.max_requests,
                )
                return False
            return True
        except Exception as e:
            logger.warning("Redis rate limiter error: %s -- falling back", e)
            return self._fallback.allow(key)


# Default API rate limiter: 60 requests per minute per user
api_rate_limiter = TokenBucketLimiter(max_tokens=60, refill_rate=1.0)
