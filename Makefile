.PHONY: help install dev setup test lint run eval docker clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## Install production dependencies
	pip install -e .

dev:  ## Install dev + analysis dependencies
	pip install -e ".[dev,analysis]"

setup:  ## First-time setup (load data + initialize RAG)
	python scripts/setup.py

test:  ## Run all tests
	pytest tests/ -v --tb=short

test-unit:  ## Run unit tests only
	pytest tests/unit/ -v --tb=short

test-integration:  ## Run integration tests
	pytest tests/integration/ -v --tb=short

test-cov:  ## Run tests with coverage
	pytest tests/ --cov=src --cov-report=html --cov-report=term

lint:  ## Run linter (ruff)
	ruff check src/ tests/ config/
	ruff format --check src/ tests/ config/

format:  ## Auto-format code
	ruff format src/ tests/ config/

typecheck:  ## Run mypy type checking
	mypy src/ --ignore-missing-imports

run:  ## Start the API server (development)
	uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000

run-prod:  ## Start the API server (production)
	uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --workers 4

eval:  ## Run full evaluation harness
	python scripts/run_evaluation.py

analysis:  ## Run data analysis
	python src/analysis/data_analysis.py

docker:  ## Build and run with Docker Compose
	docker-compose up --build -d

docker-down:  ## Stop Docker services
	docker-compose down

clean:  ## Clean generated files
	rm -rf __pycache__ .pytest_cache htmlcov .coverage
	rm -rf outputs/figures/*.png outputs/*.csv outputs/*.json outputs/*.md
	rm -rf data/rtv_households.duckdb data/chroma_db/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
