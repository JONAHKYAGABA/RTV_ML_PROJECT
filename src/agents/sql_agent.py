"""
Text-to-SQL Agent using LangGraph.

6-node graph:
  Query Rewriter -> Schema Loader -> SQL Generator -> Validator -> Executor -> Explainer

Features:
  - Self-correction loop (up to 3 retries on SQL errors)
  - Schema-aware SQL generation
  - DuckDB-specific SQL dialect
  - Natural language explanation of results
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, TypedDict

import sqlglot
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from config.settings import get_settings
from src.db.duckdb_manager import DuckDBManager
from src.db.schema_context import (
    COLUMN_DESCRIPTIONS,
    DATA_QUALITY_WARNINGS,
    FEW_SHOT_EXAMPLES,
)
from src.core.sanitizer import sanitize_input

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class SQLAgentState(TypedDict, total=False):
    """State passed between LangGraph nodes."""
    original_question: str
    rewritten_question: str
    schema_context: str
    generated_sql: str
    validation_result: dict[str, Any]
    query_result: dict[str, Any]
    explanation: str
    error: str | None
    retry_count: int


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

@dataclass
class SQLAgent:
    """LangGraph-based Text-to-SQL agent for household data queries."""

    db: DuckDBManager = field(default_factory=DuckDBManager)
    _llm: ChatOpenAI | None = field(default=None, init=False, repr=False)
    _graph: Any = field(default=None, init=False, repr=False)

    @property
    def llm(self) -> ChatOpenAI:
        if self._llm is None:
            settings = get_settings()
            self._llm = ChatOpenAI(
                model=settings.llm_model,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
                api_key=settings.openai_api_key,
            )
        return self._llm

    @property
    def graph(self) -> Any:
        if self._graph is None:
            self._graph = self._build_graph()
        return self._graph

    # ------------------------------------------------------------------
    # Node 1: Query Rewriter
    # ------------------------------------------------------------------

    def _rewrite_query(self, state: SQLAgentState) -> SQLAgentState:
        """Rewrite the user question for clarity and SQL-friendliness."""
        question = state["original_question"]

        prompt = f"""You are a query rewriter for a household survey database.
Rewrite the following question to be more precise and SQL-friendly.
Keep the same intent but clarify any ambiguous terms.

Important context:
- "water consumption" is measured in JERRYCANS per day (not liters)
- "farm implements" has extreme outliers (max=30,000) - queries should filter < 100
- "prediction" means whether a household is predicted to hit their income target
- "predicted_income" is the predicted income + production value

Original question: {question}

Rewritten question (just the question, no explanation):"""

        response = self.llm.invoke(prompt)
        state["rewritten_question"] = response.content.strip()
        state["retry_count"] = 0
        logger.info("Rewritten: %s", state["rewritten_question"])
        return state

    # ------------------------------------------------------------------
    # Node 2: Schema Loader
    # ------------------------------------------------------------------

    def _load_schema(self, state: SQLAgentState) -> SQLAgentState:
        """Load the database schema context."""
        self.db.ensure_loaded()
        state["schema_context"] = self.db.get_schema_description()
        return state

    # ------------------------------------------------------------------
    # Node 3: SQL Generator
    # ------------------------------------------------------------------

    def _generate_sql(self, state: SQLAgentState) -> SQLAgentState:
        """Generate DuckDB SQL from the rewritten question."""
        error_context = ""
        if state.get("error"):
            error_context = f"""

PREVIOUS ATTEMPT FAILED with error:
{state['error']}

Previous SQL:
{state.get('generated_sql', 'N/A')}

Fix the SQL to avoid this error.
"""

        # Build few-shot examples section
        few_shots = "\n".join(
            f"Q: {ex['question']}\nSQL: {ex['sql'].strip()}\n"
            for ex in FEW_SHOT_EXAMPLES[:5]
        )

        # Build data quality warnings
        warnings = "\n".join(f"- {w}" for w in DATA_QUALITY_WARNINGS)

        prompt = f"""You are an expert DuckDB SQL generator for the RTV household dataset.

DATABASE SCHEMA:
{state['schema_context']}

DATA QUALITY WARNINGS:
{warnings}

SIMILAR EXAMPLES:
{few_shots}

QUESTION: {state['rewritten_question']}
{error_context}
Think step by step:
1. Which columns answer this question?
2. Do I need GROUP BY, aggregation, or window functions?
3. Are there data quality issues to handle (outliers, nulls, unit confusion)?
4. Write the SQL.

RULES:
1. ONLY generate SELECT statements. No DDL or DML.
2. Use DuckDB SQL dialect (supports PERCENTILE_CONT, LIST, STRUCT, etc.)
3. For farm_implements_owned aggregations, ALWAYS use PERCENTILE_CONT or filter WHERE farm_implements_owned < 100
4. Water consumption is in JERRYCANS (column: average_water_consumed_per_day)
5. Use ROUND() for decimal display.
6. Table name is 'households'.
7. All column names are lowercase.
8. For percentage calculations, use ROUND(COUNT(*) FILTER (WHERE condition) * 100.0 / COUNT(*), 2)
9. LIMIT results to 50 rows max unless counting/aggregating.
10. For CORR() or correlation analysis, compute CORR() over ALL rows (not per-group, which returns NaN). Show overall correlation alongside a per-group breakdown.
11. Crop diversity = sum of boolean crop columns (cassava, maize, ground_nuts, irish_potatoes, sweet_potatoes, perennial_crops_grown_food_banana).

Return ONLY the SQL query, no explanation. Do not wrap in markdown code blocks.
SQL:"""

        response = self.llm.invoke(prompt)
        sql = response.content.strip()

        # Clean up markdown code blocks if present
        sql = re.sub(r"^```(?:sql)?\s*", "", sql)
        sql = re.sub(r"\s*```$", "", sql)
        sql = sql.strip()

        state["generated_sql"] = sql
        logger.info("Generated SQL: %s", sql[:200])
        return state

    # ------------------------------------------------------------------
    # Node 4: Validator
    # ------------------------------------------------------------------

    def _validate_sql(self, state: SQLAgentState) -> SQLAgentState:
        """Validate the generated SQL using sqlglot."""
        sql = state["generated_sql"]
        errors: list[str] = []

        # Check for dangerous operations
        sql_upper = sql.upper().strip()
        for keyword in ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE"]:
            if keyword in sql_upper.split():
                errors.append(f"Dangerous operation detected: {keyword}")

        # Syntax validation with sqlglot
        try:
            sqlglot.parse(sql, dialect="duckdb")
        except sqlglot.errors.ParseError as e:
            errors.append(f"SQL syntax error: {e}")

        state["validation_result"] = {
            "valid": len(errors) == 0,
            "errors": errors,
        }

        if errors:
            logger.warning("SQL validation errors: %s", errors)

        return state

    # ------------------------------------------------------------------
    # Node 5: Executor
    # ------------------------------------------------------------------

    def _execute_sql(self, state: SQLAgentState) -> SQLAgentState:
        """Execute the validated SQL against DuckDB."""
        if not state["validation_result"]["valid"]:
            state["error"] = "; ".join(state["validation_result"]["errors"])
            state["query_result"] = {"success": False, "error": state["error"]}
            return state

        result = self.db.execute_query(state["generated_sql"])
        state["query_result"] = result

        if not result["success"]:
            state["error"] = result["error"]
            logger.warning("Query execution failed: %s", result["error"])
        else:
            state["error"] = None
            logger.info("Query returned %d rows", result["row_count"])

        return state

    # ------------------------------------------------------------------
    # Node 6: Explainer
    # ------------------------------------------------------------------

    def _explain_results(self, state: SQLAgentState) -> SQLAgentState:
        """Generate a natural language explanation of the query results."""
        result = state["query_result"]

        if not result["success"]:
            state["explanation"] = (
                f"I was unable to answer your question due to a query error: {result['error']}"
            )
            return state

        # Format results for the LLM
        columns = result["columns"]
        rows = result["rows"]

        if not rows:
            state["explanation"] = (
                "The query returned no results. This might mean the condition "
                "doesn't match any records in the dataset."
            )
            return state

        # Create a readable table
        table_str = " | ".join(columns) + "\n"
        table_str += "-" * len(table_str) + "\n"
        for row in rows[:20]:  # Limit display
            table_str += " | ".join(str(v) for v in row) + "\n"

        if len(rows) > 20:
            table_str += f"... and {len(rows) - 20} more rows\n"

        prompt = f"""You are a data analyst explaining query results to a non-technical stakeholder.

ORIGINAL QUESTION: {state['original_question']}

SQL QUERY EXECUTED:
{state['generated_sql']}

RESULTS ({result['row_count']} rows):
{table_str}

Provide a clear, concise explanation of the results that directly answers the question.
Include key numbers and insights. If the data reveals interesting patterns, mention them briefly.
Keep the explanation under 200 words.

IMPORTANT CONTEXT:
- Water consumption is measured in JERRYCANS per day (~20 liters each)
- predicted_income represents predicted income + production value
- prediction=true means the household is expected to hit their income target

Explanation:"""

        response = self.llm.invoke(prompt)
        state["explanation"] = response.content.strip()
        return state

    # ------------------------------------------------------------------
    # Graph Construction
    # ------------------------------------------------------------------

    def _should_retry(self, state: SQLAgentState) -> str:
        """Decide whether to retry SQL generation or proceed to explanation."""
        if state.get("error") and state.get("retry_count", 0) < MAX_RETRIES:
            state["retry_count"] = state.get("retry_count", 0) + 1
            return "retry"
        return "explain"

    def _build_graph(self) -> StateGraph:
        """Build the 6-node LangGraph agent."""
        graph = StateGraph(SQLAgentState)

        # Add nodes
        graph.add_node("rewrite", self._rewrite_query)
        graph.add_node("load_schema", self._load_schema)
        graph.add_node("generate_sql", self._generate_sql)
        graph.add_node("validate", self._validate_sql)
        graph.add_node("execute", self._execute_sql)
        graph.add_node("explain", self._explain_results)

        # Define edges
        graph.set_entry_point("rewrite")
        graph.add_edge("rewrite", "load_schema")
        graph.add_edge("load_schema", "generate_sql")
        graph.add_edge("generate_sql", "validate")
        graph.add_edge("validate", "execute")

        # Conditional: retry or explain
        graph.add_conditional_edges(
            "execute",
            self._should_retry,
            {"retry": "generate_sql", "explain": "explain"},
        )
        graph.add_edge("explain", END)

        return graph.compile()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def query(self, question: str) -> dict[str, Any]:
        """Answer a natural language question about the household data.

        Input is sanitized before processing.

        Returns:
            {
                "question": original question,
                "sql": generated SQL,
                "result": query result dict,
                "explanation": natural language answer,
                "retries": number of retry attempts,
            }
        """
        question = sanitize_input(question)

        initial_state: SQLAgentState = {
            "original_question": question,
            "rewritten_question": "",
            "schema_context": "",
            "generated_sql": "",
            "validation_result": {},
            "query_result": {},
            "explanation": "",
            "error": None,
            "retry_count": 0,
        }

        final_state = self.graph.invoke(initial_state)

        return {
            "question": question,
            "rewritten_question": final_state.get("rewritten_question", ""),
            "sql": final_state.get("generated_sql", ""),
            "result": final_state.get("query_result", {}),
            "explanation": final_state.get("explanation", ""),
            "retries": final_state.get("retry_count", 0),
        }
