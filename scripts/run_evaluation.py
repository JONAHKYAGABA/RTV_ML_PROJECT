"""
Evaluation Runner - Answers all assignment questions and evaluates responses.

Calls the running API at http://localhost:8000 to run the 5 SQL evaluation
questions, 6 RAG questions, and 2 hybrid questions, then evaluates each
response with the /api/v1/evaluate endpoint (LLM-as-Judge).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

API_BASE = "http://localhost:8000"

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


def api_call(method: str, path: str, body: dict | None = None) -> dict:
    """Make an API call to the running server."""
    url = API_BASE + path
    data = json.dumps(body).encode() if body else None
    req = Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    with urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def run_evaluation():
    """Execute all evaluation questions and score results."""
    print("=" * 72)
    print("  RTV MULTI-AGENT SYSTEM - EVALUATION RUNNER")
    print("=" * 72)

    # Check API health
    print("\nChecking API health...")
    try:
        health = api_call("GET", "/api/v1/health")
        print(f"  Status: {health['status']}")
        print(f"  SQL: {health['sql_row_count']} rows | RAG: {health['rag_chunk_count']} chunks")
        print(f"  Redis: {health['redis_connected']} | Qdrant: {health['qdrant_connected']}")
        if health["status"] != "healthy":
            print("  WARNING: System is degraded, results may be incomplete.")
    except Exception as e:
        print(f"  ERROR: Cannot reach API at {API_BASE}: {e}")
        print("  Make sure the API is running: docker compose up -d")
        sys.exit(1)

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
        try:
            data = api_call("POST", "/api/v1/sql/query", {"question": q})
            latency = (time.time() - start) * 1000

            print(f"  SQL: {(data.get('sql') or 'N/A')[:100]}...")
            print(f"  Answer: {(data.get('answer') or 'N/A')[:200]}...")
            print(f"  Latency: {latency:.0f}ms")

            # Evaluate with LLM-as-Judge - pass query_result for sql_correctness
            eval_data = api_call("POST", "/api/v1/evaluate", {
                "question": q,
                "answer": data.get("answer", ""),
                "eval_type": "sql",
                "sql": data.get("sql", ""),
                "query_result": data.get("metadata", {}).get("query_result", {}),
            })

            scores = {k: v["score"] for k, v in eval_data.get("evaluations", {}).items()
                      if isinstance(v, dict) and "score" in v}
            sql_scores.append(scores)
            print(f"  Judge: {scores} | Pass: {eval_data.get('overall_pass')}")

            results["sql_questions"].append({
                "question": q,
                "sql": data.get("sql"),
                "answer": data.get("answer"),
                "latency_ms": round(latency, 1),
                "scores": scores,
                "overall_pass": eval_data.get("overall_pass"),
            })
        except Exception as e:
            print(f"  ERROR: {e}")
            results["sql_questions"].append({"question": q, "error": str(e)})
        print()

    # --- RAG Questions ---
    print("\n--- RAG EVALUATION QUESTIONS ---\n")
    rag_scores = []
    for i, q in enumerate(RAG_QUESTIONS, 1):
        print(f"Q{i}: {q}")
        start = time.time()
        try:
            data = api_call("POST", "/api/v1/rag/query", {"question": q})
            latency = (time.time() - start) * 1000

            print(f"  Answer: {(data.get('answer') or 'N/A')[:200]}...")
            print(f"  Sources: {data.get('metadata', {}).get('source_count', 0)} chunks")
            print(f"  Latency: {latency:.0f}ms")

            # Evaluate with LLM-as-Judge - pass context and source chunks
            context = data.get("metadata", {}).get("context", "")
            sources = data.get("sources", [])
            eval_data = api_call("POST", "/api/v1/evaluate", {
                "question": q,
                "answer": data.get("answer", ""),
                "eval_type": "rag",
                "context": context,
                "context_chunks": sources if sources else None,
            })

            scores = {k: v["score"] for k, v in eval_data.get("evaluations", {}).items()
                      if isinstance(v, dict) and "score" in v}
            rag_scores.append(scores)
            print(f"  Judge: {scores} | Pass: {eval_data.get('overall_pass')}")

            results["rag_questions"].append({
                "question": q,
                "answer": data.get("answer"),
                "source_count": data.get("metadata", {}).get("source_count", 0),
                "latency_ms": round(latency, 1),
                "scores": scores,
                "overall_pass": eval_data.get("overall_pass"),
            })
        except Exception as e:
            print(f"  ERROR: {e}")
            results["rag_questions"].append({"question": q, "error": str(e)})
        print()

    # --- Hybrid Questions ---
    print("\n--- HYBRID EVALUATION QUESTIONS ---\n")
    hybrid_scores = []
    for i, q in enumerate(HYBRID_QUESTIONS, 1):
        print(f"Q{i}: {q}")
        start = time.time()
        try:
            data = api_call("POST", "/api/v1/query", {"question": q})
            latency = (time.time() - start) * 1000

            print(f"  Route: {data.get('route')}")
            print(f"  Answer: {(data.get('answer') or 'N/A')[:200]}...")
            print(f"  Latency: {latency:.0f}ms")

            # Evaluate with LLM-as-Judge - pass full context based on route
            eval_type = "sql" if data.get("route") == "sql" else "rag"
            eval_body = {
                "question": q,
                "answer": data.get("answer", ""),
                "eval_type": eval_type,
            }
            if data.get("sql"):
                eval_body["sql"] = data["sql"]
            if data.get("metadata", {}).get("query_result"):
                eval_body["query_result"] = data["metadata"]["query_result"]
            if data.get("metadata", {}).get("context"):
                eval_body["context"] = data["metadata"]["context"]
            if data.get("sources"):
                eval_body["context_chunks"] = data["sources"]

            eval_data = api_call("POST", "/api/v1/evaluate", eval_body)

            scores = {k: v["score"] for k, v in eval_data.get("evaluations", {}).items()
                      if isinstance(v, dict) and "score" in v}
            hybrid_scores.append(scores)
            print(f"  Judge: {scores} | Pass: {eval_data.get('overall_pass')}")

            results["hybrid_questions"].append({
                "question": q,
                "answer": data.get("answer"),
                "route": data.get("route"),
                "latency_ms": round(latency, 1),
                "scores": scores,
                "overall_pass": eval_data.get("overall_pass"),
            })
        except Exception as e:
            print(f"  ERROR: {e}")
            results["hybrid_questions"].append({"question": q, "error": str(e)})
        print()

    # --- Summary ---
    avg_sql = {}
    for metric in ["relevancy", "sql_correctness"]:
        vals = [s.get(metric, 0) for s in sql_scores if metric in s]
        avg_sql[metric] = sum(vals) / len(vals) if vals else 0

    avg_rag = {}
    for metric in ["faithfulness", "relevancy", "context_precision"]:
        vals = [s.get(metric, 0) for s in rag_scores if metric in s]
        avg_rag[metric] = sum(vals) / len(vals) if vals else 0

    all_pass = sum(1 for r in results["sql_questions"] + results["rag_questions"] + results["hybrid_questions"]
                   if r.get("overall_pass"))
    total = len(SQL_QUESTIONS) + len(RAG_QUESTIONS) + len(HYBRID_QUESTIONS)

    results["summary"] = {
        "sql_avg_scores": {k: round(v, 3) for k, v in avg_sql.items()},
        "rag_avg_scores": {k: round(v, 3) for k, v in avg_rag.items()},
        "total_questions": total,
        "passed": all_pass,
        "failed": total - all_pass,
    }

    print("\n" + "=" * 72)
    print("  EVALUATION SUMMARY")
    print("=" * 72)
    print(f"\n  Overall: {all_pass}/{total} passed")
    print(f"\n  SQL Agent Average Scores:")
    for k, v in avg_sql.items():
        bar = "#" * int(v * 20)
        print(f"    {k:20s}: {v:.3f}  [{bar:<20s}]")
    print(f"\n  RAG Agent Average Scores:")
    for k, v in avg_rag.items():
        bar = "#" * int(v * 20)
        print(f"    {k:20s}: {v:.3f}  [{bar:<20s}]")

    # Save results
    output_path = Path(__file__).resolve().parents[1] / "outputs" / "evaluation_results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Results saved to: {output_path}")
    print("=" * 72)


if __name__ == "__main__":
    run_evaluation()
