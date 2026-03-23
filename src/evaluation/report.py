"""
Evaluation report generator -- Markdown + JSON output.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def generate_markdown_report(results: dict[str, Any]) -> str:
    """Generate a Markdown evaluation report."""
    lines = [
        "# RTV Multi-Agent System -- Evaluation Report",
        f"Generated: {datetime.now().isoformat()[:19]}",
        "",
        "## Summary",
        "",
    ]

    summary = results.get("summary", {})
    lines.append(f"Total Questions Evaluated: {summary.get('total_questions', 0)}")
    lines.append("")

    # SQL scores
    lines.append("### SQL Agent Scores")
    lines.append("")
    lines.append("| Metric | Score |")
    lines.append("|--------|-------|")
    for k, v in summary.get("sql_avg_scores", {}).items():
        status = "PASS" if v >= 0.7 else "FAIL"
        lines.append(f"| {k} | {v:.3f} ({status}) |")
    lines.append("")

    # RAG scores
    lines.append("### RAG Agent Scores")
    lines.append("")
    lines.append("| Metric | Score |")
    lines.append("|--------|-------|")
    for k, v in summary.get("rag_avg_scores", {}).items():
        status = "PASS" if v >= 0.7 else "FAIL"
        lines.append(f"| {k} | {v:.3f} ({status}) |")
    lines.append("")

    # Detailed results
    lines.append("## SQL Questions")
    lines.append("")
    for q in results.get("sql_questions", []):
        lines.append(f"### {q['question']}")
        lines.append(f"- **SQL**: `{q.get('sql', 'N/A')[:100]}`")
        lines.append(f"- **Latency**: {q.get('latency_ms', 0):.0f}ms")
        lines.append(f"- **Scores**: {q.get('scores', {})}")
        lines.append(f"- **Answer**: {q.get('answer', '')[:300]}")
        lines.append("")

    lines.append("## RAG Questions")
    lines.append("")
    for q in results.get("rag_questions", []):
        lines.append(f"### {q['question']}")
        lines.append(f"- **Sources**: {q.get('source_count', 0)} chunks")
        lines.append(f"- **Latency**: {q.get('latency_ms', 0):.0f}ms")
        lines.append(f"- **Scores**: {q.get('scores', {})}")
        lines.append(f"- **Answer**: {q.get('answer', '')[:300]}")
        lines.append("")

    lines.append("## Hybrid Questions")
    lines.append("")
    for q in results.get("hybrid_questions", []):
        lines.append(f"### {q['question']}")
        lines.append(f"- **Route**: {q.get('route', 'N/A')}")
        lines.append(f"- **Latency**: {q.get('latency_ms', 0):.0f}ms")
        lines.append(f"- **Answer**: {q.get('answer', '')[:300]}")
        lines.append("")

    return "\n".join(lines)


def save_report(results: dict[str, Any]) -> tuple[Path, Path]:
    """Save evaluation results as JSON and Markdown.

    Returns:
        (json_path, markdown_path)
    """
    output_dir = PROJECT_ROOT / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "evaluation_results.json"
    md_path = output_dir / "evaluation_report.md"

    with open(json_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    md_content = generate_markdown_report(results)
    with open(md_path, "w") as f:
        f.write(md_content)

    return json_path, md_path
