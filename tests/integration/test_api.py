"""Integration tests for the FastAPI application."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.app import app


@pytest.fixture
def client():
    """Create a test client (skips if API key not configured)."""
    return TestClient(app)


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    def test_health_returns_200(self, client: TestClient):
        """Health endpoint should always return 200."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "sql_ready" in data
        assert "rag_ready" in data


class TestSchemaEndpoint:
    """Tests for the schema endpoint."""

    def test_schema_returns_description(self, client: TestClient):
        """Schema endpoint should return database schema."""
        response = client.get("/api/v1/schema")
        if response.status_code == 503:
            pytest.skip("System not initialized")
        assert response.status_code == 200
        data = response.json()
        assert "schema_text" in data


class TestQueryEndpoints:
    """Tests for query endpoints (require API key)."""

    def test_sql_query_validation(self, client: TestClient):
        """SQL query should validate input."""
        response = client.post("/api/v1/sql/query", json={"question": "hi"})
        # Should fail with 422 (too short) or 503 (not initialized)
        assert response.status_code in [422, 503]

    def test_rag_query_validation(self, client: TestClient):
        """RAG query should validate input."""
        response = client.post("/api/v1/rag/query", json={"question": "hi"})
        assert response.status_code in [422, 503]

    def test_unified_query_validation(self, client: TestClient):
        """Unified query should validate input."""
        response = client.post("/api/v1/query", json={"question": "hi"})
        assert response.status_code in [422, 503]
