"""Health check service: programmatic health checks, alert management."""

from __future__ import annotations

import asyncio
import datetime
import time
from pathlib import Path
from typing import Any, Callable

import aiosqlite
from loguru import logger

from nanobot.copilot import tz as _tz


class HealthCheckService:
    """Programmatic health checker with event-driven news feed.

    Runs during active hours only (default 7am-10pm).
    All checks are purely programmatic (HTTP pings, DB queries, changelog diff).
    No LLM calls — if intelligence is needed, escalate to HeartbeatService
    (reads HEARTBEAT.md) or the dream cycle.

    Events are written to ``heartbeat_events`` table and consumed by
    the context builder at next session start.
    """

    def __init__(
        self,
        copilot_docs_dir: str = "data/copilot",
        deliver_fn: Callable | None = None,
        delivery_channel: str = "whatsapp",
        delivery_chat_id: str = "",
        db_path: str = "",
        interval_s: int = 1800,
        active_hours: tuple[int, int] = (7, 22),
        subagent_manager: Any = None,
        task_manager: Any = None,
        qdrant_url: str = "http://localhost:6333",
        cron_service: Any = None,
        session_manager: Any = None,
        reset_session_fn: Callable | None = None,
        daily_reset_enabled: bool = False,
        daily_reset_hour: int = 6,
        daily_reset_quiet_minutes: int = 60,
        **kwargs,  # Accept and ignore legacy kwargs
    ):
        self._docs_dir = Path(copilot_docs_dir)
        self._deliver = deliver_fn
        self._channel = delivery_channel
        self._chat_id = delivery_chat_id
        self._db_path = db_path
        self._interval = interval_s
        self._active_hours = active_hours
        self._subagent_manager = subagent_manager
        self._task_manager = task_manager
        self._qdrant_url = qdrant_url.rstrip("/")
        self._cron_service = cron_service
        self._session_manager = session_manager
        self._reset_session_fn = reset_session_fn
        self._daily_reset_enabled = daily_reset_enabled
        self._daily_reset_hour = daily_reset_hour
        self._daily_reset_quiet_minutes = daily_reset_quiet_minutes

        self._running = False
        self._task: asyncio.Task | None = None
        self._changelog_path = Path.home() / ".nanobot" / "CHANGELOG.local"
        self._last_changelog_size: int = 0  # Track file size to detect new entries
        self._last_reset_date: str | None = None  # Track daily reset
        self.last_tick_at: datetime.datetime | None = None  # Surfaced in /status

    async def start(self) -> None:
        """Start the health check loop."""
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(
            f"Health check started (interval={self._interval}s, "
            f"active={self._active_hours[0]}-{self._active_hours[1]})"
        )

    def stop(self) -> None:
        """Stop the health check."""
        self._running = False
        if self._task:
            self._task.cancel()

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check tick failed: {e}")
            await asyncio.sleep(self._interval)

    async def _tick(self) -> None:
        """Execute one health check cycle — purely programmatic."""
        now = _tz.local_now()

        start = time.time()
        events: list[dict] = []

        # 1. Programmatic health checks (no LLM)
        qdrant_events = await self._check_qdrant()
        events += qdrant_events

        # Auto-resolve alerts for subsystems that are now healthy
        if not qdrant_events:  # Qdrant healthy
            await self._resolve_alerts("qdrant")
        # Also resolve stale embedding/memory alerts if no new ones in this tick
        await self._resolve_stale_alerts(hours=4)

        # 2. Check local changelog for external changes
        changelog_events = self._check_changelog()
        events += changelog_events

        # 3. Check for unresolved alerts
        events += await self._check_unresolved_alerts()

        # 4. Check cron timer health
        cron_events = await self._check_cron()
        events += cron_events

        # 5. Check stuck subagents/tasks (no LLM)
        stuck = await self._check_stuck_jobs()
        if stuck:
            events.append({
                "type": "task_update",
                "severity": "medium",
                "message": stuck,
            })

        # 6. Daily session reset (consolidate + clear user session)
        reset_events = await self._check_daily_reset()
        events += reset_events

        # 7. Write noteworthy events to DB
        noteworthy = [e for e in events if e]
        if noteworthy:
            await self._write_events(noteworthy)

        duration_ms = int((time.time() - start) * 1000)
        await self._log(len(noteworthy), duration_ms)

        # 8. Deliver to user ONLY if high-severity events exist
        high = [e for e in noteworthy if e.get("severity") == "high"]
        if high and self._deliver and self._chat_id:
            summary = "\n".join(f"- {e['message'][:200]}" for e in high)
            try:
                await self._deliver(self._channel, self._chat_id, f"Alert:\n{summary}")
            except Exception as e:
                logger.warning(f"Health check delivery failed: {e}")

        self.last_tick_at = now

    # --- Cron timer health ---

    async def _check_cron(self) -> list[dict]:
        """Check cron timer task is alive when there are active jobs."""
        if not self._cron_service:
            return []
        try:
            status = self._cron_service.status()
            if not status.get("enabled") or status.get("jobs", 0) == 0:
                return []
            timer_task = self._cron_service._timer_task
            has_next_wake = status.get("next_wake_at_ms") is not None
            if has_next_wake and (timer_task is None or timer_task.done()):
                logger.warning("Cron timer task dead with active jobs — re-arming")
                self._cron_service._arm_timer()
                from nanobot.copilot.alerting.bus import get_alert_bus
                await get_alert_bus().alert(
                    "cron", "high",
                    "Cron timer task found dead with active jobs — re-armed automatically",
                    "timer_dead_rearmed",
                )
                return [{
                    "type": "health_error",
                    "severity": "high",
                    "message": "Cron timer was dead with active jobs — re-armed automatically",
                }]
        except Exception as e:
            logger.warning(f"Cron health check failed: {e}")
        return []

    # --- Daily session reset ---

    async def _check_daily_reset(self) -> list[dict]:
        """Trigger session reset once daily when user is idle."""
        if not self._daily_reset_enabled or not self._reset_session_fn:
            return []
        now = _tz.local_now()
        if now.hour < self._daily_reset_hour:
            return []  # Too early
        today = now.strftime("%Y-%m-%d")
        if self._last_reset_date == today:
            return []  # Already reset today

        # Check idle time via session updated_at
        if self._session_manager and self._chat_id:
            user_key = f"{self._channel}:{self._chat_id}"
            user_session = self._session_manager.get_or_create(user_key)
            if not user_session.messages:
                self._last_reset_date = today
                return []  # Nothing to clear
            if user_session.updated_at:
                idle_minutes = (now.replace(tzinfo=None) - user_session.updated_at).total_seconds() / 60
                if idle_minutes < self._daily_reset_quiet_minutes:
                    return []  # User active, retry next tick

        # Fire the reset (uses same code path as /new)
        user_key = f"{self._channel}:{self._chat_id}"
        try:
            await self._reset_session_fn(user_key)
        except Exception as e:
            logger.error(f"Daily session reset failed: {e}")
            from nanobot.copilot.alerting.bus import get_alert_bus
            await get_alert_bus().alert("health_check", "medium",
                f"Daily session reset failed: {e}", "daily_reset_failed")
            return []

        self._last_reset_date = today
        logger.info(f"Daily reset: session '{user_key}' refreshed")

        # Send brief notification to user
        if self._deliver and self._chat_id:
            try:
                await self._deliver(self._channel, self._chat_id,
                    "Good morning — session refreshed.")
            except Exception:
                pass  # Non-critical

        return [{
            "type": "session_reset",
            "severity": "info",
            "message": f"Daily session reset completed for {user_key}",
        }]

    # --- Local changelog detection ---

    def _check_changelog(self) -> list[dict]:
        """Read new entries from CHANGELOG.local since last check."""
        if not self._changelog_path.exists():
            return []
        try:
            size = self._changelog_path.stat().st_size
            if size <= self._last_changelog_size:
                return []  # No new content
            with open(self._changelog_path, "r") as f:
                f.seek(self._last_changelog_size)
                new_content = f.read().strip()
            self._last_changelog_size = size
            if not new_content:
                return []
            # Filter to actual entries (skip comments)
            lines = [ln for ln in new_content.splitlines() if ln.startswith("[")]
            if not lines:
                return []
            summary = "; ".join(ln[:200] for ln in lines[:5])
            return [{
                "type": "external_change",
                "severity": "info",
                "message": f"Codebase changes detected: {summary}",
            }]
        except Exception as e:
            logger.debug(f"Changelog check failed: {e}")
            return []

    # --- Alert resolution ---

    async def _resolve_alerts(self, subsystem: str) -> None:
        """Resolve all unresolved alerts for a subsystem that is now healthy."""
        if not self._db_path:
            return
        try:
            async with aiosqlite.connect(self._db_path) as db:
                cur = await db.execute(
                    """UPDATE alerts SET resolved_at = CURRENT_TIMESTAMP
                       WHERE subsystem = ? AND resolved_at IS NULL
                       RETURNING id""",
                    (subsystem,),
                )
                resolved = await cur.fetchall()
                if resolved:
                    await db.commit()
                    logger.info(f"Health check: auto-resolved {len(resolved)} alert(s) for {subsystem}")
        except Exception as e:
            logger.debug(f"Alert resolution failed for {subsystem}: {e}")

    async def _resolve_stale_alerts(self, hours: int = 4) -> None:
        """Resolve alerts that haven't recurred in N hours."""
        if not self._db_path:
            return
        try:
            async with aiosqlite.connect(self._db_path) as db:
                cur = await db.execute(
                    """UPDATE alerts SET resolved_at = CURRENT_TIMESTAMP
                       WHERE resolved_at IS NULL
                         AND timestamp < ?
                       RETURNING id""",
                    (_tz.local_datetime_str(offset_hours=-hours),),
                )
                resolved = await cur.fetchall()
                if resolved:
                    await db.commit()
                    logger.info(f"Health check: auto-resolved {len(resolved)} stale alert(s) (>{hours}h)")
        except Exception as e:
            logger.debug(f"Stale alert resolution failed: {e}")

    # --- Programmatic health checks ---

    async def _check_qdrant(self) -> list[dict]:
        """Check Qdrant health via HTTP GET /collections."""
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{self._qdrant_url}/collections",
                method="GET",
            )
            loop = asyncio.get_event_loop()
            resp = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: urllib.request.urlopen(req, timeout=5),
                ),
                timeout=10,
            )
            if resp.status == 200:
                return []  # Healthy — no event
        except Exception as e:
            return [{
                "type": "health_error",
                "severity": "high",
                "message": f"Qdrant unreachable: {e}",
            }]
        return []

    async def _check_unresolved_alerts(self) -> list[dict]:
        """Check alerts table for unresolved high/medium alerts in last 4 hours."""
        if not self._db_path:
            return []
        try:
            async with aiosqlite.connect(self._db_path) as db:
                cur = await db.execute(
                    """SELECT severity, message FROM alerts
                       WHERE timestamp > ?
                         AND severity IN ('high', 'medium')
                         AND resolved_at IS NULL
                         AND message NOT LIKE '%lm_studio%'
                         AND message NOT LIKE '%LM Studio%'
                         AND error_key NOT LIKE 'provider_failed%'
                       ORDER BY timestamp DESC LIMIT 5""",
                    (_tz.local_datetime_str(offset_hours=-4),),
                )
                rows = await cur.fetchall()
                if rows:
                    return [{
                        "type": "alert_summary",
                        "severity": "medium",
                        "message": f"{len(rows)} recent alert(s): "
                        + "; ".join(f"[{r[0]}] {r[1][:80]}" for r in rows[:3]),
                    }]
        except Exception as e:
            logger.debug(f"Alert check failed: {e}")
        return []

    async def _check_stuck_jobs(self) -> str:
        """Check for and handle stuck subagents and tasks. Returns report string."""
        parts: list[str] = []

        if self._subagent_manager:
            try:
                cancelled = await self._subagent_manager.cancel_stuck(threshold_seconds=600)
                if cancelled:
                    parts.append(f"Cancelled {len(cancelled)} stuck subagent(s): {cancelled}")
            except Exception as e:
                logger.warning(f"Stuck subagent check failed: {e}")

        if self._task_manager:
            try:
                failed = await self._task_manager.fail_stuck_tasks(threshold_minutes=30)
                if failed:
                    parts.append(f"Marked {len(failed)} stuck task(s) as failed: {failed}")
            except Exception as e:
                logger.warning(f"Stuck task check failed: {e}")

        return " | ".join(parts) if parts else ""

    # --- Event persistence ---

    async def _write_events(self, events: list[dict]) -> None:
        """Write events to heartbeat_events table."""
        if not self._db_path or not events:
            return
        try:
            async with aiosqlite.connect(self._db_path) as db:
                for ev in events:
                    await db.execute(
                        """INSERT INTO heartbeat_events
                           (event_type, severity, message, source)
                           VALUES (?, ?, ?, ?)""",
                        (
                            ev.get("type", "unknown"),
                            ev.get("severity", "info"),
                            ev.get("message", ""),
                            ev.get("source", "health_check"),
                        ),
                    )
                await db.commit()
        except Exception as e:
            logger.warning(f"Failed to write health check events: {e}")

    async def _log(self, events_count: int, duration_ms: int) -> None:
        """Log health check run to database."""
        if not self._db_path:
            return
        try:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    """INSERT INTO heartbeat_log
                       (tasks_checked, tasks_with_results, duration_ms)
                       VALUES (?, ?, ?)""",
                    (1, events_count, duration_ms),
                )
                await db.commit()
        except Exception as e:
            logger.warning(f"Health check log failed: {e}")
