"""ExtendedContextBuilder — wraps nanobot's ContextBuilder with tiered assembly."""

import time
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.agent.context import ContextBuilder
from nanobot.copilot.context.budget import TokenBudget


class ExtendedContextBuilder:
    """Wraps ``ContextBuilder`` and adds tiered context assembly.

    Tier 1: Last 2-3 exchanges verbatim (always included).
    Tier 2: Structured extractions from background SLM — facts, decisions,
            constraints formatted as a briefing block.
    Tier 3: Session summaries from previous sessions (Phase 4).

    Delegates ``add_tool_result`` and ``add_assistant_message`` directly to the
    wrapped builder so the agent loop sees the same interface.
    """

    def __init__(
        self,
        base: ContextBuilder,
        budget: TokenBudget | None = None,
        context_budget: int = 1500,
        continuation_threshold: float = 0.70,
        copilot_docs_dir: str | None = None,
        memory_manager: Any = None,
    ):
        self._base = base
        self._budget = budget or TokenBudget()
        self._context_budget = context_budget
        self._continuation_threshold = continuation_threshold
        self._docs_dir = Path(copilot_docs_dir) if copilot_docs_dir else None
        self._memory_manager = memory_manager

        # Identity doc cache
        self._identity_cache: str = ""
        self._identity_cache_ts: float = 0.0
        self._identity_cache_ttl: float = 60.0  # 60s

        # Expose attributes that external code may access
        self.workspace = base.workspace
        self.memory = base.memory
        self.skills = base.skills

    # ----- Delegated methods (unchanged interface) -----

    def add_tool_result(
        self,
        messages: list[dict[str, Any]],
        tool_call_id: str,
        tool_name: str,
        result: str,
    ) -> list[dict[str, Any]]:
        return self._base.add_tool_result(messages, tool_call_id, tool_name, result)

    def add_assistant_message(
        self,
        messages: list[dict[str, Any]],
        content: str | None,
        tool_calls: list[dict[str, Any]] | None = None,
        reasoning_content: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._base.add_assistant_message(
            messages, content, tool_calls, reasoning_content=reasoning_content
        )

    # ----- Extended build_messages -----

    def build_messages(
        self,
        history: list[dict[str, Any]],
        current_message: str,
        skill_names: list[str] | None = None,
        media: list[str] | None = None,
        channel: str | None = None,
        chat_id: str | None = None,
        session_metadata: dict[str, Any] | None = None,
        lessons: list | None = None,
    ) -> list[dict[str, Any]]:
        """Build messages with tiered context injection.

        ``session_metadata`` is the ``Session.metadata`` dict, expected to
        contain an ``"extractions"`` key with a list of extraction result dicts.
        ``lessons`` is a list of active Lesson objects to inject.
        """
        # Start from the base builder's output
        messages = self._base.build_messages(
            history=history,
            current_message=current_message,
            skill_names=skill_names,
            media=media,
            channel=channel,
            chat_id=chat_id,
            session_metadata=session_metadata,
        )

        # Inject identity docs (soul.md, user.md, agents.md)
        identity_docs = self._load_identity_docs()
        if identity_docs:
            self._inject_into_system(messages, identity_docs)

        # Inject Tier 2: structured extractions into system prompt
        if session_metadata:
            briefing = self._format_extractions(session_metadata)
            if briefing:
                self._inject_into_system(messages, briefing)

        # Inject active lessons
        if lessons:
            from nanobot.copilot.metacognition.lessons import LessonManager
            lesson_block = LessonManager.format_for_injection(lessons)
            if lesson_block:
                self._inject_into_system(messages, lesson_block)

        return messages

    def needs_continuation(
        self, messages: list[dict[str, Any]], model: str
    ) -> bool:
        """Check if context needs to be rebuilt."""
        return self._budget.needs_continuation(
            messages, model, self._continuation_threshold
        )

    def rebuild_from_extractions(
        self,
        session: Any,  # Session object
        current_message: str,
        channel: str | None = None,
        chat_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Rebuild context from Tier 2 extractions + last 2 exchanges.

        Called when ``needs_continuation()`` returns True.
        """
        # Keep only last 2 exchanges (4 messages: user+assistant pairs)
        recent = session.get_history(max_messages=4)

        messages = self.build_messages(
            history=recent,
            current_message=current_message,
            channel=channel,
            chat_id=chat_id,
            session_metadata=session.metadata,
        )

        logger.info("Context refreshed — rebuilt from extractions + last 2 exchanges")
        return messages

    # ----- Internal helpers -----

    def _format_extractions(self, metadata: dict[str, Any]) -> str:
        """Format stored extractions as a concise briefing block."""
        extractions = metadata.get("extractions", [])
        if not extractions:
            return ""

        # Use the most recent extractions, staying within budget
        parts: list[str] = []
        tokens_used = 0

        for ext in reversed(extractions):
            lines: list[str] = []
            for fact in ext.get("facts", []):
                lines.append(f"- Fact: {fact}")
            for decision in ext.get("decisions", []):
                lines.append(f"- Decision: {decision}")
            for constraint in ext.get("constraints", []):
                lines.append(f"- Constraint: {constraint}")
            for entity in ext.get("entities", []):
                lines.append(f"- Ref: {entity}")

            if not lines:
                continue

            block = "\n".join(lines)
            block_tokens = self._budget.count_tokens(block)
            if tokens_used + block_tokens > self._context_budget:
                break
            parts.append(block)
            tokens_used += block_tokens

        if not parts:
            return ""

        parts.reverse()  # Chronological order
        return "## Conversation Context (extracted)\n\n" + "\n".join(parts)

    def _load_identity_docs(self) -> str:
        """Read soul.md, user.md, agents.md from the configured directory.

        Results are cached for 60s to avoid re-reading on every message.
        """
        if self._docs_dir is None or not self._docs_dir.exists():
            return ""

        now = time.time()
        if self._identity_cache and (now - self._identity_cache_ts) < self._identity_cache_ttl:
            return self._identity_cache

        parts: list[str] = []
        for fname in ("soul.md", "user.md", "agents.md", "policy.md"):
            fpath = self._docs_dir / fname
            if fpath.exists():
                try:
                    content = fpath.read_text(encoding="utf-8").strip()
                    if content:
                        parts.append(content)
                except Exception as e:
                    logger.warning(f"Failed to read {fpath}: {e}")

        self._identity_cache = "\n\n---\n\n".join(parts) if parts else ""
        self._identity_cache_ts = now
        return self._identity_cache

    @staticmethod
    def _inject_into_system(
        messages: list[dict[str, Any]], extra: str
    ) -> None:
        """Append *extra* to the system message content."""
        for msg in messages:
            if msg.get("role") == "system":
                msg["content"] = msg["content"] + "\n\n---\n\n" + extra
                return
