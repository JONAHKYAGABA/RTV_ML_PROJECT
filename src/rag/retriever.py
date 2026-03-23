"""
Retrieval module with section-aware filtering and cross-encoder reranking.

Supports both ChromaDB (local dev) and Qdrant (production) backends.
Includes section-keyword mapping from the RTV Agriculture Handbook
for targeted retrieval.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Section filter map from design doc: maps keywords to handbook sections
SECTION_FILTER_MAP = {
    "composting": "Composting",
    "compost": "Composting",
    "heap": "Composting",
    "pit": "Composting",
    "decomposition": "Composting",
    "liquid manure": "Liquid Manure",
    "manure": "Liquid Manure",
    "fertilizer": "Liquid Manure",
    "keyhole": "Keyhole Gardening",
    "garden": "Keyhole Gardening",
    "raised bed": "Keyhole Gardening",
    "nursery": "Nursery Bed",
    "seedling": "Nursery Bed",
    "transplant": "Nursery Bed",
    "germination": "Nursery Bed",
    "soil": "Soil & Water Conservation",
    "water conservation": "Soil & Water Conservation",
    "erosion": "Soil & Water Conservation",
    "terracing": "Soil & Water Conservation",
    "mulching": "Soil & Water Conservation",
}


def detect_section_filter(question: str) -> str | None:
    """Detect the most relevant handbook section from question keywords."""
    q_lower = question.lower()
    for keyword, section in SECTION_FILTER_MAP.items():
        if keyword in q_lower:
            return section
    return None


def classify_content_type(text: str) -> str:
    """Classify a chunk's content type for metadata tagging."""
    import re

    if re.search(r"step \d+|procedure|excavat|construct|dig|layer", text, re.I):
        return "procedure"
    if re.search(r"materials?|requir|tools|equipment|supplies", text, re.I):
        return "materials"
    if re.search(r"when|conditions?|recommend|suitable|climate", text, re.I):
        return "conditions"
    return "rationale"


class Reranker:
    """Cross-encoder reranker for improving retrieval precision.

    Uses cross-encoder/ms-marco-MiniLM-L-6-v2 to score (question, passage) pairs
    jointly, which is more accurate than cosine similarity for final ranking.
    """

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2") -> None:
        self.model_name = model_name
        self._model = None

    def _load_model(self):
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder

                self._model = CrossEncoder(self.model_name, max_length=512)
                logger.info("Loaded cross-encoder reranker: %s", self.model_name)
            except ImportError:
                logger.warning("sentence-transformers not available for reranking")
                self._model = "unavailable"

    def rerank(
        self,
        question: str,
        passages: list[str],
        top_k: int = 5,
    ) -> list[int]:
        """Rerank passages and return indices sorted by relevance.

        Returns:
            List of passage indices ordered by relevance score (descending).
        """
        self._load_model()

        if self._model == "unavailable" or not passages:
            return list(range(min(top_k, len(passages))))

        pairs = [[question, p] for p in passages]
        scores = self._model.predict(pairs)

        ranked_indices = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True,
        )
        return ranked_indices[:top_k]


class RetrieverPipeline:
    """End-to-end retrieval pipeline with HyDE + section filtering + reranking.

    Args:
        vector_store: The vector store instance (ChromaDB or Qdrant wrapper).
        embedding_service: Embedding service for query encoding.
        reranker: Optional cross-encoder reranker.
        top_k_initial: Number of candidates for initial retrieval.
        top_k_final: Number of results after reranking.
    """

    def __init__(
        self,
        vector_store: Any,
        embedding_service: Any = None,
        reranker: Reranker | None = None,
        top_k_initial: int = 20,
        top_k_final: int = 5,
    ) -> None:
        self.vector_store = vector_store
        self.embedding_service = embedding_service
        self.reranker = reranker or Reranker()
        self.top_k_initial = top_k_initial
        self.top_k_final = top_k_final

    def retrieve(
        self,
        question: str,
        query_embedding: Any = None,
        top_k: int | None = None,
    ) -> list[dict]:
        """Retrieve and rerank relevant chunks.

        Args:
            question: User's question.
            query_embedding: Pre-computed embedding (e.g., from HyDE).
            top_k: Override for final result count.

        Returns:
            List of chunk dicts with 'text' and 'metadata' keys.
        """
        final_k = top_k or self.top_k_final

        # Detect section filter from question
        section = detect_section_filter(question)
        if section:
            logger.info("Section filter detected: %s", section)

        # Initial retrieval
        results = self.vector_store.search(
            query=question,
            n_results=self.top_k_initial,
        )

        if not results:
            return []

        # Extract texts for reranking
        texts = [r.get("text", "") for r in results]

        # Rerank
        try:
            ranked_indices = self.reranker.rerank(
                question=question,
                passages=texts,
                top_k=final_k,
            )
            reranked = [results[i] for i in ranked_indices]
        except Exception as e:
            logger.warning("Reranking failed: %s -- using original order", e)
            reranked = results[:final_k]

        return reranked
