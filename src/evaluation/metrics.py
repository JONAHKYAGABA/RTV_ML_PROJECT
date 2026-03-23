"""
Custom evaluation metrics for the RTV ML system.

Extends the LLM-as-Judge with specific SQL and RAG quality metrics.
"""

from __future__ import annotations

import re
from typing import Any


def check_sql_correctness(sql: str, result: dict[str, Any]) -> dict[str, Any]:
    """Check SQL correctness metrics.

    Returns:
        {
            "syntax_valid": bool,
            "executed_successfully": bool,
            "has_results": bool,
            "uses_outlier_handling": bool,
            "correct_units": bool,
        }
    """
    sql_upper = sql.upper()

    return {
        "syntax_valid": result.get("success", False) or result.get("error") is None,
        "executed_successfully": result.get("success", False),
        "has_results": result.get("row_count", 0) > 0,
        "uses_outlier_handling": (
            "PERCENTILE_CONT" in sql_upper
            or "farm_implements_owned" not in sql.lower()
            or "< 100" in sql
            or "<= 100" in sql
        ),
        "correct_units": "jerrycan" in sql.lower() or "average_water" not in sql.lower(),
    }


def check_hallucination_rate(answer: str, context_chunks: list[str]) -> float:
    """Check what fraction of answer sentences are NOT grounded in context.

    Returns:
        Hallucination rate (0.0 = fully grounded, 1.0 = fully hallucinated)
    """
    # Split answer into sentences
    sentences = re.split(r"(?<=[.!?])\s+", answer)
    if not sentences:
        return 0.0

    context_text = " ".join(context_chunks).lower()
    ungrounded = 0

    for sentence in sentences:
        # Extract key terms (nouns, numbers, specific claims)
        words = re.findall(r"\b[a-z]{4,}\b", sentence.lower())
        if not words:
            continue

        # Check if at least some key terms appear in context
        matched = sum(1 for w in words if w in context_text)
        if matched < len(words) * 0.3:  # Less than 30% of terms grounded
            ungrounded += 1

    return ungrounded / len(sentences) if sentences else 0.0


def check_citation_accuracy(
    answer: str, num_sources: int
) -> dict[str, Any]:
    """Check if cited sources in the answer are valid.

    Returns:
        {"valid_citations": list, "invalid_citations": list, "accuracy": float}
    """
    # Extract all [Source N] references
    citations = re.findall(r"\[Source\s+(\d+)\]", answer)

    valid = [c for c in citations if 1 <= int(c) <= num_sources]
    invalid = [c for c in citations if int(c) < 1 or int(c) > num_sources]

    accuracy = len(valid) / len(citations) if citations else 1.0

    return {
        "valid_citations": valid,
        "invalid_citations": invalid,
        "accuracy": accuracy,
        "total_citations": len(citations),
    }
