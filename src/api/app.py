"""
FastAPI application for the RTV Multi-Agent ML System.

Integrates:
  - Middleware stack (tracing, rate limiting, request logging)
  - Separated route definitions (src.api.routes)
  - Structured schema models (src.api.schemas)
  - OpenTelemetry tracing initialization
  - Lifespan management for all services
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.tracing import setup_tracing
from src.core.observability import setup_langsmith
from src.api.middleware import TracingMiddleware, RateLimitMiddleware, RequestLoggingMiddleware
from src.api.routes import router

from config.settings import get_settings
from src.agents.sql_agent import SQLAgent
from src.agents.rag_agent import RAGAgent
from src.orchestrator.router import MultiAgentOrchestrator
from src.evaluation.judge import LLMJudge

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global instances (initialized on startup)
# ---------------------------------------------------------------------------
orchestrator: MultiAgentOrchestrator | None = None
judge: LLMJudge | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize all services on startup, cleanup on shutdown."""
    global orchestrator, judge

    logger.info("Initializing RTV Multi-Agent System...")

    # Initialize observability
    setup_tracing()
    setup_langsmith()

    # Initialize orchestrator (SQL agent + RAG agent)
    orchestrator = MultiAgentOrchestrator()

    # Load SQL database
    row_count = orchestrator.sql_agent.db.ensure_loaded()
    logger.info("SQL database ready: %d rows", row_count)

    # Initialize RAG pipeline
    try:
        chunk_count = orchestrator.rag_agent.initialize()
        logger.info("RAG pipeline ready: %d chunks", chunk_count)
    except FileNotFoundError:
        logger.warning("Agriculture Handbook not found - RAG queries will fail until initialized")

    # Initialize evaluation judge
    judge = LLMJudge()
    logger.info("System ready.")

    yield

    # Cleanup
    if orchestrator:
        orchestrator.sql_agent.db.close()
    logger.info("System shutdown complete.")


# ---------------------------------------------------------------------------
# App Factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="RTV Multi-Agent ML System",
    description=(
        "Production-grade multi-agent AI system combining Text-to-SQL and RAG "
        "for Raising the Village household data and agriculture knowledge. "
        "Features LangGraph orchestration, DuckDB OLAP, Qdrant vector search, "
        "and LLM-as-Judge evaluation."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Middleware stack (order matters: outermost first)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(TracingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
app.include_router(router)


# Root endpoint
@app.get("/")
async def root():
    """API root -- redirect to docs."""
    return {
        "service": "RTV Multi-Agent ML System",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/v1/health",
    }
