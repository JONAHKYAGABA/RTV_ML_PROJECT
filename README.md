# RTV Multi-Agent ML System

**Multi-Agent AI System for Raising the Village (RTV) - ML Engineer Technical Assignment**

A production-grade system combining **Text-to-SQL**, **RAG (Retrieval-Augmented Generation)**, and **Multi-Agent Orchestration** to analyze household survey data and agricultural knowledge for rural development in Uganda.

---

## Architecture Overview

```
User Query
    |
    v
+------------------+       +------------------+
|   FastAPI Server  |------>|   Test Dashboard |
|   /api/v1/*       |       |   /test          |
+--------+---------+       +------------------+
         |
+--------+---------+
|   Orchestrator    |   (LangGraph Supervisor)
| (Intent Router)   |
+--+-----+------+--+
   |     |      |
+--+--+ +--+--+ +--------+
| SQL | | RAG | | Hybrid |
|Agent| |Agent| | (Both) |
+--+--+ +--+--+ +--------+
   |       |
+--+--+ +--+--------+-------+
|DuckDB| | Qdrant   | BGE-M3|
|27.5K | | Vector   | 1024d |
|rows  | | Store    | embed |
+------+ +----------+-------+
```

### System Components

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Text-to-SQL Agent** | LangGraph (6-node) + DuckDB + sqlglot | Convert natural language to SQL queries on household data |
| **RAG Pipeline** | Qdrant + BGE-M3 + HyDE + Cross-Encoder Reranker | Retrieve and answer questions from Agriculture Handbook |
| **Orchestrator** | LangGraph Supervisor | Route queries to appropriate agent(s) based on intent |
| **Evaluation** | LLM-as-Judge (Claude Sonnet 4) | Assess faithfulness, relevancy, precision, SQL correctness |
| **API** | FastAPI + middleware stack | RESTful endpoints with tracing, rate limiting, logging |
| **Observability** | LangSmith + Weights & Biases + OpenTelemetry + Jaeger | Full tracing, experiment tracking, metric logging |

### Infrastructure Services (Docker)

| Service | Image | Purpose |
|---------|-------|---------|
| **Qdrant** | qdrant/qdrant:v1.9.7 | Production vector database (cosine similarity) |
| **Redis** | redis:7-alpine | Caching, conversation memory, semantic cache |
| **MinIO** | minio/minio:latest | S3-compatible object storage for artifacts |
| **Jaeger** | jaegertracing/all-in-one:1.54 | Distributed tracing UI (OpenTelemetry) |

---

## Quick Start (Docker - Recommended)

### Prerequisites

- **Docker** and **Docker Compose** installed
- **Anthropic API key** ([get one here](https://console.anthropic.com/))
- **Data files** in project root:
  - `Test Data 2026-03-17-12-43.xlsx` (household dataset)
  - `Copy of RTV_IMP_Handbook_*.pdf` (agriculture handbook)

### 1. Configure Environment

```bash
git clone https://github.com/JONAHKYAGABA/RTV_ML_PROJECT.git
cd RTV_ML_PROJECT

cp .env.example .env
# Edit .env and set your ANTHROPIC_API_KEY
```

### 2. Build and Start

```bash
docker compose up --build -d
```

This starts all services:
- **API Server**: http://localhost:8000
- **API Docs (Swagger)**: http://localhost:8000/docs
- **Test Dashboard**: http://localhost:8000/test
- **Qdrant UI**: http://localhost:6333/dashboard
- **MinIO Console**: http://localhost:9001
- **Jaeger Tracing**: http://localhost:16686

### 3. Test the System

Open the **Test Dashboard** at http://localhost:8000/test to interactively test all endpoints including edge cases.

Or use curl:

```bash
# Health check
curl http://localhost:8000/api/v1/health

# SQL query
curl -X POST http://localhost:8000/api/v1/sql/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What proportion of households participate in business by region?"}'

# RAG query
curl -X POST http://localhost:8000/api/v1/rag/query \
  -H "Content-Type: application/json" \
  -d '{"question": "How do I construct a compost pit?"}'

# Unified query (auto-routes)
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the average predicted income by region?"}'

# Database schema
curl http://localhost:8000/api/v1/schema
```

### 4. Run Tests in Docker

```bash
# Unit tests
docker compose exec api python -m pytest tests/unit/ -v

# Integration tests
docker compose exec api python -m pytest tests/integration/ -v

# All tests with coverage
docker compose exec api python -m pytest tests/ -v --cov=src
```

### 5. Run Evaluation Harness

```bash
docker compose exec api python -m src.evaluation.runner
# Results: results/latest_eval.json and results/latest_eval.md
```

### 6. Stop Services

```bash
docker compose down
# To also remove volumes:
docker compose down -v
```

---

## Local Development (Without Docker)

```bash
python -m venv .venv
source .venv/bin/activate       # Linux/Mac
# .venv\Scripts\activate        # Windows

pip install -e ".[dev,analysis]"

cp .env.example .env
# Set ANTHROPIC_API_KEY, and update hosts to localhost (QDRANT_HOST=localhost, REDIS_HOST=localhost)

python -m uvicorn src.api.app:app --reload --port 8000
```

Note: Without Docker, Qdrant/Redis/MinIO/Jaeger won't be available. The system falls back to ChromaDB for vector storage.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/health` | System health check (SQL + RAG status) |
| `GET` | `/api/v1/schema` | Database schema description |
| `POST` | `/api/v1/query` | Unified query (auto-routes to SQL/RAG/hybrid) |
| `POST` | `/api/v1/sql/query` | Direct SQL agent query |
| `POST` | `/api/v1/rag/query` | Direct RAG agent query |
| `POST` | `/api/v1/rag/initialize` | Initialize/reload RAG pipeline |
| `POST` | `/api/v1/evaluate` | Run LLM-as-Judge evaluation |
| `GET` | `/test` | Interactive API test dashboard |
| `GET` | `/docs` | Swagger API documentation |
| `GET` | `/redoc` | ReDoc API documentation |

---

## Project Structure

```
RTV_ML_PROJECT/
|-- config/
|   |-- settings.py              # Pydantic settings (env-based config)
|   |-- eval_questions.yaml      # Benchmark evaluation questions
|-- src/
|   |-- agents/
|   |   |-- sql_agent.py         # Text-to-SQL LangGraph agent (6-node)
|   |   |-- rag_agent.py         # RAG conversational agent
|   |-- api/
|   |   |-- app.py               # FastAPI application + lifespan
|   |   |-- routes.py            # API route definitions
|   |   |-- schemas.py           # Pydantic request/response models
|   |   |-- middleware.py         # Tracing, rate limiting, logging
|   |   |-- static/index.html    # Interactive test dashboard
|   |-- core/
|   |   |-- tracing.py           # OpenTelemetry setup + @traceable
|   |   |-- circuit_breaker.py   # Circuit breakers for LLM/DB/Vector
|   |   |-- rate_limiter.py      # Token bucket + Redis rate limiting
|   |   |-- observability.py     # LangSmith + W&B integration
|   |-- db/
|   |   |-- duckdb_manager.py    # DuckDB operations + indexes + views
|   |   |-- schema_context.py    # Schema DDL + column descriptions + few-shot examples
|   |   |-- connection_pool.py   # Thread-safe connection pool
|   |-- evaluation/
|   |   |-- judge.py             # LLM-as-Judge (4 metrics)
|   |   |-- runner.py            # Full evaluation harness
|   |-- orchestrator/
|   |   |-- router.py            # Multi-agent LangGraph routing
|   |-- rag/
|   |   |-- document_loader.py   # Handbook ingestion + section-aware chunking
|   |   |-- pipeline.py          # End-to-end RAG pipeline (HyDE + retrieve + generate)
|   |   |-- vector_store.py      # ChromaDB vector store (local fallback)
|   |   |-- qdrant_store.py      # Qdrant vector store (production)
|   |   |-- embeddings.py        # BGE-M3 / sentence-transformers wrapper
|   |   |-- hyde.py              # Hypothetical Document Embeddings
|   |   |-- retriever.py         # Section-aware retrieval + cross-encoder reranker
|   |-- analysis/
|       |-- data_analysis.py     # Comprehensive EDA
|-- tests/
|   |-- unit/                    # Unit tests (DuckDB, vector store, etc.)
|   |-- integration/             # API integration tests
|-- results/                     # Evaluation reports (JSON + Markdown)
|-- data/                        # DuckDB database files
|-- .env.example                 # Environment variable template
|-- docker-compose.yml           # Full stack: API + Qdrant + Redis + MinIO + Jaeger
|-- Dockerfile                   # Multi-stage production build
|-- pyproject.toml               # Dependencies and build config
```

---

## Text-to-SQL Agent (Part 1)

**Architecture:** 6-node LangGraph with self-correction loop

```
Query Rewriter -> Schema Loader -> SQL Generator -> Validator -> Executor -> Explainer
                                        ^                           |
                                        |___ retry (up to 3x) _____|
```

**Data Quality Handling:**
- `farm_implements_owned`: Uses `PERCENTILE_CONT(0.5)` or `WHERE farm_implements_owned <= 100` (outlier max=30,000)
- `average_water_consumed_per_day`: Units are JERRYCANS (1 jerrycan ~ 20 liters), zero = possible missing data
- `household_id`: Structured string (never cast to integer)
- `land_size_for_crop_agriculture_acres`: max=99 may encode 'unknown'

**DuckDB Indexes:**
- `idx_region`, `idx_district`, `idx_prediction`, `idx_region_pred`
- `farm_implements_clean` view (filters outliers > 100)

---

## RAG Pipeline (Part 2)

**Embedding Model:** BAAI/bge-m3 (1024-dim, dense + sparse vectors)

**Retrieval Pipeline:**
1. **Section-aware chunking** (900 tokens, 180 overlap)
2. **HyDE query expansion** (70% hypothetical + 30% original)
3. **Qdrant vector search** (cosine similarity, top-20 candidates)
4. **Cross-encoder reranking** (ms-marco-MiniLM-L-6-v2, top-5 final)

**Section Filter Map:** Auto-detects handbook sections (Composting, Liquid Manure, Keyhole Gardening, Nursery Bed, Soil & Water Conservation) from question keywords.

---

## Multi-Agent Orchestration (Part 3)

**Intent Classification:** LLM-based router with three categories:
- `sql`: Data/statistics questions -> SQL Agent
- `rag`: How-to/knowledge questions -> RAG Agent
- `hybrid`: Questions needing both sources -> Both agents + synthesis

---

## Evaluation Framework (Part 4)

### LLM-as-Judge Metrics

| Metric | Applies To | Description |
|--------|-----------|-------------|
| **Faithfulness** | RAG | Answer grounded in retrieved context |
| **Answer Relevancy** | SQL + RAG | Answer addresses the question asked |
| **Context Precision** | RAG | Retrieved chunks are relevant |
| **SQL Correctness** | SQL | Query matches intent, valid syntax, correct results |

**Judge Model:** Claude Sonnet 4 (separate from generation model to avoid self-evaluation bias)

### Running Evaluation

```bash
# In Docker
docker compose exec api python -m src.evaluation.runner

# Locally
python -m src.evaluation.runner
```

Results saved to `results/latest_eval.json` and `results/latest_eval.md`.

---

## Technology Stack

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Database | DuckDB | OLAP-optimized, zero-config, analytical queries on 27K rows |
| LLM | Claude Sonnet 4 (Anthropic) | Strong instruction following, JSON mode |
| Agent Framework | LangGraph | Stateful graphs with conditional edges, retry loops |
| Vector Store | Qdrant (prod) / ChromaDB (dev) | Production-grade with metadata filtering |
| Embeddings | BAAI/bge-m3 (1024-dim) | Dense + sparse, multilingual, state-of-the-art |
| Reranker | cross-encoder/ms-marco-MiniLM-L-6-v2 | Accurate joint scoring |
| SQL Validation | sqlglot | Cross-dialect SQL parsing and validation |
| API | FastAPI | Async, auto-docs, Pydantic validation |
| Caching | Redis | Conversation memory, semantic cache |
| Object Storage | MinIO | S3-compatible artifact storage |
| Tracing | OpenTelemetry + Jaeger | Distributed tracing with UI |
| Experiment Tracking | LangSmith + Weights & Biases | Full observability |

---

## License

MIT
