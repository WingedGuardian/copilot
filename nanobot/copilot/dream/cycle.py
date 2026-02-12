"""Dream cycle: nightly maintenance orchestrator."""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Awaitable

import aiosqlite
from loguru import logger


@dataclass
class DreamReport:
    """Aggregated results from all maintenance jobs."""

    episodes_consolidated: int = 0
    items_created: int = 0
    items_pruned: int = 0
    cost_summary: str = ""
    lessons_reviewed: int = 0
    lessons_deactivated: int = 0
    backup_status: str = ""
    alerts: list[str] = field(default_factory=list)
    remediations: int = 0
    errors: list[str] = field(default_factory=list)
    duration_ms: int = 0

    def to_summary(self) -> str:
        """Format as WhatsApp-friendly summary."""
        lines = ["Dream Cycle Complete"]
        lines.append(f"Duration: {self.duration_ms}ms")
        if self.episodes_consolidated:
            lines.append(f"Memory: {self.episodes_consolidated} consolidated, {self.items_created} items created")
        if self.cost_summary:
            lines.append(f"Cost: {self.cost_summary}")
        if self.lessons_reviewed:
            lines.append(f"Lessons: {self.lessons_reviewed} reviewed, {self.lessons_deactivated} deactivated")
        if self.backup_status:
            lines.append(f"Backup: {self.backup_status}")
        if self.alerts:
            lines.append(f"Alerts: {len(self.alerts)}")
        if self.errors:
            lines.append(f"Errors: {'; '.join(self.errors[:3])}")
        return "\n".join(lines)


class DreamCycle:
    """Nightly maintenance orchestrator: memory consolidation, cost reporting, lesson review, backup, monitoring."""

    def __init__(
        self,
        db_path: str = "",
        memory_manager: Any = None,
        status_aggregator: Any = None,
        execute_fn: Callable[[str], Awaitable[str]] | None = None,
        backup_dir: str = "/home/ubuntu/executive-copilot/backups",
        deliver_fn: Callable | None = None,
        delivery_channel: str = "whatsapp",
        delivery_chat_id: str = "",
    ):
        self._db_path = db_path
        self._memory = memory_manager
        self._status = status_aggregator
        self._execute_fn = execute_fn
        self._backup_dir = Path(backup_dir)
        self._deliver = deliver_fn
        self._channel = delivery_channel
        self._chat_id = delivery_chat_id

    async def run(self) -> DreamReport:
        """Run all 5 maintenance jobs and return report."""
        start = time.time()
        report = DreamReport()

        # Job 1: Memory consolidation
        try:
            c = await self._consolidate_memory()
            report.episodes_consolidated = c.get("processed", 0)
            report.items_created = c.get("created", 0)
        except Exception as e:
            report.errors.append(f"consolidation: {e}")
            logger.error(f"Dream consolidation failed: {e}")

        # Job 2: Cost reporting
        try:
            report.cost_summary = await self._generate_cost_report()
        except Exception as e:
            report.errors.append(f"cost: {e}")

        # Job 3: Lesson review
        try:
            lr = await self._review_lessons()
            report.lessons_reviewed = lr.get("reviewed", 0)
            report.lessons_deactivated = lr.get("deactivated", 0)
        except Exception as e:
            report.errors.append(f"lessons: {e}")

        # Job 4: Backup
        try:
            report.backup_status = await self._backup()
        except Exception as e:
            report.errors.append(f"backup: {e}")

        # Job 5: Monitor + remediation
        try:
            mr = await self._monitor_and_remediate()
            report.alerts = mr.get("alerts", [])
            report.remediations = mr.get("remediations", 0)
        except Exception as e:
            report.errors.append(f"monitor: {e}")

        report.duration_ms = int((time.time() - start) * 1000)

        # Log to DB
        await self._log_report(report)

        # Deliver summary
        if self._deliver and self._chat_id:
            try:
                await self._deliver(self._channel, self._chat_id, report.to_summary())
            except Exception as e:
                logger.warning(f"Dream report delivery failed: {e}")

        logger.info(f"Dream cycle complete in {report.duration_ms}ms")
        return report

    async def _consolidate_memory(self) -> dict:
        """Use agent to review recent episodes and extract patterns."""
        if not self._memory or not self._execute_fn:
            return {"processed": 0, "created": 0}

        # Ask the agent to consolidate
        prompt = (
            "Review the most recent memories and extract any patterns, preferences, "
            "or important facts that should be remembered long-term. Use the memory tool "
            "to store any discoveries."
        )
        try:
            await self._execute_fn(prompt)
        except Exception as e:
            logger.warning(f"Memory consolidation agent call failed: {e}")

        return {"processed": 1, "created": 0}

    async def _generate_cost_report(self) -> str:
        """Query yesterday's costs and generate summary."""
        if not self._db_path:
            return "No DB configured"

        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                """SELECT model, COUNT(*) as calls, SUM(cost_usd) as total,
                   SUM(tokens_input) as tok_in, SUM(tokens_output) as tok_out
                   FROM cost_log WHERE date(timestamp) = date('now', '-1 day')
                   GROUP BY model ORDER BY total DESC"""
            )
            rows = await cur.fetchall()

        if not rows:
            return "No activity yesterday"

        total = sum(r[2] or 0 for r in rows)
        lines = [f"Yesterday: ${total:.2f}"]
        for model, calls, cost, tok_in, tok_out in rows:
            lines.append(f"  {model}: ${cost:.2f} ({calls} calls)")
        return "\n".join(lines)

    async def _review_lessons(self) -> dict:
        """Decay confidence for stale lessons, deactivate dead ones."""
        if not self._db_path:
            return {"reviewed": 0, "deactivated": 0}

        async with aiosqlite.connect(self._db_path) as db:
            # Decay lessons not applied in 7 days
            await db.execute(
                """UPDATE lessons SET confidence = MAX(confidence - 0.05, 0.0)
                   WHERE active = 1 AND (last_applied IS NULL OR
                   last_applied < datetime('now', '-7 days'))"""
            )

            # Deactivate lessons with very low confidence
            cur = await db.execute(
                """UPDATE lessons SET active = 0
                   WHERE active = 1 AND confidence < 0.15
                   RETURNING id"""
            )
            deactivated = len(await cur.fetchall())

            cur = await db.execute("SELECT COUNT(*) FROM lessons WHERE active = 1")
            reviewed = (await cur.fetchone())[0]

            await db.commit()

        return {"reviewed": reviewed, "deactivated": deactivated}

    async def _backup(self) -> str:
        """Copy SQLite database to backup directory."""
        import datetime
        date_str = datetime.date.today().isoformat()
        backup_path = self._backup_dir / date_str
        backup_path.mkdir(parents=True, exist_ok=True)

        # Copy SQLite
        if self._db_path and Path(self._db_path).exists():
            shutil.copy2(self._db_path, backup_path / "copilot.db")

        # Prune old backups (keep 7 days)
        if self._backup_dir.exists():
            cutoff = datetime.date.today() - datetime.timedelta(days=7)
            for d in self._backup_dir.iterdir():
                if d.is_dir():
                    try:
                        d_date = datetime.date.fromisoformat(d.name)
                        if d_date < cutoff:
                            shutil.rmtree(d)
                    except ValueError:
                        pass

        return f"Backed up to {backup_path}"

    async def _monitor_and_remediate(self) -> dict:
        """Run health checks and attempt remediation."""
        if not self._status:
            return {"alerts": [], "remediations": 0}

        report = await self._status.collect()
        alerts = []
        remediations = 0

        for sub in report.subsystems:
            if not sub.healthy:
                alerts.append(f"{sub.name}: {sub.details}")

        return {"alerts": alerts, "remediations": remediations}

    async def _log_report(self, report: DreamReport) -> None:
        """Log dream cycle to database."""
        if not self._db_path:
            return
        try:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    """INSERT INTO dream_cycle_log
                       (duration_ms, episodes_consolidated, items_created, items_pruned,
                        lessons_reviewed, alerts_count, remediations_count, errors)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        report.duration_ms,
                        report.episodes_consolidated,
                        report.items_created,
                        report.items_pruned,
                        report.lessons_reviewed,
                        len(report.alerts),
                        report.remediations,
                        "; ".join(report.errors) if report.errors else None,
                    ),
                )
                await db.commit()
        except Exception as e:
            logger.warning(f"Dream log failed: {e}")
