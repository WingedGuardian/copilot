"""Copilot heartbeat service: event-driven health monitor + task reviewer."""

from __future__ import annotations

import asyncio
import datetime
import time
from pathlib import Path
from typing import Callable, Awaitable

import aiosqlite
from loguru import logger


class CopilotHeartbeatService:
    """Programmatic health monitor with event-driven news feed.

    Runs during active hours only (default 7am-10pm).
    Health checks are programmatic (HTTP pings, DB queries) — no LLM.
    LLM is only called when pending tasks need review (judgment required).

    Events are written to ``heartbeat_events`` table and consumed by
    the context builder at next session start.
    """

    def __init__(
        self,
        copilot_docs_dir: str = "data/copilot",
        execute_fn: Callable[[str], Awaitable[str]] | None = None,
        deliver_fn: Callable | None = None,
        delivery_channel: str = "whatsapp",
        delivery_chat_id: str = "",
        db_path: str = "",
        interval_s: int = 7200,
        active_hours: tuple[int, int] = (7, 22),
        subagent_manager: "SubagentManager | None" = None,
        task_manager: "TaskManager | None" = None,
        qdrant_url: str = "http://localhost:6333",
        redis_url: str = "redis://localhost:6379/0",
    ):
        self._docs_dir = Path(copilot_docs_dir)
        self._execute_fn = execute_fn
        self._deliver = deliver_fn
        self._channel = delivery_channel
        self._chat_id = delivery_chat_id
        self._db_path = db_path
        self._interval = interval_s
        self._active_hours = active_hours
        self._subagent_manager = subagent_manager
        self._task_manager = task_manager
        self._qdrant_url = qdrant_url.rstrip("/")
        self._redis_url = redis_url

        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the heartbeat loop."""
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(
            f"Copilot heartbeat started (interval={self._interval}s, "
            f"active={self._active_hours[0]}-{self._active_hours[1]})"
        )

    def stop(self) -> None:
        """Stop the heartbeat."""
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
                logger.error(f"Heartbeat tick failed: {e}")
            await asyncio.sleep(self._interval)

    async def _tick(self) -> None:
        """Execute one heartbeat cycle — programmatic checks + conditional LLM."""
        now = datetime.datetime.now()
        if not (self._active_hours[0] <= now.hour < self._active_hours[1]):
            return  # Outside active hours

        start = time.time()
        events: list[dict] = []

        # 1. Programmatic health checks (no LLM)
        events += await self._check_qdrant()
        events += await self._check_redis()

        # 2. Check for unresolved alerts
        events += await self._check_unresolved_alerts()

        # 3. Check stuck subagents/tasks (existing logic, no LLM)
        stuck = await self._check_stuck_jobs()
        if stuck:
            events.append({
                "type": "task_update",
                "severity": "medium",
                "message": stuck,
            })

        # 4. LLM call for task review — ONLY if pending tasks exist
        if self._task_manager and self._execute_fn:
            try:
                pending = await self._task_manager.list_pending()
                if pending:
                    review = await self._execute_fn(
                        "Review these pending tasks. Note anything stuck, "
                        "overdue, or needing attention. Be brief.\n"
                        + "\n".join(f"- {t}" for t in pending[:10])
                    )
                    if review and review.strip():
                        events.append({
                            "type": "review_finding",
                            "severity": "info",
                            "message": review.strip()[:500],
                        })
            except Exception as e:
                logger.warning(f"Heartbeat task review failed: {e}")

        # 5. Write noteworthy events to DB
        noteworthy = [e for e in events if e]
        if noteworthy:
            await self._write_events(noteworthy)

        duration_ms = int((time.time() - start) * 1000)
        await self._log(len(noteworthy), duration_ms)

        # 6. Deliver to user ONLY if high-severity events exist
        high = [e for e in noteworthy if e.get("severity") == "high"]
        if high and self._deliver and self._chat_id:
            summary = "\n".join(f"- {e['message'][:200]}" for e in high)
            try:
                await self._deliver(self._channel, self._chat_id, f"Alert:\n{summary}")
            except Exception as e:
                logger.warning(f"Heartbeat delivery failed: {e}")

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

    async def _check_redis(self) -> list[dict]:
        """Check Redis health via PING."""
        try:
            import socket
            # Parse redis URL for host/port
            url = self._redis_url
            host = "localhost"
            port = 6379
            if "://" in url:
                parts = url.split("://")[1].split("/")[0]
                if ":" in parts:
                    host, port_s = parts.split(":", 1)
                    port = int(port_s)
                else:
                    host = parts

            loop = asyncio.get_event_loop()

            def _ping():
                s = socket.create_connection((host, port), timeout=5)
                try:
                    s.sendall(b"PING\r\n")
                    data = s.recv(64)
                    return b"+PONG" in data
                finally:
                    s.close()

            ok = await asyncio.wait_for(
                loop.run_in_executor(None, _ping),
                timeout=10,
            )
            if ok:
                return []  # Healthy
        except Exception as e:
            return [{
                "type": "health_error",
                "severity": "high",
                "message": f"Redis unreachable: {e}",
            }]
        return [{
            "type": "health_error",
            "severity": "high",
            "message": "Redis PING failed (unexpected response)",
        }]

    async def _check_unresolved_alerts(self) -> list[dict]:
        """Check alerts table for unresolved high/medium alerts in last 4 hours."""
        if not self._db_path:
            return []
        try:
            async with aiosqlite.connect(self._db_path) as db:
                cur = await db.execute(
                    """SELECT severity, message FROM alerts
                       WHERE timestamp > datetime('now', '-4 hours')
                         AND severity IN ('high', 'medium')
                       ORDER BY timestamp DESC LIMIT 5""",
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
                            ev.get("source", "heartbeat"),
                        ),
                    )
                await db.commit()
        except Exception as e:
            logger.warning(f"Failed to write heartbeat events: {e}")

    async def _log(self, events_count: int, duration_ms: int) -> None:
        """Log heartbeat run to database."""
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
            logger.warning(f"Heartbeat log failed: {e}")
