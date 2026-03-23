"""
OpenTelemetry tracing with trace_id propagation.

Every LangGraph node, LLM call, SQL execution, and retrieval operation
emits a span under a shared trace_id propagated from the API request.
"""

from __future__ import annotations

import os
import uuid
import logging
from contextvars import ContextVar
from functools import wraps
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Context variable for trace_id propagation across async boundaries
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")
session_id_var: ContextVar[str] = ContextVar("session_id", default="")

# Flag for whether full OTEL tracing is available
_otel_available = False
_tracer = None

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter,
    )

    _otel_available = True
except ImportError:
    logger.info("OpenTelemetry not installed -- tracing disabled (install opentelemetry-sdk)")


def setup_tracing(service_name: str = "rtv-agent-system") -> None:
    """Initialize OpenTelemetry tracing if the SDK is installed."""
    global _tracer

    if not _otel_available:
        logger.warning("OpenTelemetry SDK not available -- using no-op tracer")
        return

    endpoint = os.getenv("OTEL_ENDPOINT", "http://localhost:4317")

    resource = Resource.create({
        "service.name": service_name,
        "service.version": os.getenv("GIT_SHA", "dev"),
    })

    provider = TracerProvider(resource=resource)
    try:
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
    except Exception as e:
        logger.warning("Failed to connect OTEL exporter: %s", e)

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(service_name)
    logger.info("OpenTelemetry tracing initialized (endpoint=%s)", endpoint)


def get_tracer():
    """Return the global tracer (or None if OTEL unavailable)."""
    return _tracer


def generate_trace_id() -> str:
    """Generate a new trace ID for a request."""
    return uuid.uuid4().hex[:16]


def traceable(name: str, attributes: dict[str, Any] | None = None):
    """Decorator that wraps a function in an OTEL span.

    If OTEL is not available, the function runs without instrumentation.
    Always propagates trace_id from the context variable.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            current_trace = trace_id_var.get("")

            if _tracer is not None:
                with _tracer.start_as_current_span(name) as span:
                    if current_trace:
                        span.set_attribute("rtv.trace_id", current_trace)
                    if attributes:
                        for k, v in attributes.items():
                            span.set_attribute(k, v)
                    try:
                        result = func(*args, **kwargs)
                        span.set_attribute("rtv.success", True)
                        return result
                    except Exception as e:
                        span.set_attribute("rtv.success", False)
                        span.set_attribute("rtv.error", str(e))
                        raise
            else:
                return func(*args, **kwargs)

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            current_trace = trace_id_var.get("")

            if _tracer is not None:
                with _tracer.start_as_current_span(name) as span:
                    if current_trace:
                        span.set_attribute("rtv.trace_id", current_trace)
                    if attributes:
                        for k, v in attributes.items():
                            span.set_attribute(k, v)
                    try:
                        result = await func(*args, **kwargs)
                        span.set_attribute("rtv.success", True)
                        return result
                    except Exception as e:
                        span.set_attribute("rtv.success", False)
                        span.set_attribute("rtv.error", str(e))
                        raise
            else:
                return await func(*args, **kwargs)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    return decorator
