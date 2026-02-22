"""ExtendedContextBuilder — wraps nanobot's ContextBuilder with tiered assembly."""

from pathlib import Path
from typing import Any

import aiosqlite
from loguru import logger

from nanobot.agent.context import ContextBuilder
from nanobot.copilot import tz as _tz
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
        memory_manager: Any = None,
    ):
        self._base = base
        self._budget = budget or TokenBudget()
        self._context_budget = context_budget
        self._continuation_threshold = continuation_threshold
        self._memory_manager = memory_manager

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
        memory_context: str | None = None,
        recent_events: str | None = None,
        core_facts: str | None = None,
        situational_briefing: str | None = None,
    ) -> list[dict[str, Any]]:
        """Build messages with tiered context injection.

        ``session_metadata`` is the ``Session.metadata`` dict, expected to
        contain an ``"extractions"`` key with a list of extraction result dicts.
        ``lessons`` is a list of active Lesson objects to inject.
        ``memory_context`` is pre-fetched episodic memory from proactive_recall.
        ``core_facts`` is a pre-fetched block of high-confidence facts.
        ``situational_briefing`` is a pre-built summary of active tasks and spend.
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

        # Identity docs (SOUL, USER, AGENTS, POLICY, CAPABILITIES) are loaded
        # by ContextBuilder via BOOTSTRAP_FILES — no separate injection needed.

        # Inject heartbeat events (news feed from background monitoring)
        if recent_events:
            self._inject_into_system(messages, recent_events)

        # Inject situational briefing (active tasks, pending questions, spend)
        if situational_briefing:
            self._inject_into_system(messages, situational_briefing)

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

        # Inject core facts (high-confidence structured items)
        if core_facts:
            self._inject_into_system(messages, core_facts)

        # Inject proactive episodic memory (cross-session recall)
        if memory_context:
            self._inject_into_system(messages, memory_context)

        # Orientation hint when context may be incomplete (< 3 exchanges)
        real_history = [m for m in history if m.get("role") in ("user", "assistant")]
        if 0 < len(real_history) < 6:
            self._inject_into_system(
                messages,
                "Note: You may be continuing a prior conversation. "
                "Use recall_messages to review recent exchanges if needed.",
            )

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

    @staticmethod
    async def build_situational_briefing(db_path: str) -> str:
        """Build a concise situational briefing from the task queue and spend.

        Pure SQL — no LLM call.  Returns ``""`` when there is nothing to report.
        """
        try:
            active_tasks: list[dict] = []
            awaiting: list[dict] = []
            completed_24h = 0
            daily_spend = 0.0

            async with aiosqlite.connect(Path(db_path)) as db:
                db.row_factory = aiosqlite.Row

                # 1. Active / awaiting / pending tasks (limit 5)
                try:
                    rows = await db.execute_fetchall(
                        "SELECT id, title, status, priority FROM tasks "
                        "WHERE status IN ('active','awaiting','pending','planning') "
                        "ORDER BY priority ASC, created_at DESC LIMIT 5"
                    )
                    active_tasks = [dict(r) for r in rows] if rows else []
                except Exception:
                    pass

                # 2. Tasks with pending questions
                try:
                    rows = await db.execute_fetchall(
                        "SELECT id, title, pending_questions FROM tasks "
                        "WHERE pending_questions IS NOT NULL AND status = 'awaiting' "
                        "LIMIT 3"
                    )
                    awaiting = [dict(r) for r in rows] if rows else []
                except Exception:
                    pass

                # 3. Completions in last 24h
                try:
                    cur = await db.execute(
                        "SELECT COUNT(*) FROM tasks "
                        "WHERE status = 'completed' "
                        "AND updated_at > ?",
                        (_tz.local_datetime_str(offset_hours=-24),),
                    )
                    completed_24h = (await cur.fetchone())[0]
                except Exception:
                    pass

                # 4. Today's spend
                try:
                    cur = await db.execute(
                        "SELECT COALESCE(SUM(cost_usd), 0) FROM cost_log "
                        "WHERE date(timestamp) = ?",
                        (_tz.local_date_str(),),
                    )
                    daily_spend = (await cur.fetchone())[0]
                except Exception:
                    pass

            # Format only if there's something to say
            if not active_tasks and not awaiting and not completed_24h and not daily_spend:
                return ""

            parts: list[str] = ["## Current Situation\n"]

            if active_tasks:
                parts.append("**Active tasks:**")
                for t in active_tasks:
                    parts.append(f"- [{t['status']}] {t['title'][:80]} (id: {t['id'][:8]})")

            if awaiting:
                parts.append("\n**Awaiting your input:**")
                for t in awaiting:
                    q = (t["pending_questions"] or "")[:120]
                    parts.append(f"- {t['title'][:60]}: {q}")

            summary: list[str] = []
            if completed_24h:
                summary.append(f"{completed_24h} task(s) completed in last 24h")
            if daily_spend:
                summary.append(f"Today's LLM spend: ${daily_spend:.4f}")
            if summary:
                parts.append("\n" + " | ".join(summary))

            return "\n".join(parts)
        except Exception as e:
            logger.debug(f"Situational briefing failed: {e}")
            return ""

    @staticmethod
    def _inject_into_system(
        messages: list[dict[str, Any]], extra: str
    ) -> None:
        """Append *extra* to the system message content."""
        for msg in messages:
            if msg.get("role") == "system":
                msg["content"] = msg["content"] + "\n\n---\n\n" + extra
                return
