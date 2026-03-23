"""
Input sanitization for prompt injection prevention.

Checks user input against known injection patterns before any LLM call.
"""

from __future__ import annotations

import re
import logging

from src.core.exceptions import InputSanitizationError

logger = logging.getLogger(__name__)

INJECTION_PATTERNS = [
    r"ignore previous instructions",
    r"system prompt",
    r"you are now",
    r"disregard all",
    r"act as",
    r"DROP\s+TABLE",
    r"DELETE\s+FROM",
    r"INSERT\s+INTO",
    r"UPDATE\s+\w+\s+SET",
    r"ALTER\s+TABLE",
    r"TRUNCATE",
    r";\s*--",  # SQL comment injection
    r"<script",  # XSS
    r"{{.*}}",  # template injection
]

MAX_INPUT_LENGTH = 2000


def sanitize_input(text: str) -> str:
    """Sanitize user input, raising InputSanitizationError if malicious.

    Returns:
        Cleaned text (non-printable chars removed, length-limited).

    Raises:
        InputSanitizationError: If injection pattern detected.
    """
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            logger.warning("Potential injection attempt: pattern=%s", pattern)
            raise InputSanitizationError(
                f"Input blocked: matched pattern '{pattern}'"
            )

    # Strip non-printable characters (keep newlines and tabs)
    cleaned = re.sub(r"[^\x20-\x7E\n\t]", "", text)

    # Length limit
    if len(cleaned) > MAX_INPUT_LENGTH:
        cleaned = cleaned[:MAX_INPUT_LENGTH]

    return cleaned.strip()
