"""
LLM-as-Judge Evaluation Framework.

Evaluates agent responses across multiple dimensions:
  - Faithfulness: Does the answer align with the retrieved context?
  - Answer Relevancy: Does the answer address the question?
  - Context Precision: Are the retrieved chunks relevant?
  - SQL Correctness: Does the generated SQL produce valid results?

Uses a separate LLM call (Claude) as the judge to avoid self-evaluation bias.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from langchain_anthropic import ChatAnthropic

from config.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass
class EvaluationResult:
    """Result of a single evaluation."""
    metric: str
    score: float  # 0.0 to 1.0
    reasoning: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMJudge:
    """LLM-based evaluation judge for RAG and SQL agent responses."""

    _llm: ChatAnthropic | None = field(default=None, init=False, repr=False)

    @property
    def llm(self) -> ChatAnthropic:
        if self._llm is None:
            settings = get_settings()
            self._llm = ChatAnthropic(
                model=settings.judge_model,
                temperature=0.0,
                max_tokens=2048,
                anthropic_api_key=settings.anthropic_api_key,
            )
        return self._llm

    def _parse_score_response(self, response_text: str, metric: str) -> EvaluationResult:
        """Parse the judge's response to extract score and reasoning."""
        try:
            # Try to parse as JSON first
            data = json.loads(response_text)
            return EvaluationResult(
                metric=metric,
                score=float(data.get("score", 0)),
                reasoning=data.get("reasoning", ""),
                details=data.get("details", {}),
            )
        except (json.JSONDecodeError, ValueError):
            # Fall back to text parsing
            score = 0.0
            lines = response_text.strip().split("\n")
            for line in lines:
                line_lower = line.lower()
                if "score" in line_lower:
                    # Extract number from line
                    import re
                    numbers = re.findall(r"(\d+\.?\d*)", line)
                    if numbers:
                        score = min(float(numbers[0]), 1.0)
                        break

            return EvaluationResult(
                metric=metric,
                score=score,
                reasoning=response_text.strip(),
            )

    # ------------------------------------------------------------------
    # Metric 1: Faithfulness
    # ------------------------------------------------------------------

    def evaluate_faithfulness(
        self,
        question: str,
        answer: str,
        context: str,
    ) -> EvaluationResult:
        """Evaluate whether the answer is faithful to the provided context."""
        prompt = f"""You are an evaluation judge. Rate the FAITHFULNESS of an answer.

Faithfulness measures whether the answer only contains information that can be
derived from the provided context. An unfaithful answer makes claims not
supported by the context.

QUESTION: {question}

CONTEXT PROVIDED:
{context[:3000]}

ANSWER BEING EVALUATED:
{answer}

Rate faithfulness on a scale of 0.0 to 1.0:
- 1.0: Every claim in the answer is supported by the context
- 0.7: Most claims are supported, minor unsupported details
- 0.5: Mix of supported and unsupported claims
- 0.3: Many unsupported claims
- 0.0: Answer contradicts or is entirely unsupported by context

Respond in JSON format:
{{"score": <float 0-1>, "reasoning": "<explanation>"}}"""

        response = self.llm.invoke(prompt)
        return self._parse_score_response(response.content, "faithfulness")

    # ------------------------------------------------------------------
    # Metric 2: Answer Relevancy
    # ------------------------------------------------------------------

    def evaluate_relevancy(
        self,
        question: str,
        answer: str,
    ) -> EvaluationResult:
        """Evaluate whether the answer is relevant to the question."""
        prompt = f"""You are an evaluation judge. Rate the RELEVANCY of an answer.

Relevancy measures whether the answer actually addresses the question asked.
An irrelevant answer might be factually correct but not answer what was asked.

QUESTION: {question}

ANSWER BEING EVALUATED:
{answer}

Rate relevancy on a scale of 0.0 to 1.0:
- 1.0: Directly and completely answers the question
- 0.7: Mostly answers the question with some tangential info
- 0.5: Partially answers the question
- 0.3: Mostly off-topic
- 0.0: Completely irrelevant to the question

Respond in JSON format:
{{"score": <float 0-1>, "reasoning": "<explanation>"}}"""

        response = self.llm.invoke(prompt)
        return self._parse_score_response(response.content, "answer_relevancy")

    # ------------------------------------------------------------------
    # Metric 3: Context Precision
    # ------------------------------------------------------------------

    def evaluate_context_precision(
        self,
        question: str,
        context_chunks: list[dict],
    ) -> EvaluationResult:
        """Evaluate whether the retrieved context chunks are relevant."""
        chunks_text = ""
        for i, chunk in enumerate(context_chunks, 1):
            text = chunk.get("text", "")[:500]
            chunks_text += f"\n[Chunk {i}]: {text}\n"

        prompt = f"""You are an evaluation judge. Rate the CONTEXT PRECISION of retrieved chunks.

Context precision measures what fraction of the retrieved chunks are actually
relevant to answering the question.

QUESTION: {question}

RETRIEVED CHUNKS:
{chunks_text}

For each chunk, determine if it's relevant to answering the question.
Then calculate precision = (relevant chunks) / (total chunks).

Respond in JSON format:
{{"score": <float 0-1>, "reasoning": "<explanation>", "details": {{"relevant_chunks": [<list of relevant chunk numbers>], "total_chunks": <int>}}}}"""

        response = self.llm.invoke(prompt)
        return self._parse_score_response(response.content, "context_precision")

    # ------------------------------------------------------------------
    # Metric 4: SQL Correctness
    # ------------------------------------------------------------------

    def evaluate_sql_correctness(
        self,
        question: str,
        sql: str,
        query_result: dict[str, Any],
        explanation: str,
    ) -> EvaluationResult:
        """Evaluate the correctness of a generated SQL query."""
        result_preview = ""
        if query_result.get("success"):
            columns = query_result.get("columns", [])
            rows = query_result.get("rows", [])[:5]
            result_preview = f"Columns: {columns}\nFirst rows: {rows}"
        else:
            result_preview = f"Query failed: {query_result.get('error', 'Unknown error')}"

        prompt = f"""You are an evaluation judge. Rate the SQL CORRECTNESS.

SQL correctness evaluates:
1. Does the SQL query match the intent of the question?
2. Is the SQL syntactically valid?
3. Does the result make sense for the question?
4. Are appropriate aggregations/filters used?

QUESTION: {question}

GENERATED SQL:
{sql}

QUERY RESULT:
{result_preview}

EXPLANATION PROVIDED:
{explanation}

Rate correctness on a scale of 0.0 to 1.0:
- 1.0: Perfect SQL, correct result, clear explanation
- 0.7: Correct approach with minor issues
- 0.5: Partially correct, may have wrong aggregation or filter
- 0.3: Significant issues but shows understanding
- 0.0: Completely wrong or query failed

Respond in JSON format:
{{"score": <float 0-1>, "reasoning": "<explanation>"}}"""

        response = self.llm.invoke(prompt)
        return self._parse_score_response(response.content, "sql_correctness")

    # ------------------------------------------------------------------
    # Batch Evaluation
    # ------------------------------------------------------------------

    def evaluate_sql_response(
        self,
        question: str,
        sql: str,
        query_result: dict[str, Any],
        explanation: str,
    ) -> dict[str, EvaluationResult]:
        """Run all applicable evaluations for a SQL agent response."""
        results: dict[str, EvaluationResult] = {}

        results["relevancy"] = self.evaluate_relevancy(question, explanation)
        results["sql_correctness"] = self.evaluate_sql_correctness(
            question, sql, query_result, explanation
        )

        return results

    def evaluate_rag_response(
        self,
        question: str,
        answer: str,
        context: str,
        context_chunks: list[dict],
    ) -> dict[str, EvaluationResult]:
        """Run all applicable evaluations for a RAG agent response."""
        results: dict[str, EvaluationResult] = {}

        results["faithfulness"] = self.evaluate_faithfulness(question, answer, context)
        results["relevancy"] = self.evaluate_relevancy(question, answer)
        results["context_precision"] = self.evaluate_context_precision(
            question, context_chunks
        )

        return results

    def format_results(self, results: dict[str, EvaluationResult]) -> str:
        """Format evaluation results as a readable table."""
        lines = ["Metric               | Score | Reasoning"]
        lines.append("-" * 80)
        for metric, result in results.items():
            score_bar = "#" * int(result.score * 10) + "." * (10 - int(result.score * 10))
            reason_short = result.reasoning[:50] + "..." if len(result.reasoning) > 50 else result.reasoning
            lines.append(f"{result.metric:20s} | {result.score:.2f}  | [{score_bar}] {reason_short}")
        return "\n".join(lines)
