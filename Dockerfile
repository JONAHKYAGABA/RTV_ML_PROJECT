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

# Application code
COPY . .

# Create required directories with proper ownership
# Include model cache dir for HuggingFace models (BGE-M3)
RUN mkdir -p /app/data /app/outputs /app/results /app/data/chroma_db /app/.cache \
    && chown -R rtv:rtv /app

USER rtv

EXPOSE 8000

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
# HuggingFace model cache inside the container
ENV HF_HOME=/app/.cache
ENV TRANSFORMERS_CACHE=/app/.cache

# Health check -- extended start period for model download on first boot
HEALTHCHECK --interval=30s --timeout=10s --start-period=180s --retries=5 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:8000/api/v1/health || exit 1

CMD ["python", "-m", "uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
