"""Natural language approval parser: regex + optional SLM for ambiguous cases."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ApprovalResponse:
    """Parsed approval response from the user."""

    intent: str  # "approve" / "deny" / "modify" / "unclear"
    confidence: float = 0.0
    reason: str = ""
    modified_args: dict[str, Any] | None = None
    new_rule: str | None = None


# Pre-compiled patterns for fast parsing
_APPROVE_RE = re.compile(
    r"^(yes|yeah|yep|go|do it|approved?|ok|okay|sure|go ahead|go for it|proceed|yea|affirmative|absolutely|definitely)\b",
    re.IGNORECASE,
)
_DENY_RE = re.compile(
    r"^(no|nope|don'?t|deny|denied|stop|cancel|not now|hold|reject|refuse|abort|negative)\b",
    re.IGNORECASE,
)
_MODIFY_RE = re.compile(
    r"(change|modify|update|replace|instead|but with|edit|alter|adjust|use .+ instead)\b",
    re.IGNORECASE,
)
_CANCEL_RE = re.compile(
    r"^(skip|later|cancel|nevermind|never\s*mind|forget it)\b",
    re.IGNORECASE,
)
_RULE_CREATION_RE = re.compile(
    r"(auto.?approve|from now on|always allow|always approve|never ask.*(again|about))",
    re.IGNORECASE,
)


class NLApprovalParser:
    """Parses user messages as approval/denial responses."""

    def __init__(
        self,
        slm_provider: Any = None,
        slm_model: str | None = None,
    ):
        self._slm_provider = slm_provider
        self._slm_model = slm_model

    def parse(self, text: str) -> ApprovalResponse:
        """Parse a user message as an approval response.

        Fast regex path first, then SLM fallback for ambiguous cases.
        """
        text = text.strip()

        # Quick cancel check
        if _CANCEL_RE.match(text):
            return ApprovalResponse(intent="deny", confidence=0.95, reason="User cancelled")

        # Fast path: regex
        result = self._parse_regex(text)
        if result and result.confidence >= 0.7:
            # Check for rule creation in the same message
            rule = self.detect_rule_creation(text)
            if rule:
                result.new_rule = rule
            return result

        # Check for modification request
        if _MODIFY_RE.search(text):
            return ApprovalResponse(
                intent="modify", confidence=0.7, reason=text
            )

        # If we got a low-confidence regex match, return it
        if result:
            return result

        # Fallback: unclear
        return ApprovalResponse(intent="unclear", confidence=0.3, reason=text)

    def detect_rule_creation(self, text: str) -> str | None:
        """Check if the user is trying to create a dynamic approval rule.

        Returns the extracted rule text or None.
        """
        if _RULE_CREATION_RE.search(text):
            return text
        return None

    @staticmethod
    def _parse_regex(text: str) -> ApprovalResponse | None:
        """Regex-based fast path for obvious cases."""
        if _APPROVE_RE.match(text):
            return ApprovalResponse(
                intent="approve", confidence=0.9, reason="Approved via regex match"
            )
        if _DENY_RE.match(text):
            return ApprovalResponse(
                intent="deny", confidence=0.9, reason="Denied via regex match"
            )
        return None
