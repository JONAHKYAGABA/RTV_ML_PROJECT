"""
Embedding service wrapper.

Supports multiple embedding backends:
  - sentence-transformers (default, CPU-friendly)
  - BGE-M3 via FlagEmbedding (production, GPU-optimized)

The service is a singleton -- initialized once and reused.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Unified embedding interface supporting multiple backends.

    Args:
        model_name: Name of the embedding model.
        device: Device to run on ('cpu', 'cuda').
        use_fp16: Use FP16 for reduced memory (GPU only).
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        device: str = "cpu",
        use_fp16: bool = False,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self._model: Any = None
        self._is_bge = "bge" in model_name.lower()
        self._use_fp16 = use_fp16

    def _load_model(self) -> None:
        """Lazy-load the embedding model."""
        if self._model is not None:
            return

        if self._is_bge:
            try:
                from FlagEmbedding import BGEM3FlagModel

                self._model = BGEM3FlagModel(
                    self.model_name,
                    use_fp16=self._use_fp16,
                    device=self.device,
                )
                logger.info("Loaded BGE-M3 model: %s (device=%s)", self.model_name, self.device)
                return
            except ImportError:
                logger.warning("FlagEmbedding not installed -- falling back to sentence-transformers")

        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(self.model_name, device=self.device)
        self._is_bge = False
        logger.info("Loaded sentence-transformer: %s (device=%s)", self.model_name, self.device)

    def embed(self, texts: list[str]) -> np.ndarray:
        """Embed a list of texts and return dense vectors.

        Returns:
            np.ndarray of shape (len(texts), dim)
        """
        self._load_model()

        if self._is_bge:
            result = self._model.encode(
                texts,
                batch_size=32,
                max_length=512,
                return_dense=True,
                return_sparse=False,
                return_colbert_vecs=False,
            )
            return np.array(result["dense_vecs"])
        else:
            return self._model.encode(texts, convert_to_numpy=True)

    def embed_query(self, text: str) -> np.ndarray:
        """Embed a single query text.

        Returns:
            np.ndarray of shape (dim,)
        """
        return self.embed([text])[0]

    def embed_for_indexing(self, texts: list[str]) -> dict:
        """Embed texts for indexing with optional sparse vectors.

        Returns dict with 'dense_vecs' and optionally 'sparse_vecs'.
        """
        self._load_model()

        if self._is_bge:
            return self._model.encode(
                texts,
                batch_size=32,
                max_length=512,
                return_dense=True,
                return_sparse=True,
                return_colbert_vecs=False,
            )
        else:
            dense = self._model.encode(texts, convert_to_numpy=True)
            return {"dense_vecs": dense}

    @property
    def dimension(self) -> int:
        """Return embedding dimension."""
        self._load_model()
        test = self.embed_query("test")
        return test.shape[0]


# Module-level singleton
_embedding_service: EmbeddingService | None = None


def get_embedding_service(
    model_name: str = "all-MiniLM-L6-v2",
    device: str = "cpu",
) -> EmbeddingService:
    """Return a singleton embedding service."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService(model_name=model_name, device=device)
    return _embedding_service
