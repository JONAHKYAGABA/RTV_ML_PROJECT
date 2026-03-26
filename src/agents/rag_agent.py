"""
RAG Agent wrapping the RAG pipeline with conversation-style interface.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from src.rag.pipeline import RAGPipeline

logger = logging.getLogger(__name__)


@dataclass
class RAGAgent:
    """Conversational RAG agent for agriculture handbook queries."""

    pipeline: RAGPipeline = field(default_factory=RAGPipeline)

    def initialize(self, force_reload: bool = False) -> int:
        """Initialize the underlying RAG pipeline."""
        return self.pipeline.initialize(force_reload=force_reload)

    def query(self, question: str) -> dict[str, Any]:
        """Answer a question about the agriculture handbook.

        Returns:
            {
                "question": str,
                "answer": str,
                "sources": list of source chunks,
                "source_count": int,
            }
        """
        result = self.pipeline.answer(question)

        return {
            "question": result["question"],
            "answer": result["answer"],
            "sources": [
                {
                    "text": s["text"],
                    "metadata": s["metadata"],
                    "score": s.get("score", 0),
                }
                for s in result["sources"]
            ],
            "source_count": len(result["sources"]),
            "context": result.get("context", ""),
        }
