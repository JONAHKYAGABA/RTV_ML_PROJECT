"""
Circuit breaker wrappers for external service calls.

Prevents cascading failures when LLM APIs, vector DBs, or other
external services become unavailable. After N consecutive failures
the circuit opens and returns graceful fallback responses.
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from threading import Lock
from typing import Any, Callable

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"        # Normal operation
    OPEN = "open"            # Failing -- reject calls
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreakerError(Exception):
    """Raised when a call is rejected because the circuit is open."""


class CircuitBreaker:
    """Thread-safe circuit breaker for external service calls.

    Args:
        name: Identifier for logging and metrics.
        fail_max: Consecutive failures before opening the circuit.
        reset_timeout: Seconds to wait before testing recovery.
        fallback: Optional callable returning a fallback response.
    """

    def __init__(
        self,
        name: str,
        fail_max: int = 5,
        reset_timeout: float = 60.0,
        fallback: Callable[[], Any] | None = None,
    ) -> None:
        self.name = name
        self.fail_max = fail_max
        self.reset_timeout = reset_timeout
        self.fallback = fallback

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0
        self._lock = Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.time() - self._last_failure_time >= self.reset_timeout:
                    self._state = CircuitState.HALF_OPEN
                    logger.info("Circuit '%s' entering HALF_OPEN state", self.name)
            return self._state

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute func through the circuit breaker."""
        current_state = self.state

        if current_state == CircuitState.OPEN:
            logger.warning(
                "Circuit '%s' is OPEN -- rejecting call (resets in %.0fs)",
                self.name,
                self.reset_timeout - (time.time() - self._last_failure_time),
            )
            if self.fallback:
                return self.fallback()
            raise CircuitBreakerError(
                f"Circuit '{self.name}' is open. Service temporarily unavailable."
            )

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _on_success(self) -> None:
        with self._lock:
            self._failure_count = 0
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                logger.info("Circuit '%s' recovered -- CLOSED", self.name)

    def _on_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._failure_count >= self.fail_max:
                self._state = CircuitState.OPEN
                logger.error(
                    "Circuit '%s' OPEN after %d consecutive failures",
                    self.name,
                    self._failure_count,
                )

    def reset(self) -> None:
        """Manually reset the circuit to CLOSED state."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            logger.info("Circuit '%s' manually reset", self.name)


# ---------------------------------------------------------------------------
# Pre-configured breakers for each external service
# ---------------------------------------------------------------------------

llm_breaker = CircuitBreaker(
    name="llm_api",
    fail_max=5,
    reset_timeout=60,
    fallback=lambda: "The AI service is temporarily unavailable. Please retry in a moment.",
)

vectordb_breaker = CircuitBreaker(
    name="qdrant",
    fail_max=3,
    reset_timeout=30,
    fallback=lambda: "Knowledge base temporarily offline.",
)

duckdb_breaker = CircuitBreaker(
    name="duckdb",
    fail_max=3,
    reset_timeout=15,
)
