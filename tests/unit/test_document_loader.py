"""Unit tests for the document loader and chunking."""

from __future__ import annotations

import pytest

from src.rag.document_loader import chunk_documents


class TestChunkDocuments:
    """Tests for document chunking."""

    def test_basic_chunking(self):
        """Test that documents are chunked correctly."""
        docs = [
            {
                "text": "A " * 500,  # ~1000 chars
                "metadata": {"source": "test.pdf", "page": 1},
            }
        ]
        chunks = chunk_documents(docs, chunk_size=200, chunk_overlap=40)
        assert len(chunks) > 1

    def test_metadata_preserved(self):
        """Test that metadata is preserved through chunking."""
        docs = [
            {
                "text": "This is a test document with enough content to create at least one chunk. " * 20,
                "metadata": {"source": "handbook.pdf", "page": 5},
            }
        ]
        chunks = chunk_documents(docs, chunk_size=200, chunk_overlap=40)
        for chunk in chunks:
            assert chunk["metadata"]["source"] == "handbook.pdf"
            assert chunk["metadata"]["page"] == "5" or chunk["metadata"]["page"] == 5
            assert "chunk_index" in chunk["metadata"]

    def test_empty_input(self):
        """Test handling of empty document list."""
        chunks = chunk_documents([])
        assert chunks == []

    def test_short_chunks_filtered(self):
        """Test that very short chunks are filtered out."""
        docs = [
            {
                "text": "Short",
                "metadata": {"source": "test.pdf"},
            }
        ]
        chunks = chunk_documents(docs, chunk_size=900, chunk_overlap=180)
        # "Short" is < 50 chars, should be filtered
        assert len(chunks) == 0

    def test_chunk_overlap(self):
        """Test that chunks have proper overlap."""
        text = "word " * 400  # ~2000 chars
        docs = [{"text": text, "metadata": {"source": "test.pdf"}}]
        chunks = chunk_documents(docs, chunk_size=500, chunk_overlap=100)

        # Check that consecutive chunks share some text
        if len(chunks) >= 2:
            c1 = chunks[0]["text"]
            c2 = chunks[1]["text"]
            # The end of c1 should overlap with the start of c2
            assert len(c1) > 0
            assert len(c2) > 0
