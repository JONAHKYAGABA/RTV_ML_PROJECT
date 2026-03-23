# ============================================================
# RTV Multi-Agent ML System — Production Dockerfile
# Multi-stage build for minimal image size
# ============================================================

# Stage 1: Build dependencies
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install PyTorch CPU-only FIRST (200MB instead of 2.4GB CUDA)
RUN pip install --no-cache-dir --prefix=/install \
    torch --index-url https://download.pytorch.org/whl/cpu

# Then install the rest of the deps (sentence-transformers will reuse the CPU torch)
COPY pyproject.toml ./
RUN pip install --no-cache-dir --prefix=/install . 2>&1 | tail -5

# Stage 2: Production image
FROM python:3.12-slim AS production

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# System dependencies for runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r rtv && useradd -r -g rtv -d /app -s /sbin/nologin rtv

# Create required directories (before COPY so ownership sticks)
RUN mkdir -p /app/data /app/outputs /app/results /app/.cache \
    && chown -R rtv:rtv /app

# Pre-download embedding model at build time so startup is instant
ENV HF_HOME=/app/.cache
ENV TRANSFORMERS_CACHE=/app/.cache
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3')" \
    && chown -R rtv:rtv /app/.cache

# Application code (this layer busts cache on code changes, but deps + model are cached above)
COPY --chown=rtv:rtv . .

USER rtv

EXPOSE 8000

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Health check — model is pre-downloaded, so start period can be shorter
HEALTHCHECK --interval=30s --timeout=10s --start-period=45s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:8000/api/v1/health || exit 1

CMD ["python", "-m", "uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
