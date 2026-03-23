"""
HyDE (Hypothetical Document Embeddings) query expansion.

Instead of embedding the user question directly (which looks nothing like
handbook text), HyDE generates a hypothetical answer passage in the style
of the handbook, then embeds that passage as the query vector. This
drastically reduces the embedding space gap between question and answer.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from config.settings import get_settings
from src.core.retry import llm_retry

logger = logging.getLogger(__name__)

HYDE_PROMPT = """Write a short passage (100-150 words) that might appear in a technical \
agriculture handbook and would directly answer the following question.
Write in the style of a field manual: specific, step-by-step, practical.
Do NOT indicate uncertainty. Write as if you are the source document.

Question: {question}

Passage:"""


class HyDEExpander:
    """Generates hypothetical documents for improved retrieval.

    Args:
        llm: Language model callable (takes prompt, returns string).
        embedding_service: Service for generating embeddings.
        blend_ratio: Weight for HyDE embedding vs original (default 0.7 HyDE).
    """

    def __init__(
        self,
        llm: Any = None,
        embedding_service: Any = None,
        blend_ratio: float = 0.7,
    ) -> None:
        self._llm = llm
        self._embedding_service = embedding_service
        self.blend_ratio = blend_ratio

    def _get_llm(self):
        """Lazy-load LLM if not provided."""
        if self._llm is None:
            from langchain_anthropic import ChatAnthropic

            settings = get_settings()
            self._llm = ChatAnthropic(
                model=settings.llm_model,
                temperature=0.1,
                max_tokens=300,
                api_key=settings.anthropic_api_key,
            )
        return self._llm

    def _get_embeddings(self):
        """Lazy-load embedding service."""
        if self._embedding_service is None:
            from src.rag.embeddings import get_embedding_service

            self._embedding_service = get_embedding_service()
        return self._embedding_service

    @llm_retry(max_attempts=2)
    def generate_hypothetical(self, question: str) -> str:
        """Generate a hypothetical document passage for the question."""
        llm = self._get_llm()
        prompt = HYDE_PROMPT.format(question=question)

        response = llm.invoke(prompt)
        hypothetical = response.content if hasattr(response, "content") else str(response)

        logger.debug(
            "HyDE generated hypothetical (%d chars) for: %s",
            len(hypothetical),
            question[:80],
        )
        return hypothetical

    def expand(self, question: str) -> tuple[str, np.ndarray]:
        """Expand query using HyDE.

        Returns:
            Tuple of (hypothetical_passage, blended_embedding).
        """
        embeddings = self._get_embeddings()

        # Generate hypothetical passage
        hypothetical = self.generate_hypothetical(question)

        # Embed both the hypothetical and original question
        hyde_embedding = embeddings.embed_query(hypothetical)
        original_embedding = embeddings.embed_query(question)

        # Blend: 70% HyDE + 30% original (empirically optimal)
        blended = (
            self.blend_ratio * hyde_embedding
            + (1 - self.blend_ratio) * original_embedding
        )

        # Normalize to unit vector
        norm = np.linalg.norm(blended)
        if norm > 0:
            blended = blended / norm

        return hypothetical, blended
