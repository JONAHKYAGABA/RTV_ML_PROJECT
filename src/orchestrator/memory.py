"""
Conversation memory using Redis.

Multi-turn conversation context is stored in Redis with a TTL of 1 hour.
Each session maintains a sliding window of the last 10 turns.
Falls back to in-memory dict when Redis is unavailable.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class ConversationMemory:
    """Redis-backed conversation memory with in-memory fallback."""

    def __init__(
        self,
        redis_url: str | None = None,
        max_turns: int = 10,
        ttl_seconds: int = 3600,
    ) -> None:
        self.max_turns = max_turns
        self.ttl_seconds = ttl_seconds
        self._redis = None
        self._fallback: dict[str, list[dict]] = {}

        if redis_url:
            try:
                import redis
                self._redis = redis.from_url(redis_url)
                self._redis.ping()
                logger.info("Conversation memory: Redis connected")
            except Exception as e:
                logger.warning("Redis unavailable, using in-memory fallback: %s", e)
                self._redis = None

    def get(self, session_id: str) -> list[dict[str, str]]:
        """Get conversation history for a session."""
        if self._redis:
            try:
                key = f"conv:{session_id}"
                raw = self._redis.lrange(key, 0, self.max_turns * 2 - 1)
                return [json.loads(m) for m in raw]
            except Exception:
                pass

        return self._fallback.get(session_id, [])

    def append(self, session_id: str, role: str, content: str) -> None:
        """Append a message to conversation history."""
        msg = {"role": role, "content": content}

        if self._redis:
            try:
                key = f"conv:{session_id}"
                self._redis.lpush(key, json.dumps(msg))
                self._redis.ltrim(key, 0, self.max_turns * 2 - 1)
                self._redis.expire(key, self.ttl_seconds)
                return
            except Exception:
                pass

        # Fallback
        if session_id not in self._fallback:
            self._fallback[session_id] = []
        self._fallback[session_id].insert(0, msg)
        self._fallback[session_id] = self._fallback[session_id][:self.max_turns * 2]

    def clear(self, session_id: str) -> None:
        """Clear conversation history for a session."""
        if self._redis:
            try:
                self._redis.delete(f"conv:{session_id}")
            except Exception:
                pass
        self._fallback.pop(session_id, None)
