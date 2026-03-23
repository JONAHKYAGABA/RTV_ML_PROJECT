"""
Observability integrations: LangSmith + Weights & Biases.

LangSmith: Automatic tracing of all LangChain/LangGraph calls.
W&B: Experiment tracking for evaluation runs, metric logging, and artifact storage.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LangSmith Integration
# ---------------------------------------------------------------------------

def setup_langsmith(
    project_name: str = "rtv-multi-agent-system",
    tracing_enabled: bool = True,
) -> bool:
    """Configure LangSmith tracing for LangChain/LangGraph operations.

    LangSmith automatically traces all LLM calls, chain executions,
    and LangGraph node transitions when LANGCHAIN_TRACING_V2=true.

    Returns True if LangSmith was successfully configured.
    """
    api_key = os.getenv("LANGCHAIN_API_KEY", "")
    if not api_key:
        logger.info(
            "LANGCHAIN_API_KEY not set -- LangSmith tracing disabled. "
            "Set LANGCHAIN_API_KEY to enable experiment tracking."
        )
        return False

    os.environ["LANGCHAIN_TRACING_V2"] = "true" if tracing_enabled else "false"
    os.environ["LANGCHAIN_PROJECT"] = project_name
    os.environ["LANGCHAIN_ENDPOINT"] = os.getenv(
        "LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com"
    )

    logger.info(
        "LangSmith tracing enabled (project=%s, endpoint=%s)",
        project_name,
        os.environ["LANGCHAIN_ENDPOINT"],
    )
    return True


def get_langsmith_client():
    """Return a LangSmith client for programmatic access (e.g., datasets, feedback).

    Returns None if langsmith is not installed or not configured.
    """
    try:
        from langsmith import Client
        api_key = os.getenv("LANGCHAIN_API_KEY")
        if not api_key:
            return None
        return Client()
    except ImportError:
        logger.debug("langsmith package not installed")
        return None


# ---------------------------------------------------------------------------
# Weights & Biases Integration
# ---------------------------------------------------------------------------

_wandb_run = None


def setup_wandb(
    project: str = "rtv-multi-agent-eval",
    entity: str | None = None,
    config: dict[str, Any] | None = None,
    tags: list[str] | None = None,
) -> bool:
    """Initialize a Weights & Biases run for experiment tracking.

    W&B tracks evaluation metrics, model configurations, and artifacts
    across runs for comparison and regression detection.

    Returns True if W&B was successfully initialized.
    """
    global _wandb_run

    api_key = os.getenv("WANDB_API_KEY", "")
    if not api_key:
        logger.info(
            "WANDB_API_KEY not set -- W&B experiment tracking disabled. "
            "Set WANDB_API_KEY to enable."
        )
        return False

    try:
        import wandb

        _wandb_run = wandb.init(
            project=project,
            entity=entity,
            config=config or {},
            tags=tags or ["rtv", "multi-agent", "evaluation"],
            reinit=True,
        )
        logger.info(
            "W&B experiment tracking initialized (project=%s, run=%s)",
            project,
            _wandb_run.name,
        )
        return True
    except ImportError:
        logger.info("wandb package not installed -- experiment tracking disabled")
        return False
    except Exception as e:
        logger.warning("W&B initialization failed: %s", e)
        return False


def log_eval_metrics(metrics: dict[str, float], step: int | None = None) -> None:
    """Log evaluation metrics to W&B."""
    global _wandb_run

    if _wandb_run is None:
        return

    try:
        import wandb
        wandb.log(metrics, step=step)
        logger.debug("Logged %d metrics to W&B", len(metrics))
    except Exception as e:
        logger.warning("Failed to log to W&B: %s", e)


def log_eval_table(
    questions: list[dict[str, Any]],
    table_name: str = "evaluation_results",
) -> None:
    """Log evaluation results as a W&B Table for interactive analysis."""
    global _wandb_run

    if _wandb_run is None:
        return

    try:
        import wandb

        columns = [
            "id", "question", "expected_route", "actual_route",
            "route_correct", "latency_ms", "pass",
        ]

        # Add judge score columns dynamically
        score_cols = set()
        for q in questions:
            if isinstance(q.get("judge_scores"), dict):
                score_cols.update(q["judge_scores"].keys())
        columns.extend(sorted(score_cols))

        table = wandb.Table(columns=columns)
        for q in questions:
            row = [
                q.get("id", ""),
                q.get("question", "")[:100],
                q.get("expected_route", ""),
                q.get("actual_route", ""),
                q.get("route_correct", False),
                q.get("latency_ms", 0),
                q.get("pass", False),
            ]
            for col in sorted(score_cols):
                scores = q.get("judge_scores", {})
                row.append(scores.get(col, 0) if isinstance(scores, dict) else 0)
            table.add_data(*row)

        wandb.log({table_name: table})
        logger.info("Logged evaluation table to W&B (%d rows)", len(questions))
    except Exception as e:
        logger.warning("Failed to log W&B table: %s", e)


def log_artifact(
    file_path: str,
    name: str = "eval-report",
    artifact_type: str = "evaluation",
) -> None:
    """Log a file as a W&B artifact for versioned storage."""
    global _wandb_run

    if _wandb_run is None:
        return

    try:
        import wandb

        artifact = wandb.Artifact(name, type=artifact_type)
        artifact.add_file(file_path)
        _wandb_run.log_artifact(artifact)
        logger.info("Logged artifact '%s' to W&B", name)
    except Exception as e:
        logger.warning("Failed to log W&B artifact: %s", e)


def finish_wandb() -> None:
    """Finalize the W&B run."""
    global _wandb_run

    if _wandb_run is not None:
        try:
            import wandb
            wandb.finish()
            logger.info("W&B run finished")
        except Exception:
            pass
        _wandb_run = None
