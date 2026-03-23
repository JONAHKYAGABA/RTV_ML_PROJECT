"""
Evaluation Runner - Answers all assignment questions and evaluates responses.

Runs the 5 SQL evaluation questions, 6 RAG questions, and 2 hybrid questions,
then evaluates each response with LLM-as-Judge.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import get_settings
from src.agents.sql_agent import SQLAgent
from src.agents.rag_agent import RAGAgent
from src.orchestrator.router import MultiAgentOrchestrator
from src.evaluation.judge import LLMJudge

# ---------------------------------------------------------------------------
# Evaluation Questions (from the assignment)
# ---------------------------------------------------------------------------

SQL_QUESTIONS = [
    "What is the average predicted income for households in each district?",
    "Which region has the highest percentage of households predicted to meet their target?",
    "How does crop diversity (number of different crops grown) correlate with predicted income?",
    "What are the top 5 villages by average predicted income, and what crops do they primarily grow?",
    "Compare the average water consumption between households that participate in business vs those that don't.",
]

RAG_QUESTIONS = [
    "What are the recommended steps for preparing a compost pit according to the handbook?",
    "How should a keyhole garden be constructed and maintained?",
    "What materials are needed to prepare liquid manure?",
    "What organic pesticide methods does the handbook recommend?",
    "Describe the process for setting up a nursery bed.",
    "What soil and water conservation techniques are described in the handbook?",
]

HYBRID_QUESTIONS = [
    "In districts where Irish potato farming is most common, what soil conservation techniques from the handbook would be most relevant?",
    "For households with low predicted income in the North region, what agricultural practices from the handbook could help improve their productivity?",
]


def run_evaluation():
    """Execute all evaluation questions and score results."""
    print("=" * 72)
    print("  RTV MULTI-AGENT SYSTEM - EVALUATION RUNNER")
    print("=" * 72)

    # Initialize
    orchestrator = MultiAgentOrchestrator()
    orchestrator.initialize()
    judge = LLMJudge()

    results = {
        "sql_questions": [],
        "rag_questions": [],
        "hybrid_questions": [],
        "summary": {},
    }

    # --- SQL Questions ---
    print("\n--- SQL EVALUATION QUESTIONS ---\n")
    sql_scores = []
    for i, q in enumerate(SQL_QUESTIONS, 1):
        print(f"Q{i}: {q}")
        start = time.time()
        result = orchestrator.sql_agent.query(q)
        latency = (time.time() - start) * 1000

        print(f"  SQL: {result['sql'][:100]}...")
        print(f"  Answer: {result['explanation'][:200]}...")
        print(f"  Latency: {latency:.0f}ms | Retries: {result['retries']}")

        # Evaluate
        evals = judge.evaluate_sql_response(
            question=q,
            sql=result["sql"],
            query_result=result["result"],
            explanation=result["explanation"],
        )

        scores = {k: v.score for k, v in evals.items()}
        sql_scores.append(scores)
        print(f"  Scores: {scores}")
        print()

        results["sql_questions"].append({
            "question": q,
            "sql": result["sql"],
            "answer": result["explanation"],
            "latency_ms": round(latency, 1),
            "retries": result["retries"],
            "scores": scores,
        })

    # --- RAG Questions ---
    print("\n--- RAG EVALUATION QUESTIONS ---\n")
    rag_scores = []
    for i, q in enumerate(RAG_QUESTIONS, 1):
        print(f"Q{i}: {q}")
        start = time.time()
        result = orchestrator.rag_agent.query(q)
        latency = (time.time() - start) * 1000

        print(f"  Answer: {result['answer'][:200]}...")
        print(f"  Sources: {result['source_count']} chunks")
        print(f"  Latency: {latency:.0f}ms")

        # Get full pipeline result for context
        full_result = orchestrator.rag_agent.pipeline.answer(q)
        evals = judge.evaluate_rag_response(
            question=q,
            answer=result["answer"],
            context=full_result["context"],
            context_chunks=full_result["sources"],
        )

        scores = {k: v.score for k, v in evals.items()}
        rag_scores.append(scores)
        print(f"  Scores: {scores}")
        print()

        results["rag_questions"].append({
            "question": q,
            "answer": result["answer"],
            "source_count": result["source_count"],
            "latency_ms": round(latency, 1),
            "scores": scores,
        })

    # --- Hybrid Questions ---
    print("\n--- HYBRID EVALUATION QUESTIONS ---\n")
    for i, q in enumerate(HYBRID_QUESTIONS, 1):
        print(f"Q{i}: {q}")
        start = time.time()
        result = orchestrator.query(q)
        latency = (time.time() - start) * 1000

        print(f"  Route: {result['route']}")
        print(f"  Answer: {result['answer'][:200]}...")
        print(f"  Latency: {latency:.0f}ms")
        print()

        results["hybrid_questions"].append({
            "question": q,
            "answer": result["answer"],
            "route": result["route"],
            "latency_ms": round(latency, 1),
        })

    # --- Summary ---
    avg_sql = {}
    for metric in ["relevancy", "sql_correctness"]:
        vals = [s.get(metric, 0) for s in sql_scores if metric in s]
        avg_sql[metric] = sum(vals) / len(vals) if vals else 0

    avg_rag = {}
    for metric in ["faithfulness", "relevancy", "context_precision"]:
        vals = [s.get(metric, 0) for s in rag_scores if metric in s]
        avg_rag[metric] = sum(vals) / len(vals) if vals else 0

    results["summary"] = {
        "sql_avg_scores": {k: round(v, 3) for k, v in avg_sql.items()},
        "rag_avg_scores": {k: round(v, 3) for k, v in avg_rag.items()},
        "total_questions": len(SQL_QUESTIONS) + len(RAG_QUESTIONS) + len(HYBRID_QUESTIONS),
    }

    print("\n" + "=" * 72)
    print("  EVALUATION SUMMARY")
    print("=" * 72)
    print(f"\n  SQL Agent Average Scores:")
    for k, v in avg_sql.items():
        print(f"    {k:20s}: {v:.3f}")
    print(f"\n  RAG Agent Average Scores:")
    for k, v in avg_rag.items():
        print(f"    {k:20s}: {v:.3f}")

    # Save results
    output_path = Path(__file__).resolve().parents[1] / "outputs" / "evaluation_results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Results saved to: {output_path}")


if __name__ == "__main__":
    run_evaluation()
