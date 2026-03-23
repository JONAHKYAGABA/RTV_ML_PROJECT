"""Unit tests for the vector store."""

from __future__ import annotations

import pytest

from src.rag.vector_store import VectorStore


@pytest.fixture
def store(tmp_path):
    """Create a VectorStore with a temporary directory."""
    return VectorStore(
        collection_name="test_collection",
        persist_dir=str(tmp_path / "chroma_test"),
    )


class TestVectorStore:
    """Tests for vector store operations."""

    def test_add_and_count(self, store: VectorStore):
        """Test adding documents and counting."""
        chunks = [
            {"text": "Composting is a natural process of decomposition.", "metadata": {"source": "test"}},
            {"text": "Keyhole gardens are raised garden beds.", "metadata": {"source": "test"}},
            {"text": "Liquid manure provides nutrients to soil.", "metadata": {"source": "test"}},
        ]
        added = store.add_documents(chunks)
        assert added == 3
        assert store.count() == 3

    def test_search(self, store: VectorStore):
        """Test similarity search returns results."""
        chunks = [
            {"text": "Composting breaks down organic matter into nutrient-rich soil.", "metadata": {"topic": "composting"}},
            {"text": "Keyhole gardens are circular raised beds with a center compost basket.", "metadata": {"topic": "keyhole"}},
            {"text": "Water conservation prevents soil erosion and maintains moisture.", "metadata": {"topic": "water"}},
        ]
        store.add_documents(chunks)

        results = store.search("How to make compost?", top_k=2)
        assert len(results) > 0
        assert len(results) <= 2
        # The first result should be about composting
        assert "compost" in results[0]["text"].lower()

    def test_search_empty_store(self, store: VectorStore):
        """Test search on empty collection."""
        results = store.search("any query", top_k=5)
        assert results == []

    def test_reset(self, store: VectorStore):
        """Test collection reset."""
        store.add_documents([
            {"text": "Test document", "metadata": {"source": "test"}},
        ])
        assert store.count() == 1
        store.reset()
        # Need to recreate collection reference
        store._collection = None
        assert store.count() == 0
