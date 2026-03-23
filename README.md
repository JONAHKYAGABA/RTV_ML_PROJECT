# RTV Multi-Agent ML System

**Multi-Agent AI System for Raising the Village (RTV) - Technical Assignment**

A production-grade system combining **Text-to-SQL**, **RAG (Retrieval-Augmented Generation)**, and **Multi-Agent Orchestration** to analyze household survey data and agricultural knowledge for rural development in Uganda.

---

## Architecture Overview

```
                    +------------------+
                    |   FastAPI Server  |
                    |   /api/v1/query   |
                    +--------+---------+
                             |
                    +--------+---------+
                    |   Orchestrator    |
                    | (Intent Router)   |
                    +--+-----+------+--+
                       |     |      |
              +--------+  +--+--+  +--------+
              |  SQL   |  | RAG |  | Hybrid |
              | Agent  |  |Agent|  | (Both) |
              +---+----+  +--+--+  +--------+
                  |          |
           +------+    +----+-----+
           |DuckDB|    | ChromaDB |
           |27.5K |    | Handbook |
           |rows  |    | Chunks   |
           +------+    +----------+
```

### System Components

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Text-to-SQL Agent** | LangGraph (6-node) + DuckDB + sqlglot | Convert natural language to SQL queries on household data |
| **RAG Pipeline** | ChromaDB + sentence-transformers + HyDE | Retrieve and answer questions from Agriculture Handbook |
| **Orchestrator** | LangGraph Supervisor | Route queries to appropriate agent(s) based on intent |
| **Evaluation** | LLM-as-Judge (Claude) | Assess faithfulness, relevancy, precision, SQL correctness |
| **API** | FastAPI | RESTful endpoints for all system functionality |

---

## Quick Start

### Prerequisites

- Python 3.11+
- Anthropic API key ([get one here](https://console.anthropic.com/))
- Docker (optional, for containerized deployment)

### Option 1: Local Setup (Recommended for Development)

```bash
# Clone the repository
git clone https://github.com/JONAHKYAGABA/RTV_ML_PROJECT.git
cd RTV_ML_PROJECT

# Create virtual environment
python -m venv .venv
source .venv/bin/activate       # Linux/Mac
# .venv\Scripts\activate        # Windows

# Install dependencies
pip install -e ".[dev,analysis]"

# Configure environment
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# Place data files in project root:
#   - Test Data 2026-03-17-12-43.xlsx (household dataset)
#   - Copy of RTV_IMP_Handbook_*.pdf  (agriculture handbook)

# Run setup (loads data + initializes RAG)
python scripts/setup.py

# Start the API server
python -m uvicorn src.api.app:app --reload --port 8000
```

### Option 2: Docker Deployment

```bash
# Configure environment
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY

# Build and start
docker-compose up --build

# API available at http://localhost:8000
```

---

## API Reference

### Health Check
```bash
curl http://localhost:8000/api/v1/health
```

### Unified Query (Auto-Routes)
```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the average predicted income by region?", "evaluate": true}'
```

### Direct SQL Query
```bash
curl -X POST http://localhost:8000/api/v1/sql/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Which district has the highest average predicted income?"}'
```

### Direct RAG Query
```bash
curl -X POST http://localhost:8000/api/v1/rag/query \
  -H "Content-Type: application/json" \
  -d '{"question": "How should a keyhole garden be constructed?"}'
```

### Database Schema
```bash
curl http://localhost:8000/api/v1/schema
```

### Evaluate a Response
```bash
curl -X POST http://localhost:8000/api/v1/evaluate \
  -H "Content-Type: application/json" \
  -d '{"question": "...", "answer": "...", "context": "...", "eval_type": "rag"}'
```

---

## Dataset Overview

### Household Survey Data (27,525 records)

| Feature | Type | Description |
|---------|------|-------------|
| household_id | STRING | Structured ID (e.g., RUB-NTA-EZE-M-153334-7) |
| district | STRING | 22 administrative districts |
| region | STRING | 5 regions (South West, Mid West, North, Central, East) |
| cohort | INT | Launch year (2023, 2024, 2025) |
| cassava...banana | BOOL | Crop types grown by household |
| tot_hhmembers | INT | Total household members (0-20) |
| predicted_income | FLOAT | Predicted income + production value |
| prediction | BOOL | Whether household will hit income target |

**Key Statistics:**
- 54.4% of households predicted to hit target
- South West region has highest income (mean=2.08) and prediction rate (59.7%)
- VSLA participation is near-universal (93.1%)
- Maize is the most grown crop (51.9%)

### Agriculture Handbook

Topics covered: composting (pit/heap), keyhole gardens, liquid manure, organic pesticides, nursery beds, soil & water conservation.

---

## Text-to-SQL Agent (Part 1)

**Architecture:** 6-node LangGraph with self-correction loop

```
Query Rewriter -> Schema Loader -> SQL Generator -> Validator -> Executor -> Explainer
                                        ^                           |
                                        |___ retry (up to 3x) _____|
```

- **Query Rewriter**: Clarifies ambiguous terms and adds domain context
- **Schema Loader**: Provides full DuckDB schema with data quality notes
- **SQL Generator**: Produces DuckDB-dialect SQL with LLM
- **Validator**: Syntax checking via sqlglot + write-operation blocking
- **Executor**: Safe read-only execution with error handling
- **Explainer**: Natural language summary of results

**Data Quality Handling:**
- `farm_implements_owned`: Filters extreme outliers (max=30,000)
- `average_water_consumed_per_day`: Documented as JERRYCANS not liters
- `land_size`: Handles max=99 as potential 'unknown' encoding

---

## RAG Pipeline (Part 2)

**Chunking Strategy:** Section-aware RecursiveCharacterTextSplitter
- Chunk size: 900 tokens, Overlap: 180 tokens
- Custom separators optimized for handbook content structure

**Retrieval Enhancement:**
- **HyDE** (Hypothetical Document Embeddings): Generates synthetic answers for query expansion
- **Sentence-transformers** (all-MiniLM-L6-v2): Fast, local embeddings
- **ChromaDB**: Persistent vector store with cosine similarity

**Answer Generation:**
- Grounded responses with [Source N] citations
- Hallucination guard checking source reference validity
- Context-only answering (refuses to use external knowledge)

---

## Multi-Agent Orchestration (Part 3)

**Intent Classification:** LLM-based router with three categories:
- `sql`: Data/statistics questions -> SQL Agent
- `rag`: How-to/knowledge questions -> RAG Agent
- `hybrid`: Questions needing both sources -> Both agents + synthesis

**Hybrid Query Flow:**
1. Classify intent
2. Run both SQL and RAG agents
3. Synthesize unified answer referencing both data sources

---

## Evaluation Framework (Part 4)

### LLM-as-Judge Metrics

| Metric | Applies To | Description |
|--------|-----------|-------------|
| **Faithfulness** | RAG | Answer grounded in retrieved context |
| **Answer Relevancy** | SQL + RAG | Answer addresses the question asked |
| **Context Precision** | RAG | Retrieved chunks are relevant |
| **SQL Correctness** | SQL | Query matches intent, valid syntax, correct results |

### Running Evaluation

```bash
python scripts/run_evaluation.py
# Results saved to outputs/evaluation_results.json
```

---

## Project Structure

```
RTV_ML_PROJECT/
|-- config/
|   |-- settings.py           # Pydantic settings (env-based config)
|-- src/
|   |-- agents/
|   |   |-- sql_agent.py      # Text-to-SQL LangGraph agent
|   |   |-- rag_agent.py      # RAG conversational agent
|   |-- api/
|   |   |-- app.py            # FastAPI application
|   |-- db/
|   |   |-- duckdb_manager.py # DuckDB operations
|   |-- evaluation/
|   |   |-- judge.py          # LLM-as-Judge framework
|   |-- orchestrator/
|   |   |-- router.py         # Multi-agent routing
|   |-- rag/
|   |   |-- document_loader.py # Handbook ingestion + chunking
|   |   |-- pipeline.py       # End-to-end RAG pipeline
|   |   |-- vector_store.py   # ChromaDB vector store
|   |-- analysis/
|       |-- data_analysis.py  # Comprehensive EDA
|-- tests/
|   |-- unit/                 # Unit tests
|   |-- integration/          # API integration tests
|-- scripts/
|   |-- setup.py              # First-time setup
|   |-- run_evaluation.py     # Full evaluation runner
|-- outputs/
|   |-- figures/              # Analysis visualizations
|-- .env.example
|-- docker-compose.yml
|-- Dockerfile
|-- pyproject.toml
```

---

## Running Tests

```bash
# All tests
pytest

# Unit tests only
pytest tests/unit/ -v

# With coverage
pytest --cov=src tests/
```

---

## Data Analysis

Run the comprehensive EDA:

```bash
python src/analysis/data_analysis.py
```

Generates:
- 8 publication-quality figures in `outputs/figures/`
- Statistical summaries in `outputs/`
- Console report covering all 8 analysis sections

---

## Technology Choices

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Database | DuckDB | OLAP-optimized, zero-config, perfect for analytical queries on 27K rows |
| LLM | Claude (Anthropic) | Strong instruction following, JSON mode, tool use |
| Agent Framework | LangGraph | Stateful graphs with conditional edges, retry loops |
| Vector Store | ChromaDB | Local/embedded, no Docker dependency, persistent |
| Embeddings | sentence-transformers | Local, fast, no API key needed |
| SQL Validation | sqlglot | Cross-dialect SQL parsing and validation |
| API | FastAPI | Async, auto-docs, Pydantic validation |

---

## License

MIT
