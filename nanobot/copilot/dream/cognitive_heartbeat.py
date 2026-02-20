"""Cognitive heartbeat — extends upstream HeartbeatService with proactive awareness.

Subclasses HeartbeatService (FM2: upstream stays clean) to add:
- Dream observation context (unacted items from dream_observations)
- Active task awareness (pending/active tasks from task queue)
- Autonomy permission awareness (what can be done autonomously)
- Morning brief (first tick after dream cycle gets reflection context)
- Structured observation output (writes back to dream_observations + heartbeat_events)
"""

from __future__ import annotations

import datetime
import time
from typing import Any

import aiosqlite
from loguru import logger

from nanobot.heartbeat.service import HeartbeatService, _is_heartbeat_empty


class CopilotHeartbeatService(HeartbeatService):
    """Cognitive heartbeat — extends upstream with proactive inner monologue."""

    def __init__(
        self,
        *,
        db_path: str = "",
        task_manager: Any = None,
        dream_cycle: Any = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._db_path = db_path
        self._task_manager = task_manager
        self._dream_cycle = dream_cycle
        self._last_dream_check: float = 0.0  # epoch of last dream reflection check

    async def _tick(self) -> None:
        """Execute a cognitive heartbeat tick.

        Unlike upstream (which skips on empty HEARTBEAT.md), the cognitive
        heartbeat always runs — dream observations and tasks are checked
        regardless of HEARTBEAT.md content.
        """
        self.last_tick_at = datetime.datetime.utcnow()

        # FM4: Skip if dream cycle is running to avoid concurrent LLM calls
        if self._dream_cycle and getattr(self._dream_cycle, "is_running", False):
            logger.debug("Heartbeat: skipping — dream cycle in progress")
            return

        # Gather all context in parallel
        heartbeat_md = self._read_heartbeat_file()
        observations = await self._get_unacted_observations()
        pending_tasks = await self._get_pending_tasks()
        permissions = await self._get_autonomy_permissions()
        active_lessons = await self._get_active_lessons()
        morning_brief = await self._get_morning_brief()

        # Decide if there's anything to process
        has_heartbeat_tasks = not _is_heartbeat_empty(heartbeat_md)
        has_cognitive_context = bool(observations or pending_tasks or morning_brief)

        if not has_heartbeat_tasks and not has_cognitive_context:
            logger.debug("Heartbeat: nothing to process (no tasks, no observations)")
            return

        # Build cognitive prompt
        prompt = self._build_cognitive_prompt(
            heartbeat_md=heartbeat_md if has_heartbeat_tasks else None,
            observations=observations,
            pending_tasks=pending_tasks,
            permissions=permissions,
            active_lessons=active_lessons,
            morning_brief=morning_brief,
        )

        logger.info("Heartbeat: cognitive tick starting...")

        if self.on_heartbeat:
            try:
                response = await self.on_heartbeat(prompt)
                await self._process_response(response)
                logger.info("Heartbeat: cognitive tick complete")
            except Exception as e:
                logger.error(f"Heartbeat execution failed: {e}")
                try:
                    from nanobot.copilot.alerting.bus import get_alert_bus
                    await get_alert_bus().alert(
                        "heartbeat", "medium",
                        f"Cognitive heartbeat failed: {e}",
                        "heartbeat_failed",
                    )
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Context gathering
    # ------------------------------------------------------------------

    async def _get_unacted_observations(self) -> list[dict]:
        """Query dream_observations WHERE acted_on = 0, LIMIT 10."""
        if not self._db_path:
            return []
        try:
            async with aiosqlite.connect(self._db_path) as db:
                db.row_factory = aiosqlite.Row
                cur = await db.execute(
                    """SELECT id, observation_type, content, priority, source
                       FROM dream_observations
                       WHERE acted_on = 0
                         AND (expires_at IS NULL OR expires_at > datetime('now'))
                       ORDER BY
                         CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
                         created_at DESC
                       LIMIT 10"""
                )
                return [dict(r) for r in await cur.fetchall()]
        except Exception as e:
            logger.debug(f"Heartbeat: observation query failed: {e}")
            return []

    async def _get_pending_tasks(self) -> list[str]:
        """Get pending/active/awaiting tasks via TaskManager."""
        if not self._task_manager:
            return []
        try:
            return await self._task_manager.list_pending()
        except Exception as e:
            logger.debug(f"Heartbeat: task query failed: {e}")
            return []

    async def _get_autonomy_permissions(self) -> dict[str, str]:
        """Load autonomy_permissions table → {category: mode}."""
        if not self._db_path:
            return {}
        try:
            async with aiosqlite.connect(self._db_path) as db:
                cur = await db.execute(
                    "SELECT category, mode FROM autonomy_permissions"
                )
                return {row[0]: row[1] for row in await cur.fetchall()}
        except Exception as e:
            logger.debug(f"Heartbeat: autonomy query failed: {e}")
            return {}

    async def _get_active_lessons(self, limit: int = 5) -> list[dict]:
        """Fetch high-confidence active lessons (read-only, no side effects)."""
        if not self._db_path:
            return []
        try:
            async with aiosqlite.connect(self._db_path) as db:
                cur = await db.execute(
                    """SELECT lesson_text, confidence, category
                       FROM lessons
                       WHERE active = 1 AND confidence >= 0.5
                       ORDER BY confidence DESC, applied_count DESC
                       LIMIT ?""",
                    (limit,),
                )
                return [
                    {"text": row[0], "confidence": row[1], "category": row[2]}
                    for row in await cur.fetchall()
                ]
        except Exception as e:
            logger.debug(f"Heartbeat: lesson query failed: {e}")
            return []

    async def _get_morning_brief(self) -> str | None:
        """If first tick since last dream, load reflection_full from most recent dream."""
        if not self._db_path:
            return None
        try:
            async with aiosqlite.connect(self._db_path) as db:
                cur = await db.execute(
                    """SELECT run_at, reflection_full FROM dream_cycle_log
                       WHERE reflection_full IS NOT NULL AND reflection_full != ''
                       ORDER BY run_at DESC LIMIT 1"""
                )
                row = await cur.fetchone()
                if not row:
                    return None

                reflection = row[1]

                # Only show if this dream happened after our last check
                # Use a simple epoch comparison
                if self._last_dream_check == 0.0:
                    # First tick ever — show the brief
                    self._last_dream_check = time.time()
                    return reflection
                else:
                    # Check if dream ran since last check by comparing timestamps
                    cur2 = await db.execute(
                        """SELECT COUNT(*) FROM dream_cycle_log
                           WHERE run_at > datetime('now', '-4 hours')
                             AND reflection_full IS NOT NULL AND reflection_full != ''"""
                    )
                    count = (await cur2.fetchone())[0]
                    if count > 0 and time.time() - self._last_dream_check > 3600:
                        self._last_dream_check = time.time()
                        return reflection

                return None
        except Exception as e:
            logger.debug(f"Heartbeat: morning brief query failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_cognitive_prompt(
        self,
        *,
        heartbeat_md: str | None,
        observations: list[dict],
        pending_tasks: list[str],
        permissions: dict[str, str],
        active_lessons: list[dict],
        morning_brief: str | None,
    ) -> str:
        sections = [
            "You are in your heartbeat cycle. Nobody is talking to you right now. "
            "This is your time to think, observe, and (if appropriate) act."
        ]

        if heartbeat_md:
            sections.append(f"\n## HEARTBEAT.md Tasks\n{heartbeat_md}")

        if observations:
            obs_lines = []
            for o in observations:
                obs_lines.append(
                    f"- [{o.get('priority', 'medium')}] ({o.get('observation_type', '?')}) "
                    f"{o.get('content', '')[:300]}"
                )
            sections.append(
                "\n## Unacted Observations (from dream/previous heartbeats)\n"
                + "\n".join(obs_lines)
            )

        if pending_tasks:
            sections.append(
                "\n## Active Tasks\n" + "\n".join(f"- {t}" for t in pending_tasks[:10])
            )

        if permissions:
            perm_lines = [f"- {cat}: **{mode}**" for cat, mode in sorted(permissions.items())]
            sections.append(
                "\n## Autonomy Permissions\n" + "\n".join(perm_lines)
                + "\n\n*notify* = flag for user. *autonomous* = act independently. *disabled* = skip."
            )

        if active_lessons:
            lesson_lines = []
            for lesson in active_lessons:
                pct = int(lesson.get("confidence", 0.5) * 100)
                cat = lesson.get("category", "general")
                lesson_lines.append(f"- [{pct}%] ({cat}) {lesson.get('text', '')[:200]}")
            sections.append(
                "\n## Active Lessons (hard-won rules — factor these into your thinking)\n"
                + "\n".join(lesson_lines)
            )

        if morning_brief:
            sections.append(
                "\n## Morning Brief (from last dream cycle)\n"
                + morning_brief[:2000]
            )

        sections.append("""
## What you can do
- Execute HEARTBEAT.md tasks as usual
- Write observations (things you notice, patterns, capability gaps)
- Flag something for the user's next conversation
- Mark observations as acted_on if you've addressed them
- Note capability gaps for the dream cycle to process

## Output
If you have HEARTBEAT.md tasks, execute them using your tools as normal.
Then, optionally append a JSON block with any observations:
```json
[
  {"type": "observation", "content": "...", "observation_type": "pattern|capability_gap|risk|proactive_action", "priority": "low|medium|high"},
  {"type": "user_flag", "content": "...", "severity": "info|medium|high"}
]
```
If nothing needs attention beyond HEARTBEAT.md tasks, skip the JSON block entirely.""")

        return "\n".join(sections)

    # ------------------------------------------------------------------
    # Response processing
    # ------------------------------------------------------------------

    async def _process_response(self, response: str) -> None:
        """Parse structured output from heartbeat LLM response, write observations/events."""
        if not response or not self._db_path:
            return

        from nanobot.copilot.dream.cycle import DreamCycle
        parsed = DreamCycle._parse_llm_json(response)

        if not isinstance(parsed, list):
            return  # No structured output, that's fine

        observations = []
        events = []

        for item in parsed:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type", "")

            if item_type == "observation":
                observations.append({
                    "observation_type": item.get("observation_type", "pattern"),
                    "content": item.get("content", "")[:1000],
                    "priority": item.get("priority", "medium"),
                })
            elif item_type == "user_flag":
                events.append({
                    "event_type": "heartbeat_flag",
                    "severity": item.get("severity", "info"),
                    "message": item.get("content", "")[:500],
                    "source": "cognitive_heartbeat",
                })

        # Write observations to dream_observations
        if observations:
            try:
                async with aiosqlite.connect(self._db_path) as db:
                    for obs in observations:
                        await db.execute(
                            """INSERT INTO dream_observations
                               (source, observation_type, content, priority)
                               VALUES (?, ?, ?, ?)""",
                            ("cognitive_heartbeat", obs["observation_type"],
                             obs["content"], obs["priority"]),
                        )
                    await db.commit()
                logger.info(f"Heartbeat: wrote {len(observations)} observations")
            except Exception as e:
                logger.warning(f"Heartbeat: observation write failed: {e}")

        # Write events to heartbeat_events
        if events:
            try:
                async with aiosqlite.connect(self._db_path) as db:
                    for ev in events:
                        await db.execute(
                            """INSERT INTO heartbeat_events
                               (event_type, severity, message, source)
                               VALUES (?, ?, ?, ?)""",
                            (ev["event_type"], ev["severity"],
                             ev["message"], ev["source"]),
                        )
                    await db.commit()
                logger.info(f"Heartbeat: wrote {len(events)} events")
            except Exception as e:
                logger.warning(f"Heartbeat: event write failed: {e}")
