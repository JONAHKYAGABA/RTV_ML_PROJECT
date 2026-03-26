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
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

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
redis_client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize all services on startup, cleanup on shutdown."""
    global orchestrator, judge, redis_client

    logger.info("Initializing RTV Multi-Agent System...")

    # Initialize observability
    setup_tracing()
    setup_langsmith()

    # Connect to Redis
    settings = get_settings()
    try:
        import redis
        redis_client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            socket_timeout=5,
            socket_connect_timeout=5,
        )
        redis_client.ping()
        logger.info("Redis connected at %s:%s", settings.redis_host, settings.redis_port)

        # Upgrade rate limiter to Redis-backed
        from src.core import rate_limiter as rl_module
        from src.core.rate_limiter import RedisRateLimiter
        rl_module.api_rate_limiter = RedisRateLimiter(redis_client=redis_client)
        logger.info("Rate limiter upgraded to Redis-backed")
    except Exception as e:
        logger.warning("Redis unavailable, using in-memory fallback: %s", e)
        redis_client = None

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
    if redis_client:
        redis_client.close()
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
    allow_origins=["*", "null"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
app.include_router(router)

# Serve static HTML test page
STATIC_DIR = Path(__file__).resolve().parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/test")
async def test_page():
    """Serve the API test dashboard."""
    html_path = STATIC_DIR / "index.html"
    if html_path.exists():
        return FileResponse(str(html_path), media_type="text/html")
    return {"error": "Test page not found"}


# Root endpoint
@app.get("/")
async def root():
    """API root -- links to docs and test page."""
    return {
        "service": "RTV Multi-Agent ML System",
        "version": "1.0.0",
        "docs": "/docs",
        "test_ui": "/test",
        "health": "/api/v1/health",
    }
