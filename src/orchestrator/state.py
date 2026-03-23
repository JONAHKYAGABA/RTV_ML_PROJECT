"""
Shared Agent State -- Pydantic models for all agent communication.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SchemaContext(BaseModel):
    """Context package for SQL generation."""
    ddl: str
    column_descriptions: dict[str, str]
    warnings: list[str] = Field(default_factory=list)
    few_shot_examples: list[dict[str, str]] = Field(default_factory=list)


class ValidationResult(BaseModel):
    """SQL validation result."""
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ExecutionResult(BaseModel):
    """SQL execution result."""
    success: bool
    columns: list[str] = Field(default_factory=list)
    rows: list[Any] = Field(default_factory=list)
    row_count: int = 0
    error: str | None = None


class Chunk(BaseModel):
    """A retrieved document chunk."""
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    score: float = 0.0


class JudgeResult(BaseModel):
    """LLM-as-Judge evaluation result."""
    metric: str
    score: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class QueryRewriterOutput(BaseModel):
    """Structured output from the query rewriter."""
    rewritten_question: str
    output_type: Literal["aggregate", "list", "distribution", "comparison"] = "aggregate"
    relevant_columns: list[str] = Field(default_factory=list)
    requires_outlier_handling: bool = False
