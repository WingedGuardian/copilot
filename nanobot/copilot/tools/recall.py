"""Recall messages tool — lets the LLM "scroll up" in conversation history."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from nanobot.agent.tools.base import Tool

# Same error prefixes used by Session.get_history()
_ERROR_PREFIXES = (
    "I'm having trouble connecting",
    "I'm sorry, the response timed out",
)


class RecallMessagesTool(Tool):
    """Lets the agent scroll up in conversation history on demand."""

    def __init__(self, session_manager):
        self._sessions = session_manager
        self._current_session_key: str = ""

    @property
    def name(self) -> str:
        return "recall_messages"

    @property
    def description(self) -> str:
        return (
            "Scroll up in conversation history. Returns recent messages "
            "you may not have in your current context. Use when you sense "
            "the user is continuing a prior discussion."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "description": "Number of recent messages to retrieve (default 20, max 50)",
                },
            },
        }

    async def execute(self, **kwargs: Any) -> str:
        count = min(int(kwargs.get("count", 20)), 50)

        if not self._current_session_key:
            return "No active session."

        session = self._sessions.get_or_create(self._current_session_key)
        if not session.messages:
            return "No prior messages in this conversation."

        # Filter out error noise, keep real exchanges
        real = [
            m for m in session.messages
            if not (
                m["role"] == "assistant"
                and (
                    m.get("is_error")
                    or any(m["content"].startswith(p) for p in _ERROR_PREFIXES)
                )
            )
        ]

        if not real:
            return "No prior messages in this conversation."

        recent = real[-count:]
        lines = []
        for m in recent:
            ts = ""
            if m.get("timestamp"):
                try:
                    dt = datetime.fromisoformat(m["timestamp"])
                    ts = f"[{dt.strftime('%H:%M')}] "
                except (ValueError, TypeError):
                    pass
            role = m["role"]
            content = m["content"]
            # Truncate long assistant messages
            if role == "assistant" and len(content) > 200:
                content = content[:200] + "..."
            lines.append(f"{ts}{role}: {content}")

        return f"Recent messages ({len(recent)}):\n\n" + "\n".join(lines)
