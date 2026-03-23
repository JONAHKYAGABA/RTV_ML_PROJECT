"""
Vector store management using ChromaDB (local, no Docker dependency).

Handles embedding generation and similarity search.
Falls back to ChromaDB when Qdrant is unavailable.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHROMA_DIR = PROJECT_ROOT / "data" / "chroma_db"


class VectorStore:
    """ChromaDB-based vector store for RAG retrieval."""

    def __init__(
        self,
        collection_name: str = "rtv_agriculture",
        embedding_model: str = "all-MiniLM-L6-v2",
        persist_dir: str | None = None,
    ) -> None:
        self._collection_name = collection_name
        self._embedding_model_name = embedding_model
        self._persist_dir = persist_dir or str(CHROMA_DIR)
        self._client = None
        self._collection = None
        self._embedding_fn = None

    def _get_embedding_function(self) -> Any:
        """Lazy-load the sentence-transformer embedding function."""
        if self._embedding_fn is None:
            from chromadb.utils import embedding_functions
            self._embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=self._embedding_model_name,
            )
        return self._embedding_fn

    @property
    def client(self) -> Any:
        if self._client is None:
            import chromadb
            Path(self._persist_dir).mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=self._persist_dir)
            logger.info("ChromaDB initialized at %s", self._persist_dir)
        return self._client

    @property
    def collection(self) -> Any:
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=self._collection_name,
                embedding_function=self._get_embedding_function(),
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def add_documents(self, chunks: list[dict]) -> int:
        """Add chunked documents to the vector store.

        Args:
            chunks: List of {"text": str, "metadata": dict} dicts.

        Returns:
            Number of documents added.
        """
        if not chunks:
            return 0

        ids = [f"chunk_{i}" for i in range(len(chunks))]
        documents = [c["text"] for c in chunks]
        metadatas = [
            {k: str(v) for k, v in c["metadata"].items()}
            for c in chunks
        ]

        # ChromaDB has a batch limit
        batch_size = 500
        total_added = 0
        for start in range(0, len(chunks), batch_size):
            end = min(start + batch_size, len(chunks))
            self.collection.add(
                ids=ids[start:end],
                documents=documents[start:end],
                metadatas=metadatas[start:end],
            )
            total_added += end - start

        logger.info("Added %d documents to collection '%s'",
                     total_added, self._collection_name)
        return total_added

    def search(
        self,
        query: str,
        top_k: int = 5,
        where: dict | None = None,
    ) -> list[dict]:
        """Search for similar documents.

        Returns:
            List of {"text": str, "metadata": dict, "score": float} dicts
            sorted by relevance (highest score first).
        """
        kwargs: dict[str, Any] = {
            "query_texts": [query],
            "n_results": top_k,
        }
        if where:
            kwargs["where"] = where

        results = self.collection.query(**kwargs)

        docs: list[dict] = []
        if results and results["documents"]:
            for i, doc_text in enumerate(results["documents"][0]):
                score = 1.0
                if results.get("distances") and results["distances"][0]:
                    # ChromaDB returns distances; convert to similarity
                    score = 1.0 - results["distances"][0][i]

                metadata = {}
                if results.get("metadatas") and results["metadatas"][0]:
                    metadata = results["metadatas"][0][i]

                docs.append({
                    "text": doc_text,
                    "metadata": metadata,
                    "score": score,
                })

        return docs

    def count(self) -> int:
        """Return the number of documents in the collection."""
        return self.collection.count()

    def reset(self) -> None:
        """Delete and recreate the collection."""
        self.client.delete_collection(self._collection_name)
        self._collection = None
        logger.info("Collection '%s' reset", self._collection_name)
