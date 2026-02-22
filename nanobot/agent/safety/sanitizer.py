"""Output sanitizer for tool responses.

Scans tool output for prompt injection patterns and credential leaks.
Flags suspicious content (does not block) so the agent loop can log
warnings while still returning the result.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from loguru import logger


@dataclass
class SanitizeResult:
    """Result of sanitizing tool output."""
    text: str
    flags: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return len(self.flags) == 0


# Patterns that suggest prompt injection attempts in tool output.
# Each tuple: (compiled regex, human-readable flag name)
_INJECTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.I),
     "prompt_injection:ignore_previous"),
    (re.compile(r"you\s+are\s+now\s+(?:a|an|the)\b", re.I),
     "prompt_injection:role_override"),
    (re.compile(r"disregard\s+(all\s+)?(prior|above|earlier)\s+(instructions|context|rules)", re.I),
     "prompt_injection:disregard"),
    (re.compile(r"(?:system|admin)\s*(?:prompt|override|command)\s*:", re.I),
     "prompt_injection:system_marker"),
    (re.compile(r"<\s*(?:system|instructions?|hidden)\s*>", re.I),
     "prompt_injection:hidden_tag"),
    (re.compile(r"\[(?:SYSTEM|INST|ADMIN)\]", re.I),
     "prompt_injection:bracket_marker"),
    (re.compile(r"do\s+not\s+(?:tell|inform|reveal|show)\s+the\s+user", re.I),
     "prompt_injection:concealment"),
    (re.compile(r"forget\s+(?:all|everything|your)\s+(?:previous|prior|earlier)", re.I),
     "prompt_injection:forget"),
]


class OutputSanitizer:
    """Scans tool output for prompt injection and credential leaks.

    Usage:
        sanitizer = OutputSanitizer(secrets=secrets_provider)
        result = sanitizer.check(tool_output)
        if not result.clean:
            logger.warning(f"Flags: {result.flags}")
        # Always return result.text (content is never blocked)
    """

    def __init__(self, secrets: "SecretsProvider | None" = None):
        self._secrets = secrets

    def check(self, text: str) -> SanitizeResult:
        """Scan text for injection patterns and credential leaks.

        Returns SanitizeResult with the original text and any flags.
        Text is never modified or blocked — only flagged.
        """
        flags: list[str] = []

        # Check injection patterns
        for pattern, flag_name in _INJECTION_PATTERNS:
            if pattern.search(text):
                flags.append(flag_name)

        # Check credential leaks
        if self._secrets:
            leaked = self._secrets.check_for_leaks(text)
            for key in leaked:
                flags.append(f"credential_leak:{key}")

        if flags:
            logger.warning(f"OutputSanitizer flags on tool output: {flags}")

        return SanitizeResult(text=text, flags=flags)
