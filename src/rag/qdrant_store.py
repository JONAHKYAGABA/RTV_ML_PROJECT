"""
Qdrant-backed vector store for production RAG.

Uses BGE-M3 embeddings (1024-dim) with Qdrant for dense vector search.
Falls back gracefully when Qdrant is unreachable.
"""

from __future__ import annotations

import logging
from typing import Any

from config.settings import get_settings
from src.rag.embeddings import get_embedding_service

logger = logging.getLogger(__name__)


class QdrantVectorStore:
    """Qdrant vector store with BGE-M3 embeddings.

    Args:
        collection_name: Qdrant collection name.
        embedding_model: Embedding model name (default from settings).
    """

    def __init__(
        self,
        collection_name: str | None = None,
        embedding_model: str | None = None,
    ) -> None:
        settings = get_settings()
        self._collection_name = collection_name or settings.qdrant_collection
        self._embedding_model = embedding_model or settings.embedding_model
        self._client = None
        self._embedding_service = None

    @property
    def embedding_service(self):
        if self._embedding_service is None:
            self._embedding_service = get_embedding_service(
                model_name=self._embedding_model,
            )
        return self._embedding_service

    @property
    def client(self):
        if self._client is None:
            from qdrant_client import QdrantClient

            settings = get_settings()
            self._client = QdrantClient(
                host=settings.qdrant_host,
                port=settings.qdrant_port,
                timeout=10,
            )
            logger.info(
                "Connected to Qdrant at %s:%s",
                settings.qdrant_host,
                settings.qdrant_port,
            )
        return self._client

    def _ensure_collection(self, vector_size: int) -> None:
        """Create collection if it doesn't exist."""
        from qdrant_client.models import Distance, VectorParams

        collections = [c.name for c in self.client.get_collections().collections]
        if self._collection_name not in collections:
            self.client.create_collection(
                collection_name=self._collection_name,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=Distance.COSINE,
                ),
            )
            logger.info(
                "Created Qdrant collection '%s' (dim=%d)",
                self._collection_name,
                vector_size,
            )

    def add_documents(self, chunks: list[dict]) -> int:
        """Add chunked documents to Qdrant.

        Args:
            chunks: List of {"text": str, "metadata": dict} dicts.

        Returns:
            Number of documents added.
        """
        if not chunks:
            return 0

        from qdrant_client.models import PointStruct

        texts = [c["text"] for c in chunks]
        embeddings = self.embedding_service.embed(texts)

        self._ensure_collection(vector_size=embeddings.shape[1])

        points = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            payload = {
                "text": chunk["text"],
                **{k: str(v) for k, v in chunk["metadata"].items()},
            }
            points.append(
                PointStruct(
                    id=i,
                    vector=embedding.tolist(),
                    payload=payload,
                )
            )

        # Upload in batches
        batch_size = 100
        for start in range(0, len(points), batch_size):
            batch = points[start : start + batch_size]
            self.client.upsert(
                collection_name=self._collection_name,
                points=batch,
            )

        logger.info(
            "Added %d documents to Qdrant collection '%s'",
            len(chunks),
            self._collection_name,
        )
        return len(chunks)

    def search(
        self,
        query: str,
        top_k: int = 5,
        **kwargs: Any,
    ) -> list[dict]:
        """Search for similar documents.

        Returns:
            List of {"text": str, "metadata": dict, "score": float} dicts.
        """
        query_embedding = self.embedding_service.embed_query(query)

        try:
            from qdrant_client.models import models
            response = self.client.query_points(
                collection_name=self._collection_name,
                query=query_embedding.tolist(),
                limit=top_k,
            )
            results = response.points
        except Exception as e:
            logger.error("Qdrant search failed: %s", e)
            return []

        docs = []
        for hit in results:
            payload = hit.payload or {}
            text = payload.pop("text", "")
            docs.append({
                "text": text,
                "metadata": payload,
                "score": hit.score,
            })

        return docs

    def count(self) -> int:
        """Return number of documents in the collection."""
        try:
            info = self.client.get_collection(self._collection_name)
            return info.points_count
        except Exception:
            return 0

    def reset(self) -> None:
        """Delete and recreate the collection."""
        try:
            self.client.delete_collection(self._collection_name)
            logger.info("Deleted Qdrant collection '%s'", self._collection_name)
        except Exception:
            pass

    @staticmethod
    def is_available() -> bool:
        """Check if Qdrant is reachable."""
        try:
            from qdrant_client import QdrantClient

            settings = get_settings()
            client = QdrantClient(
                host=settings.qdrant_host,
                port=settings.qdrant_port,
                timeout=3,
            )
            client.get_collections()
            return True
        except Exception:
            return False
