"""
RAG Pipeline for the Agriculture Handbook.

Flow:
  1. Query expansion (HyDE - Hypothetical Document Embeddings)
  2. Vector search (Qdrant with BGE-M3 embeddings; ChromaDB fallback)
  3. Context assembly with source tracking
  4. Answer generation with hallucination guard
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from langchain_anthropic import ChatAnthropic

from config.settings import get_settings
from src.rag.document_loader import chunk_documents, load_handbook

logger = logging.getLogger(__name__)


def _create_vector_store():
    """Create the best available vector store (Qdrant > ChromaDB)."""
    from src.rag.qdrant_store import QdrantVectorStore

    if QdrantVectorStore.is_available():
        logger.info("Using Qdrant vector store (production)")
        return QdrantVectorStore()

    logger.info("Qdrant unavailable, falling back to ChromaDB (local)")
    from src.rag.vector_store import VectorStore
    return VectorStore()


@dataclass
class RAGPipeline:
    """End-to-end RAG pipeline for agricultural knowledge queries."""

    vector_store: Any = field(default=None)
    _llm: ChatAnthropic | None = field(default=None, init=False, repr=False)
    _initialized: bool = field(default=False, init=False)

    def __post_init__(self):
        if self.vector_store is None:
            self.vector_store = _create_vector_store()

    @property
    def llm(self) -> ChatAnthropic:
        if self._llm is None:
            settings = get_settings()
            self._llm = ChatAnthropic(
                model=settings.llm_model,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
                anthropic_api_key=settings.anthropic_api_key,
            )
        return self._llm

    def initialize(self, force_reload: bool = False) -> int:
        """Load and index the Agriculture Handbook.

        Returns the number of chunks indexed.
        """
        if self._initialized and not force_reload:
            count = self.vector_store.count()
            if count > 0:
                logger.info("Vector store already has %d documents", count)
                return count

        if force_reload:
            self.vector_store.reset()

        # Load and chunk the handbook
        documents = load_handbook()
        settings = get_settings()
        chunks = chunk_documents(
            documents,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )

        # Index into vector store
        count = self.vector_store.add_documents(chunks)
        self._initialized = True
        logger.info("RAG pipeline initialized with %d chunks", count)
        return count

    def _expand_query_hyde(self, question: str) -> str:
        """Generate a hypothetical answer to improve retrieval (HyDE).

        Creates a hypothetical document that might contain the answer,
        then uses it alongside the original query for retrieval.
        """
        prompt = f"""You are an agricultural expert in Uganda. Generate a short paragraph
(3-4 sentences) that would be found in an agriculture handbook and would
answer the following question. Write as if you are the handbook author.

Question: {question}

Hypothetical handbook passage:"""

        response = self.llm.invoke(prompt)
        hypothetical = response.content.strip()
        # Combine original query with hypothetical for richer retrieval
        return f"{question}\n\n{hypothetical}"

    def retrieve(
        self,
        question: str,
        top_k: int | None = None,
        use_hyde: bool = True,
    ) -> list[dict]:
        """Retrieve relevant chunks for a question.

        Args:
            question: User's natural language question.
            top_k: Number of results to return.
            use_hyde: Whether to use HyDE query expansion.

        Returns:
            List of {"text": str, "metadata": dict, "score": float}
        """
        settings = get_settings()
        k = top_k or settings.top_k

        if use_hyde:
            expanded_query = self._expand_query_hyde(question)
        else:
            expanded_query = question

        results = self.vector_store.search(expanded_query, top_k=k)
        logger.info("Retrieved %d chunks for query: %s", len(results), question[:80])
        return results

    def _build_context(self, chunks: list[dict]) -> str:
        """Assemble retrieved chunks into a structured context string."""
        if not chunks:
            return "No relevant context found in the Agriculture Handbook."

        context_parts: list[str] = []
        for i, chunk in enumerate(chunks, 1):
            source = chunk["metadata"].get("source", "Unknown")
            section = chunk["metadata"].get("section", "")
            page = chunk["metadata"].get("page", "")

            header = f"[Source {i}]"
            if section:
                header += f" Section: {section}"
            if page:
                header += f" (Page {page})"
            header += f" | {source}"

            context_parts.append(f"{header}\n{chunk['text']}")

        return "\n\n---\n\n".join(context_parts)

    def answer(
        self,
        question: str,
        top_k: int | None = None,
        use_hyde: bool = True,
    ) -> dict[str, Any]:
        """Answer a question using the RAG pipeline.

        Returns:
            {
                "question": original question,
                "answer": generated answer,
                "sources": list of source chunks used,
                "context": assembled context string,
            }
        """
        # Ensure initialized
        if self.vector_store.count() == 0:
            self.initialize()

        # Retrieve
        chunks = self.retrieve(question, top_k=top_k, use_hyde=use_hyde)

        # Build context
        context = self._build_context(chunks)

        # Generate answer
        prompt = f"""You are an agricultural advisor for Raising the Village (RTV) in Uganda.
Answer the question using ONLY the provided context from the Agriculture Handbook.

CONTEXT:
{context}

QUESTION: {question}

RULES:
1. Answer based ONLY on the provided context. Do not use external knowledge.
2. If the context doesn't contain enough information, say "The handbook does not
   explicitly address this topic" and explain what related information is available.
3. Cite specific sources using [Source N] references.
4. Be practical and actionable - these answers help field workers.
5. Keep the answer concise but complete (under 300 words).

ANSWER:"""

        response = self.llm.invoke(prompt)
        answer_text = response.content.strip()

        # Hallucination guard: check if answer references non-existent sources
        import re
        source_refs = set(re.findall(r"\[Source (\d+)\]", answer_text))
        valid_sources = set(str(i) for i in range(1, len(chunks) + 1))
        invalid_refs = source_refs - valid_sources
        if invalid_refs:
            logger.warning("Hallucinated source references: %s", invalid_refs)
            answer_text += (
                "\n\nNote: Some source references may not correspond to "
                "retrieved documents. Please verify against the original handbook."
            )

        return {
            "question": question,
            "answer": answer_text,
            "sources": chunks,
            "context": context,
        }
