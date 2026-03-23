"""
Full evaluation harness runner.

Executes all benchmark questions from eval_questions.yaml, scores
each with the LLM-as-Judge, and produces a structured JSON + Markdown report.
Designed to run in CI: exits non-zero if any metric falls below threshold.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

EVAL_QUESTIONS_PATH = Path(__file__).resolve().parents[2] / "config" / "eval_questions.yaml"
RESULTS_DIR = Path(__file__).resolve().parents[2] / "results"


def load_eval_questions() -> dict[str, Any]:
    """Load evaluation questions from YAML config."""
    with open(EVAL_QUESTIONS_PATH) as f:
        return yaml.safe_load(f)


class EvaluationRunner:
    """Orchestrates the full evaluation pipeline.

    Args:
        orchestrator: The MultiAgentOrchestrator instance.
        judge: The LLMJudge instance.
    """

    def __init__(self, orchestrator, judge) -> None:
        self.orchestrator = orchestrator
        self.judge = judge

    def run_all(self, output_dir: str | Path | None = None) -> dict[str, Any]:
        """Run all evaluation questions and produce a report.

        Returns:
            Complete evaluation report as a dictionary.
        """
        output_dir = Path(output_dir) if output_dir else RESULTS_DIR
        output_dir.mkdir(parents=True, exist_ok=True)

        config = load_eval_questions()
        eval_run_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now(timezone.utc).isoformat()

        results = {
            "eval_run_id": eval_run_id,
            "timestamp": timestamp,
            "questions": [],
            "summary": {},
        }

        all_questions = []
        for category in ["sql_questions", "rag_questions", "hybrid_questions"]:
            for q in config.get(category, []):
                q["_category"] = category
                all_questions.append(q)

        logger.info("Running evaluation: %d questions", len(all_questions))

        for i, q_config in enumerate(all_questions, 1):
            qid = q_config.get("id", f"Q{i}")
            question = q_config["question"]
            expected_route = q_config.get("expected_route", "unknown")

            logger.info("[%d/%d] Evaluating: %s", i, len(all_questions), question[:60])

            q_result = self._evaluate_single(qid, question, expected_route, q_config)
            results["questions"].append(q_result)

        # Compute summary
        results["summary"] = self._compute_summary(results["questions"])
        results["overall_pass"] = all(q["pass"] for q in results["questions"])

        # Write outputs
        self._write_json_report(results, output_dir)
        self._write_markdown_report(results, output_dir)

        pass_count = sum(1 for q in results["questions"] if q["pass"])
        total = len(results["questions"])
        logger.info(
            "Evaluation complete: %d/%d passed (overall: %s)",
            pass_count,
            total,
            "PASS" if results["overall_pass"] else "FAIL",
        )

        return results

    def _evaluate_single(
        self,
        qid: str,
        question: str,
        expected_route: str,
        config: dict,
    ) -> dict[str, Any]:
        """Evaluate a single question."""
        start = time.time()

        try:
            result = self.orchestrator.query(question)
            latency_ms = int((time.time() - start) * 1000)

            actual_route = result.get("route", "unknown")
            route_correct = actual_route == expected_route

            q_result = {
                "id": qid,
                "question": question,
                "expected_route": expected_route,
                "actual_route": actual_route,
                "route_correct": route_correct,
                "answer": result.get("answer", ""),
                "latency_ms": latency_ms,
                "pass": route_correct,  # May be updated by judge scores
            }

            # Add SQL-specific fields
            if actual_route == "sql":
                sql_result = result.get("sql_result", {})
                q_result["generated_sql"] = sql_result.get("sql", "")
                q_result["sql_valid"] = sql_result.get("result", {}).get("success", False)
                q_result["rows_returned"] = sql_result.get("result", {}).get("row_count", 0)
                q_result["attempts"] = sql_result.get("retries", 0) + 1

            # Add RAG-specific fields
            if actual_route == "rag":
                rag_result = result.get("rag_result", {})
                q_result["chunks_retrieved"] = len(rag_result.get("sources", []))

            # Run LLM-as-Judge
            try:
                judge_scores = self._run_judge(result, question, actual_route)
                q_result["judge_scores"] = judge_scores

                # Check if scores meet thresholds
                thresholds = config.get("thresholds", {})
                for metric, threshold in thresholds.items():
                    if metric in judge_scores:
                        if judge_scores[metric] < threshold:
                            q_result["pass"] = False
            except Exception as e:
                logger.warning("Judge failed for %s: %s", qid, e)
                q_result["judge_scores"] = {"error": str(e)}

        except Exception as e:
            latency_ms = int((time.time() - start) * 1000)
            q_result = {
                "id": qid,
                "question": question,
                "expected_route": expected_route,
                "actual_route": "error",
                "route_correct": False,
                "answer": f"Error: {e}",
                "latency_ms": latency_ms,
                "pass": False,
                "error": str(e),
            }

        return q_result

    def _run_judge(
        self,
        result: dict,
        question: str,
        route: str,
    ) -> dict[str, float]:
        """Run LLM-as-Judge on a result."""
        if route == "sql" and result.get("sql_result"):
            evals = self.judge.evaluate_sql_response(
                question=question,
                sql=result["sql_result"].get("sql", ""),
                query_result=result["sql_result"].get("result", {}),
                explanation=result.get("answer", ""),
            )
        elif route == "rag" and result.get("rag_result"):
            rag_res = result["rag_result"]
            context = "\n".join(
                s.get("text", "") for s in rag_res.get("sources", [])
            )
            evals = self.judge.evaluate_rag_response(
                question=question,
                answer=result.get("answer", ""),
                context=context,
                context_chunks=rag_res.get("sources", []),
            )
        else:
            return {}

        return {k: v.score for k, v in evals.items()}

    def _compute_summary(self, questions: list[dict]) -> dict[str, Any]:
        """Compute aggregate metrics from all question results."""
        sql_questions = [q for q in questions if q.get("actual_route") == "sql"]
        rag_questions = [q for q in questions if q.get("actual_route") == "rag"]

        def avg_score(qs, metric):
            scores = [
                q["judge_scores"].get(metric, 0)
                for q in qs
                if isinstance(q.get("judge_scores"), dict)
                and metric in q["judge_scores"]
            ]
            return round(sum(scores) / len(scores), 3) if scores else 0

        latencies = [q["latency_ms"] for q in questions]
        latencies.sort()
        p95_idx = int(len(latencies) * 0.95) if latencies else 0

        return {
            "total_questions": len(questions),
            "passed": sum(1 for q in questions if q["pass"]),
            "failed": sum(1 for q in questions if not q["pass"]),
            "routing_accuracy": (
                sum(1 for q in questions if q.get("route_correct"))
                / len(questions)
                if questions
                else 0
            ),
            "sql_avg_faithfulness": avg_score(sql_questions, "faithfulness"),
            "rag_avg_faithfulness": avg_score(rag_questions, "faithfulness"),
            "overall_latency_p95_ms": latencies[p95_idx] if latencies else 0,
            "avg_latency_ms": (
                round(sum(latencies) / len(latencies)) if latencies else 0
            ),
        }

    def _write_json_report(self, results: dict, output_dir: Path) -> None:
        """Write evaluation results as JSON."""
        path = output_dir / "latest_eval.json"
        with open(path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        logger.info("JSON report written to %s", path)

    def _write_markdown_report(self, results: dict, output_dir: Path) -> None:
        """Write evaluation results as Markdown."""
        path = output_dir / "latest_eval.md"
        summary = results["summary"]

        lines = [
            "# RTV Multi-Agent System -- Evaluation Report",
            "",
            f"**Run ID:** {results['eval_run_id']}",
            f"**Timestamp:** {results['timestamp']}",
            f"**Overall:** {'PASS' if results.get('overall_pass') else 'FAIL'}",
            "",
            "## Summary",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Questions Evaluated | {summary['total_questions']} |",
            f"| Passed | {summary['passed']} |",
            f"| Failed | {summary['failed']} |",
            f"| Routing Accuracy | {summary['routing_accuracy']:.0%} |",
            f"| SQL Avg Faithfulness | {summary['sql_avg_faithfulness']:.3f} |",
            f"| RAG Avg Faithfulness | {summary['rag_avg_faithfulness']:.3f} |",
            f"| Latency P95 | {summary['overall_latency_p95_ms']}ms |",
            "",
            "## Per-Question Results",
            "",
            "| ID | Question | Route | Correct | Latency | Pass |",
            "|----|----------|-------|---------|---------|------|",
        ]

        for q in results["questions"]:
            route_mark = "Y" if q.get("route_correct") else "N"
            pass_mark = "Y" if q["pass"] else "N"
            lines.append(
                f"| {q['id']} | {q['question'][:50]}... | "
                f"{q.get('actual_route', '?')} | {route_mark} | "
                f"{q['latency_ms']}ms | {pass_mark} |"
            )

        lines.extend(["", "---", "Generated by RTV Evaluation Harness"])

        with open(path, "w") as f:
            f.write("\n".join(lines))
        logger.info("Markdown report written to %s", path)


def main():
    """CLI entry point for running the evaluation harness."""
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    from src.agents.sql_agent import SQLAgent
    from src.agents.rag_agent import RAGAgent
    from src.orchestrator.router import MultiAgentOrchestrator
    from src.evaluation.judge import LLMJudge

    logger.info("Initializing system for evaluation...")
    orchestrator = MultiAgentOrchestrator()
    orchestrator.sql_agent.db.ensure_loaded()

    try:
        orchestrator.rag_agent.initialize()
    except FileNotFoundError:
        logger.warning("Agriculture Handbook not found -- RAG questions will fail")

    judge = LLMJudge()
    runner = EvaluationRunner(orchestrator, judge)

    results = runner.run_all()

    if not results.get("overall_pass"):
        logger.error("EVALUATION FAILED -- some metrics below threshold")
        sys.exit(1)

    logger.info("All evaluations passed.")


if __name__ == "__main__":
    main()
