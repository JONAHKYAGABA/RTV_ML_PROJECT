"""
Typed exception hierarchy for the RTV ML system.

Every failure mode has a defined fallback response at the appropriate tier.
Users never see raw exception messages.
"""

from __future__ import annotations


class RTVBaseError(Exception):
    """Base exception for the RTV ML system."""

    def __init__(self, message: str, user_message: str | None = None) -> None:
        super().__init__(message)
        self.user_message = user_message or "An unexpected error occurred. Please try again."


# --- SQL Agent Errors ---

class SQLGenerationError(RTVBaseError):
    """LLM failed to generate valid SQL."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            user_message="Unable to generate a valid query. Try rephrasing your question.",
        )


class SQLValidationError(RTVBaseError):
    """Generated SQL failed syntax or safety validation."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            user_message="The generated query could not be validated. Please try a different question.",
        )


class SQLExecutionError(RTVBaseError):
    """SQL query execution failed."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            user_message="Query execution failed. The question may be too complex.",
        )


# --- RAG Pipeline Errors ---

class RAGRetrievalError(RTVBaseError):
    """Vector store retrieval failed."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            user_message="Knowledge base temporarily offline. Please try again later.",
        )


class RAGGenerationError(RTVBaseError):
    """RAG answer generation failed."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            user_message="Unable to generate an answer from the handbook. Please try again.",
        )


# --- Orchestration Errors ---

class RoutingError(RTVBaseError):
    """Intent classification / routing failed."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            user_message="Unable to determine the best way to answer. Running both agents.",
        )


# --- Security ---

class InputSanitizationError(RTVBaseError):
    """Potential prompt injection or malicious input detected."""

    def __init__(self, message: str = "Blocked input") -> None:
        super().__init__(
            message,
            user_message="Your input was blocked for security reasons. Please rephrase.",
        )
