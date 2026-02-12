"""Copilot heartbeat service: proactive assistant driven by heartbeat.md."""

from __future__ import annotations

import asyncio
import datetime
import re
import time
from pathlib import Path
from typing import Callable, Awaitable

import aiosqlite
from loguru import logger


class CopilotHeartbeatService:
    """Proactive assistant that executes tasks from heartbeat.md on a schedule.

    Runs during active hours only (default 7am-10pm).
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
    ):
        self._docs_dir = Path(copilot_docs_dir)
        self._execute_fn = execute_fn
        self._deliver = deliver_fn
        self._channel = delivery_channel
        self._chat_id = delivery_chat_id
        self._db_path = db_path
        self._interval = interval_s
        self._active_hours = active_hours

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
        """Execute one heartbeat cycle."""
        now = datetime.datetime.now()
        if not (self._active_hours[0] <= now.hour < self._active_hours[1]):
            return  # Outside active hours

        heartbeat_path = self._docs_dir / "heartbeat.md"
        if not heartbeat_path.exists():
            return

        tasks, standing_instructions = self._parse_heartbeat_md(heartbeat_path)
        if not tasks:
            return

        start = time.time()
        results = []

        for task_prompt in tasks:
            if not self._execute_fn:
                break
            try:
                full_prompt = task_prompt
                if standing_instructions:
                    full_prompt = f"{standing_instructions}\n\nTask: {task_prompt}"
                result = await self._execute_fn(full_prompt)
                if result and result.strip():
                    results.append(result)
            except Exception as e:
                logger.warning(f"Heartbeat task failed: {e}")

        duration_ms = int((time.time() - start) * 1000)

        # Log to DB
        await self._log(len(tasks), len(results), duration_ms)

        # Deliver summary if there are noteworthy results
        if results and self._deliver and self._chat_id:
            summary = "Heartbeat Update:\n" + "\n".join(
                f"- {r[:200]}" for r in results[:5]
            )
            try:
                await self._deliver(self._channel, self._chat_id, summary)
            except Exception as e:
                logger.warning(f"Heartbeat delivery failed: {e}")

    @staticmethod
    def _parse_heartbeat_md(path: Path) -> tuple[list[str], str]:
        """Parse heartbeat.md into (tasks, standing_instructions)."""
        content = path.read_text(encoding="utf-8")

        # Extract unchecked tasks
        tasks = re.findall(r"- \[ \] (.+)", content)

        # Extract standing instructions section
        standing = ""
        match = re.search(r"# Standing Instructions\n(.*?)(?:\n#|\Z)", content, re.DOTALL)
        if match:
            standing = match.group(1).strip()

        return tasks, standing

    async def _log(self, checked: int, with_results: int, duration_ms: int) -> None:
        """Log heartbeat run to database."""
        if not self._db_path:
            return
        try:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    """INSERT INTO heartbeat_log
                       (tasks_checked, tasks_with_results, duration_ms)
                       VALUES (?, ?, ?)""",
                    (checked, with_results, duration_ms),
                )
                await db.commit()
        except Exception as e:
            logger.warning(f"Heartbeat log failed: {e}")
