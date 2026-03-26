"""
Pydantic request/response models for the RTV API.

All API contracts are defined here as versioned schemas.
The API layer imports these; no inline model definitions in routes.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    """Request body for query endpoints."""
    question: str = Field(
        ...,
        min_length=5,
        max_length=2000,
        description="Natural language question about household data or agriculture practices",
    )
    session_id: str | None = Field(
        None,
        description="Session ID for conversation context (auto-generated if omitted)",
    )
    evaluate: bool = Field(
        False,
        description="Run LLM-as-Judge evaluation on the response",
    )


class InitializeRequest(BaseModel):
    """Request to initialize or reload the RAG pipeline."""
    force_reload: bool = Field(
        False,
        description="Force re-ingestion even if data is already indexed",
    )


class EvaluateRequest(BaseModel):
    """Request body for evaluating a query-answer pair."""
    question: str
    answer: str
    context: str | None = None
    context_chunks: list[dict[str, Any]] | None = None
    sql: str | None = None
    query_result: dict[str, Any] | None = None
    eval_type: str = Field(
        "rag",
        description="Evaluation type: 'rag' or 'sql'",
    )


# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------

class QueryResponse(BaseModel):
    """Unified response for all query endpoints."""
    question: str
    answer: str
    route: str | None = None
    sql: str | None = None
    sources: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    evaluation: dict[str, Any] | None = None
    latency_ms: float = 0
    trace_id: str | None = None


class HealthResponse(BaseModel):
    """Health check response with service status."""
    status: str = Field(description="Overall status: 'healthy' or 'degraded'")
    sql_ready: bool
    rag_ready: bool
    sql_row_count: int = 0
    rag_chunk_count: int = 0
    redis_connected: bool = False
    qdrant_connected: bool = False
    llm_circuit: str = Field("closed", description="LLM circuit breaker state")


class SchemaResponse(BaseModel):
    """Database schema description response."""
    schema_text: str
    row_count: int = 0
    column_count: int = 0


class EvaluateResponse(BaseModel):
    """Evaluation results from LLM-as-Judge."""
    evaluations: dict[str, dict[str, Any]]
    overall_pass: bool = True
