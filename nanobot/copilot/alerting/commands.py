"""Natural language detection for alert frequency control."""

import re

# Pattern → command type
_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:notify\s+me\s+less|fewer\s+alerts|less\s+notifications)\b", re.I), "less"),
    (re.compile(r"\b(?:notify\s+me\s+more|more\s+alerts|alert\s+me\s+more\s+often)\b", re.I), "more"),
    (re.compile(r"\b(?:mute\s+alerts|silence\s+notifications|quiet\s+mode)\b", re.I), "mute"),
    (re.compile(r"\b(?:unmute\s+alerts|resume\s+notifications)\b", re.I), "unmute"),
    (re.compile(r"\b(?:alert\s+status|notification\s+settings)\b", re.I), "status"),
]


def detect_alert_command(message: str) -> str | None:
    """Return command type ('less', 'more', 'mute', 'unmute', 'status') or None."""
    for pattern, cmd in _PATTERNS:
        if pattern.search(message):
            return cmd
    return None
