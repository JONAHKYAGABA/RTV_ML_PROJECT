"""
FastAPI middleware stack for production hardening.

Provides:
  - Request tracing (trace_id injection)
  - Rate limiting (token bucket per IP/user)
  - Request/response logging
  - CORS configuration
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.tracing import trace_id_var, session_id_var
from src.core.rate_limiter import api_rate_limiter

logger = logging.getLogger(__name__)


class TracingMiddleware(BaseHTTPMiddleware):
    """Inject trace_id into every request and propagate via context variable."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Accept trace_id from header or generate a new one
        trace_id = request.headers.get("X-Trace-ID", uuid.uuid4().hex[:16])
        session_id = request.headers.get("X-Session-ID", "")

        token_trace = trace_id_var.set(trace_id)
        token_session = session_id_var.set(session_id)

        try:
            response = await call_next(request)
            response.headers["X-Trace-ID"] = trace_id
            return response
        finally:
            trace_id_var.reset(token_trace)
            session_id_var.reset(token_session)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-client rate limiting using token bucket algorithm."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip rate limiting for health checks
        if request.url.path in ("/api/v1/health", "/health", "/docs", "/openapi.json"):
            return await call_next(request)

        # Use client IP as rate limit key
        client_ip = request.client.host if request.client else "unknown"
        key = f"ip:{client_ip}"

        if not api_rate_limiter.allow(key):
            return Response(
                content='{"detail": "Rate limit exceeded. Max 60 requests per minute."}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": "60"},
            )

        return await call_next(request)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every request with method, path, status, and latency."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.time()
        trace_id = trace_id_var.get("")

        response = await call_next(request)

        latency_ms = round((time.time() - start) * 1000, 1)
        logger.info(
            "request",
            extra={
                "trace_id": trace_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "latency_ms": latency_ms,
                "client": request.client.host if request.client else "unknown",
            },
        )

        return response
