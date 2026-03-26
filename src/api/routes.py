"""
API route definitions for the RTV Multi-Agent System.

Endpoints:
  POST /api/v1/query          - Unified query (auto-routes SQL/RAG/hybrid)
  POST /api/v1/sql/query      - Direct SQL agent
  POST /api/v1/rag/query      - Direct RAG agent
  POST /api/v1/evaluate       - Evaluate a Q&A pair with LLM-as-Judge
  GET  /api/v1/health         - Health check with service statuses
  GET  /api/v1/schema         - Database schema info
  POST /api/v1/rag/initialize - Initialize/reload RAG pipeline
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException

from src.core.sanitizer import sanitize_input
from src.core.exceptions import InputSanitizationError
from src.core.tracing import trace_id_var
from src.core.circuit_breaker import llm_breaker
from src.api.schemas import (
    QueryRequest,
    QueryResponse,
    HealthResponse,
    SchemaResponse,
    InitializeRequest,
    EvaluateRequest,
    EvaluateResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["rtv"])


def _get_orchestrator():
    """Lazy import to avoid circular dependencies at module level."""
    from src.api.app import orchestrator
    return orchestrator


def _get_judge():
    """Lazy import to avoid circular dependencies at module level."""
    from src.api.app import judge
    return judge


# ---------------------------------------------------------------------------
# Health & Schema
# ---------------------------------------------------------------------------

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Check system health and readiness of all services."""
    orch = _get_orchestrator()
    sql_ready = False
    sql_rows = 0
    rag_ready = False
    rag_chunks = 0
    redis_ok = False
    qdrant_ok = False

    if orch:
        try:
            sql_ready = orch.sql_agent.db.is_loaded()
            if sql_ready:
                result = orch.sql_agent.db.conn.execute(
                    "SELECT COUNT(*) FROM households"
                ).fetchone()
                sql_rows = result[0] if result else 0
        except Exception:
            pass

        try:
            rag_chunks = orch.rag_agent.pipeline.vector_store.count()
            rag_ready = rag_chunks > 0
        except Exception:
            pass

        try:
            qdrant_ok = orch.rag_agent.pipeline.vector_store.client.get_collections() is not None
        except Exception:
            pass

    try:
        from src.api.app import redis_client
        if redis_client:
            redis_ok = redis_client.ping()
    except Exception:
        pass

    return HealthResponse(
        status="healthy" if (sql_ready or rag_ready) else "degraded",
        sql_ready=sql_ready,
        rag_ready=rag_ready,
        sql_row_count=sql_rows,
        rag_chunk_count=rag_chunks,
        redis_connected=redis_ok,
        qdrant_connected=qdrant_ok,
        llm_circuit=llm_breaker.state.value,
    )


@router.get("/schema", response_model=SchemaResponse)
async def get_schema():
    """Return the database schema description."""
    orch = _get_orchestrator()
    if not orch:
        raise HTTPException(503, "System not initialized")

    schema = orch.sql_agent.db.get_schema_description()
    return SchemaResponse(schema_text=schema)


# ---------------------------------------------------------------------------
# Query Endpoints
# ---------------------------------------------------------------------------

@router.post("/query", response_model=QueryResponse)
async def unified_query(request: QueryRequest):
    """Route a question to the appropriate agent(s) and return the answer."""
    orch = _get_orchestrator()
    if not orch:
        raise HTTPException(503, "System not initialized")

    try:
        question = sanitize_input(request.question)
    except InputSanitizationError as e:
        raise HTTPException(400, e.user_message)

    start = time.time()
    result = orch.query(question)
    latency = (time.time() - start) * 1000

    response = QueryResponse(
        question=result["question"],
        answer=result["answer"],
        route=result["route"],
        sql=result.get("metadata", {}).get("sql_query"),
        metadata=result.get("metadata", {}),
        latency_ms=round(latency, 1),
        trace_id=trace_id_var.get(""),
    )

    # Optional LLM-as-Judge evaluation
    jdg = _get_judge()
    if request.evaluate and jdg:
        try:
            if result["route"] == "sql" and result.get("sql_result"):
                evals = jdg.evaluate_sql_response(
                    question=request.question,
                    sql=result["sql_result"].get("sql", ""),
                    query_result=result["sql_result"].get("result", {}),
                    explanation=result["answer"],
                )
            elif result["route"] == "rag" and result.get("rag_result"):
                rag_res = result["rag_result"]
                evals = jdg.evaluate_rag_response(
                    question=request.question,
                    answer=result["answer"],
                    context="\n".join(
                        s.get("text", "") for s in rag_res.get("sources", [])
                    ),
                    context_chunks=rag_res.get("sources", []),
                )
            else:
                evals = {}

            response.evaluation = {
                k: {"score": v.score, "reasoning": v.reasoning}
                for k, v in evals.items()
            }
        except Exception as e:
            logger.error("Evaluation failed: %s", e)
            response.evaluation = {"error": str(e)}

    return response


@router.post("/sql/query", response_model=QueryResponse)
async def sql_query(request: QueryRequest):
    """Direct query to the SQL agent."""
    orch = _get_orchestrator()
    if not orch:
        raise HTTPException(503, "System not initialized")

    start = time.time()
    result = orch.sql_agent.query(request.question)
    latency = (time.time() - start) * 1000

    return QueryResponse(
        question=result["question"],
        answer=result["explanation"],
        route="sql",
        sql=result["sql"],
        metadata={"retries": result["retries"]},
        latency_ms=round(latency, 1),
        trace_id=trace_id_var.get(""),
    )


@router.post("/rag/query", response_model=QueryResponse)
async def rag_query(request: QueryRequest):
    """Direct query to the RAG agent."""
    orch = _get_orchestrator()
    if not orch:
        raise HTTPException(503, "System not initialized")

    start = time.time()
    result = orch.rag_agent.query(request.question)
    latency = (time.time() - start) * 1000

    return QueryResponse(
        question=result["question"],
        answer=result["answer"],
        route="rag",
        metadata={"source_count": result["source_count"]},
        latency_ms=round(latency, 1),
        trace_id=trace_id_var.get(""),
    )


# ---------------------------------------------------------------------------
# RAG Management
# ---------------------------------------------------------------------------

@router.post("/rag/initialize")
async def initialize_rag(request: InitializeRequest):
    """Initialize or reload the RAG pipeline."""
    orch = _get_orchestrator()
    if not orch:
        raise HTTPException(503, "System not initialized")

    try:
        count = orch.rag_agent.initialize(force_reload=request.force_reload)
        return {"status": "success", "chunks_indexed": count}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

@router.post("/evaluate", response_model=EvaluateResponse)
async def evaluate_response(request: EvaluateRequest):
    """Evaluate a question-answer pair using LLM-as-Judge."""
    jdg = _get_judge()
    if not jdg:
        raise HTTPException(503, "Judge not initialized")

    try:
        if request.eval_type == "sql":
            evals = jdg.evaluate_sql_response(
                question=request.question,
                sql=request.sql or "",
                query_result=request.query_result or {},
                explanation=request.answer,
            )
        else:
            evals = jdg.evaluate_rag_response(
                question=request.question,
                answer=request.answer,
                context=request.context or "",
                context_chunks=[{"text": request.context or ""}],
            )

        results = {
            k: {"score": v.score, "reasoning": v.reasoning}
            for k, v in evals.items()
        }

        overall_pass = all(
            v.get("score", 0) >= 0.7 for v in results.values()
            if isinstance(v.get("score"), (int, float))
        )

        return EvaluateResponse(evaluations=results, overall_pass=overall_pass)
    except Exception as e:
        raise HTTPException(500, f"Evaluation error: {e}")
