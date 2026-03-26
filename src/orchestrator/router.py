"""
Multi-Agent Orchestrator using LangGraph.

Routes user queries to the appropriate agent (SQL, RAG, or both)
based on intent classification. Handles hybrid queries that need
data from both household statistics and the agriculture handbook.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from config.settings import get_settings
from src.agents.sql_agent import SQLAgent
from src.agents.rag_agent import RAGAgent

logger = logging.getLogger(__name__)


class OrchestratorState(TypedDict, total=False):
    """State for the orchestrator graph."""
    question: str
    route: str  # "sql", "rag", "hybrid"
    sql_result: dict[str, Any]
    rag_result: dict[str, Any]
    final_answer: str
    metadata: dict[str, Any]


@dataclass
class MultiAgentOrchestrator:
    """LangGraph supervisor that routes queries to SQL or RAG agents."""

    sql_agent: SQLAgent = field(default_factory=SQLAgent)
    rag_agent: RAGAgent = field(default_factory=RAGAgent)
    _llm: ChatOpenAI | None = field(default=None, init=False, repr=False)
    _graph: Any = field(default=None, init=False, repr=False)

    @property
    def llm(self) -> ChatOpenAI:
        if self._llm is None:
            settings = get_settings()
            self._llm = ChatOpenAI(
                model=settings.llm_model,
                temperature=0.0,
                max_tokens=1024,
                api_key=settings.openai_api_key,
            )
        return self._llm

    @property
    def graph(self) -> Any:
        if self._graph is None:
            self._graph = self._build_graph()
        return self._graph

    def initialize(self) -> None:
        """Initialize both sub-agents."""
        self.sql_agent.db.ensure_loaded()
        self.rag_agent.initialize()
        logger.info("Orchestrator initialized with SQL + RAG agents")

    # ------------------------------------------------------------------
    # Node: Classifier / Router
    # ------------------------------------------------------------------

    def _classify_intent(self, state: OrchestratorState) -> OrchestratorState:
        """Classify the question intent to determine routing."""
        question = state["question"]

        prompt = f"""You are a query router for a system with two data sources:

1. SQL DATABASE: Contains household survey data for 27,525 households in Uganda.
   - Demographics: district, village, region, household size
   - Agriculture: crops grown (cassava, maize, etc.), land size, farm implements
   - Program: VSLA participation, business participation, evaluation metrics
   - Predictions: predicted income, whether household will hit target
   Good for: statistics, counts, averages, comparisons, rankings, filtering

2. RAG KNOWLEDGE BASE: Contains the RTV Agriculture Handbook covering:
   - Composting methods (pit composting, heap composting)
   - Keyhole garden construction and maintenance
   - Liquid manure preparation
   - Organic pesticide recipes
   - Nursery bed preparation
   - Soil and water conservation techniques
   Good for: how-to questions, best practices, agricultural techniques, procedures

Classify the following question into one of three categories:
- "sql" : Can be answered purely from household data
- "rag" : Can be answered purely from the agriculture handbook
- "hybrid" : Needs both data sources (e.g., "what composting methods are used in districts with high maize production?")

Question: {question}

Respond with ONLY one word: sql, rag, or hybrid"""

        response = self.llm.invoke(prompt)
        route = response.content.strip().lower()

        # Validate route
        if route not in ("sql", "rag", "hybrid"):
            # Default to hybrid if unclear
            route = "hybrid"

        state["route"] = route
        state["metadata"] = {"route": route}
        logger.info("Classified '%s' as: %s", question[:60], route)
        return state

    # ------------------------------------------------------------------
    # Node: SQL Agent
    # ------------------------------------------------------------------

    def _run_sql_agent(self, state: OrchestratorState) -> OrchestratorState:
        """Execute the SQL agent."""
        result = self.sql_agent.query(state["question"])
        state["sql_result"] = result
        return state

    # ------------------------------------------------------------------
    # Node: RAG Agent
    # ------------------------------------------------------------------

    def _run_rag_agent(self, state: OrchestratorState) -> OrchestratorState:
        """Execute the RAG agent."""
        result = self.rag_agent.query(state["question"])
        state["rag_result"] = result
        return state

    # ------------------------------------------------------------------
    # Node: Synthesizer (for hybrid queries)
    # ------------------------------------------------------------------

    def _synthesize(self, state: OrchestratorState) -> OrchestratorState:
        """Synthesize answers from SQL and/or RAG results."""
        route = state["route"]
        question = state["question"]

        if route == "sql":
            sql_result = state.get("sql_result", {})
            state["final_answer"] = sql_result.get("explanation", "No SQL result available.")
            state["metadata"]["sql_query"] = sql_result.get("sql", "")
            return state

        if route == "rag":
            rag_result = state.get("rag_result", {})
            state["final_answer"] = rag_result.get("answer", "No RAG result available.")
            return state

        # Hybrid: combine both results
        sql_result = state.get("sql_result", {})
        rag_result = state.get("rag_result", {})

        sql_explanation = sql_result.get("explanation", "No data available.")
        rag_answer = rag_result.get("answer", "No handbook information available.")

        prompt = f"""You are synthesizing information from two sources to answer a question.

QUESTION: {question}

DATA FROM HOUSEHOLD DATABASE:
{sql_explanation}

INFORMATION FROM AGRICULTURE HANDBOOK:
{rag_answer}

Provide a unified, coherent answer that combines insights from both sources.
Reference which source each piece of information comes from.
Keep the answer under 400 words.

SYNTHESIZED ANSWER:"""

        response = self.llm.invoke(prompt)
        state["final_answer"] = response.content.strip()
        state["metadata"]["sql_query"] = sql_result.get("sql", "")
        return state

    # ------------------------------------------------------------------
    # Routing Logic
    # ------------------------------------------------------------------

    def _route_after_classify(self, state: OrchestratorState) -> str:
        """Determine which agent(s) to invoke."""
        route = state["route"]
        if route == "sql":
            return "sql_agent"
        elif route == "rag":
            return "rag_agent"
        else:
            return "both_agents"

    # ------------------------------------------------------------------
    # Hybrid node: runs both agents sequentially
    # ------------------------------------------------------------------

    def _run_both_agents(self, state: OrchestratorState) -> OrchestratorState:
        """Run both SQL and RAG agents for hybrid queries."""
        state = self._run_sql_agent(state)
        state = self._run_rag_agent(state)
        return state

    # ------------------------------------------------------------------
    # Graph Construction
    # ------------------------------------------------------------------

    def _build_graph(self) -> Any:
        """Build the orchestrator LangGraph."""
        graph = StateGraph(OrchestratorState)

        # Nodes
        graph.add_node("classify", self._classify_intent)
        graph.add_node("sql_agent", self._run_sql_agent)
        graph.add_node("rag_agent", self._run_rag_agent)
        graph.add_node("both_agents", self._run_both_agents)
        graph.add_node("synthesize", self._synthesize)

        # Entry
        graph.set_entry_point("classify")

        # Conditional routing
        graph.add_conditional_edges(
            "classify",
            self._route_after_classify,
            {
                "sql_agent": "sql_agent",
                "rag_agent": "rag_agent",
                "both_agents": "both_agents",
            },
        )

        # All paths lead to synthesize
        graph.add_edge("sql_agent", "synthesize")
        graph.add_edge("rag_agent", "synthesize")
        graph.add_edge("both_agents", "synthesize")
        graph.add_edge("synthesize", END)

        return graph.compile()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def query(self, question: str) -> dict[str, Any]:
        """Route and answer a question using the appropriate agent(s).

        Returns:
            {
                "question": str,
                "answer": str,
                "route": "sql" | "rag" | "hybrid",
                "metadata": dict with additional details,
            }
        """
        initial_state: OrchestratorState = {
            "question": question,
            "route": "",
            "sql_result": {},
            "rag_result": {},
            "final_answer": "",
            "metadata": {},
        }

        final_state = self.graph.invoke(initial_state)

        return {
            "question": question,
            "answer": final_state.get("final_answer", ""),
            "route": final_state.get("route", "unknown"),
            "metadata": final_state.get("metadata", {}),
            "sql_result": final_state.get("sql_result"),
            "rag_result": final_state.get("rag_result"),
        }
