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
    reflection: str = ""
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
            lines.append(f"Alerts ({len(self.alerts)}):")
            for a in self.alerts[:5]:
                lines.append(f"  - {a}")
        if self.reflection:
            lines.append(f"Reflection: {self.reflection}")
        if self.errors:
            lines.append(f"Errors: {'; '.join(self.errors[:3])}")
        if len(lines) == 2:  # Only header + duration — quiet night
            lines.append("Quiet night. All systems healthy.")
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
        docs_dir: str = "data/copilot",
        emergency_cloud_model: str = "openai/gpt-4o-mini",
    ):
        self._db_path = db_path
        self._memory = memory_manager
        self._status = status_aggregator
        self._execute_fn = execute_fn
        self._backup_dir = Path(backup_dir)
        self._deliver = deliver_fn
        self._channel = delivery_channel
        self._chat_id = delivery_chat_id
        self._docs_dir = docs_dir
        self._emergency_cloud_model = emergency_cloud_model

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

        # Job 6: Reconcile memory stores (Qdrant vs FTS5)
        try:
            reconciled = await self._reconcile_memory_stores()
            if reconciled:
                report.items_pruned += reconciled
        except Exception as e:
            report.errors.append(f"reconcile: {e}")
            logger.error(f"Dream reconcile failed: {e}")

        # Job 7: Cleanup zero vectors
        try:
            cleaned = await self._cleanup_zero_vectors()
            if cleaned:
                report.items_pruned += cleaned
        except Exception as e:
            report.errors.append(f"zero_vectors: {e}")

        # Job 8: Cleanup stale routing preferences (>7 days)
        try:
            await self._cleanup_routing_preferences()
        except Exception as e:
            report.errors.append(f"routing_prefs: {e}")

        # Job 9: MEMORY.md token budget check
        try:
            await self._check_memory_budget()
        except Exception as e:
            report.errors.append(f"memory_budget: {e}")

        # Job 10: Metacognitive self-reflection
        try:
            report.reflection = await self._self_reflect(report)
        except Exception as e:
            report.errors.append(f"reflection: {e}")

        report.duration_ms = int((time.time() - start) * 1000)

        # Log to DB
        await self._log_report(report)

        # Always deliver summary to user
        if self._deliver and self._chat_id:
            try:
                await self._deliver(self._channel, self._chat_id, report.to_summary())
            except Exception as e:
                logger.warning(f"Dream report delivery failed: {e}")
                from nanobot.copilot.alerting.bus import get_alert_bus
                await get_alert_bus().alert("dream", "medium", f"Dream report delivery failed: {e}", "delivery_failed")
        elif self._deliver:
            logger.warning("Dream report ready but no chat_id configured for delivery")

        logger.info(f"Dream cycle complete in {report.duration_ms}ms")
        return report

    async def _consolidate_memory(self) -> dict:
        """Use agent to review recent episodes and extract patterns."""
        if not self._memory or not self._execute_fn:
            return {"processed": 0, "created": 0}

        # Count episodes before consolidation
        before_count = 0
        if self._db_path:
            try:
                async with aiosqlite.connect(self._db_path) as db:
                    cur = await db.execute("SELECT COUNT(*) FROM episodes_content")
                    before_count = (await cur.fetchone())[0]
            except Exception:
                pass  # Table may not exist yet

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

        # Count episodes after to determine actual items created
        after_count = before_count
        if self._db_path:
            try:
                async with aiosqlite.connect(self._db_path) as db:
                    cur = await db.execute("SELECT COUNT(*) FROM episodes_content")
                    after_count = (await cur.fetchone())[0]
            except Exception:
                pass

        created = max(0, after_count - before_count)
        return {"processed": 1, "created": created}

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

        # Copy SQLite (run in executor to avoid blocking the event loop)
        if self._db_path and Path(self._db_path).exists():
            import asyncio

            def _do_backup():
                import sqlite3
                src = sqlite3.connect(self._db_path)
                try:
                    dst = sqlite3.connect(str(backup_path / "copilot.db"))
                    try:
                        src.backup(dst)
                    finally:
                        dst.close()
                finally:
                    src.close()

            await asyncio.get_event_loop().run_in_executor(None, _do_backup)

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

    async def _reconcile_memory_stores(self, max_per_cycle: int = 50) -> int:
        """Reconcile Qdrant vectors with FTS5 index — remove orphans."""
        if not self._memory or not self._db_path:
            return 0

        cleaned = 0
        try:
            async with aiosqlite.connect(self._db_path) as db:
                cur = await db.execute(
                    "SELECT id FROM episodes ORDER BY id DESC LIMIT ?", (max_per_cycle * 2,)
                )
                db_ids = {str(row[0]) for row in await cur.fetchall()}

            if hasattr(self._memory, '_qdrant') and self._memory._qdrant:
                try:
                    result = await self._memory._qdrant.scroll(
                        collection_name="episodes",
                        limit=max_per_cycle,
                        with_payload=False,
                    )
                    points = result[0] if result else []
                    orphan_ids = [p.id for p in points if str(p.id) not in db_ids]
                    if orphan_ids:
                        await self._memory._qdrant.delete(
                            collection_name="episodes",
                            points_selector=orphan_ids,
                        )
                        cleaned = len(orphan_ids)
                        logger.info(f"Dream: reconciled {cleaned} orphan vectors")
                except Exception as e:
                    logger.warning(f"Qdrant reconciliation failed: {e}")
        except Exception as e:
            logger.warning(f"Memory reconciliation failed: {e}")

        return cleaned

    async def _cleanup_zero_vectors(self) -> int:
        """Find and delete near-zero vectors from Qdrant.

        Skips points whose session_key has a pending re-embedding in the SLM queue.
        """
        if not self._memory or not hasattr(self._memory, '_qdrant') or not self._memory._qdrant:
            return 0

        # Get protected session keys (pending embedding in SLM queue)
        protected_sessions: set[str] = set()
        slm_queue = getattr(self, "_slm_queue", None)
        if slm_queue:
            try:
                protected_sessions = await slm_queue.pending_session_keys("embedding")
            except Exception:
                pass  # If queue check fails, proceed with cleanup normally

        cleaned = 0
        try:
            result = await self._memory._qdrant.scroll(
                collection_name="episodes",
                limit=100,
                with_vectors=True,
                with_payload=True,
            )
            points = result[0] if result else []
            zero_ids = []
            skipped = 0
            for p in points:
                if p.vector and isinstance(p.vector, list):
                    magnitude = sum(v * v for v in p.vector) ** 0.5
                    if magnitude < 0.01:
                        session_key = (p.payload or {}).get("session_key", "")
                        if session_key in protected_sessions:
                            skipped += 1
                            continue
                        zero_ids.append(p.id)

            if skipped:
                logger.info(f"Dream: skipped {skipped} zero-vectors (pending re-embed)")
            if zero_ids:
                await self._memory._qdrant.delete(
                    collection_name="episodes",
                    points_selector=zero_ids,
                )
                cleaned = len(zero_ids)
                logger.info(f"Dream: cleaned {cleaned} near-zero vectors")
        except Exception as e:
            logger.warning(f"Zero vector cleanup failed: {e}")

        return cleaned

    async def _self_reflect(self, report: DreamReport) -> str:
        """Metacognitive self-reflection: what could be improved?"""
        if not self._execute_fn:
            return ""

        # Gather context for a meaningful reflection
        recent_context = await self._gather_reflection_context(report)

        prompt = f"""You are performing a nightly self-reflection. Here is today's operational data:

{recent_context}

Based on this, answer in 2-3 concise sentences:
1. What went well or poorly today?
2. What capability gap came up that I should address (a skill I could build, a tool I'm missing)?
3. One specific thing to do better tomorrow.

Do NOT use headers or formatting. Just plain sentences. Be specific, not generic."""

        try:
            result = await self._execute_fn(prompt)
            # Take the substantive content, strip formatting artifacts
            text = (result or "").strip()
            # Remove common LLM formatting wrappers
            for prefix in ("*Reflection Complete:*", "*Reflection:*", "Reflection:", "**Reflection:**"):
                if text.startswith(prefix):
                    text = text[len(prefix):].strip()
            # Truncate to ~200 chars for WhatsApp
            if len(text) > 200:
                text = text[:197] + "..."
            return text
        except Exception as e:
            logger.warning(f"Self-reflection failed: {e}")
            return ""

    async def _gather_reflection_context(self, report: DreamReport) -> str:
        """Collect recent activity data for the reflection prompt."""
        sections = []

        # Cost data
        if report.cost_summary:
            sections.append(f"Cost: {report.cost_summary}")

        # Lessons
        if report.lessons_reviewed:
            sections.append(f"Lessons: {report.lessons_reviewed} reviewed, {report.lessons_deactivated} deactivated")

        # Alerts
        if report.alerts:
            sections.append("Alerts:\n" + "\n".join(f"  - {a}" for a in report.alerts[:5]))

        # Errors from this dream cycle
        if report.errors:
            sections.append("Dream cycle errors: " + "; ".join(report.errors[:3]))

        # Recent conversations (last 24h from episodes)
        if self._db_path:
            try:
                async with aiosqlite.connect(self._db_path) as db:
                    cur = await db.execute(
                        """SELECT text FROM episodes_content
                           WHERE timestamp > unixepoch('now', '-1 day')
                           ORDER BY timestamp DESC LIMIT 10"""
                    )
                    rows = await cur.fetchall()
                    if rows:
                        # Truncate each episode to keep context manageable
                        snippets = [r[0][:150] for r in rows]
                        sections.append("Recent conversations (excerpts):\n" + "\n".join(f"  - {s}" for s in snippets))
                    else:
                        sections.append("No conversations in the last 24 hours.")

                    # Recent alerts from DB (not just dream cycle alerts)
                    cur = await db.execute(
                        """SELECT severity, subsystem, message FROM alerts
                           WHERE timestamp > datetime('now', '-1 day')
                           ORDER BY timestamp DESC LIMIT 5"""
                    )
                    alert_rows = await cur.fetchall()
                    if alert_rows:
                        sections.append("Recent system alerts:\n" + "\n".join(
                            f"  - [{r[0]}] {r[1]}: {r[2][:100]}" for r in alert_rows
                        ))
            except Exception as e:
                logger.warning(f"Reflection context query failed: {e}")

        return "\n\n".join(sections) if sections else "No activity data available."

    async def _check_memory_budget(self) -> None:
        """Warn if MEMORY.md exceeds ~400 token budget (~300 words)."""
        memory_path = Path("/home/ubuntu/.nanobot/workspace/memory/MEMORY.md")
        if not memory_path.exists():
            return
        text = memory_path.read_text()
        word_count = len(text.split())
        estimated_tokens = int(word_count * 1.3)
        if estimated_tokens > 400:
            msg = (
                f"MEMORY.md has grown to ~{estimated_tokens} tokens "
                f"({word_count} words, budget: 400 tokens). "
                "Move non-behavioral content to Qdrant via recall_messages."
            )
            logger.warning(msg)
            # Write as heartbeat event so the LLM sees it next session
            if self._db_path:
                try:
                    async with aiosqlite.connect(self._db_path) as db:
                        await db.execute(
                            """INSERT INTO heartbeat_events
                               (event_type, severity, message, source)
                               VALUES (?, ?, ?, ?)""",
                            ("memory_budget", "medium", msg, "dream_cycle"),
                        )
                        await db.commit()
                except Exception as e:
                    logger.warning(f"Failed to write memory budget event: {e}")

    async def _cleanup_routing_preferences(self) -> None:
        """Remove routing preferences older than 7 days."""
        if not self._db_path:
            return
        try:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    "DELETE FROM routing_preferences WHERE created_at < datetime('now', '-7 days')"
                )
                await db.commit()
        except Exception as e:
            logger.warning(f"Routing preference cleanup failed: {e}")

    async def run_weekly(self) -> str:
        """Weekly strategic review — audits model pool, cost trends, proposes changes."""
        if not self._execute_fn:
            return "No execute function configured"

        pool_path = Path(self._docs_dir) / "models.md"
        pool_content = pool_path.read_text() if pool_path.exists() else "(no model pool file found)"

        weekly_stats = await self._get_weekly_stats()

        prompt = f"""You are performing a weekly strategic review. This runs every Sunday.

## Current Model Pool
{pool_content}

## This Week's Stats
{weekly_stats}

## EMERGENCY FALLBACK (DO NOT MODIFY)
`{self._emergency_cloud_model}` is the hardcoded emergency fallback model. It is intentionally
excluded from your review. Never recommend changing or removing it. It exists precisely because
all other models may fail — it must remain stable and unconditionally available.

## Review Checklist

### 1. Routing Configuration Verification (REQUIRED — do this first)
The routing configuration lives in three places. Verify and update ALL of them:

a) **`~/.nanobot/config.json`** — `fast_model` and `big_model` fields under `copilot`.
   Read the file, check whether the model IDs are still current and valid.
   Use `set_preference` tool to update `fast_model` or `big_model` if stale.

b) **`nanobot/agent/loop.py`** — the `MODEL_ALIASES` dict near the top of the file.
   Read the file, verify each alias points to a current, valid model ID.
   Use `edit_file` to update any stale aliases directly.

c) **`nanobot/copilot/tools/use_model.py`** — the `_ALIASES` dict.
   Read the file, verify it mirrors loop.py aliases.
   Use `edit_file` to update if out of sync.

To verify model IDs: use `web_search` to check current Anthropic, OpenAI, Google, and
OpenRouter model listings. A model ID is stale if it has been renamed, versioned, or
deprecated by the provider. When in doubt, prefer the model ID format currently shown
in official API documentation.

After any update, log what changed ("Updated fast_model from X to Y").

### 2. Model Pool Audit
Are any models in `data/copilot/models.md` obsolete? Newer/better alternatives?
Flag any that underperformed this week. Do NOT change the emergency fallback.

### 3. Cost Trends
Compare this week's cost to last week. Are we overspending on any tier?

### 4. Free Tier Usage
Are we maximizing free tier allocations? Could any paid calls shift to free options?

### 5. New Developments
Use web_search to check for new model releases that should be added to the pool or
replace existing entries. Update `data/copilot/models.md` with findings.

## Response Format
Provide a concise weekly report (goes to WhatsApp — keep it brief):
- Routing config changes made (or "no changes needed")
- Model pool changes recommended
- Cost trend (1-2 sentences)
- Top 3 actionable suggestions for next week
- Note current date as "Last Reviewed" in the model pool"""

        try:
            result = await self._execute_fn(prompt)
        except Exception as e:
            logger.error(f"Weekly review agent call failed: {e}")
            return f"Weekly review failed: {e}"

        if self._deliver and self._chat_id:
            try:
                await self._deliver(self._channel, self._chat_id, f"Weekly Review\n\n{result}")
            except Exception as e:
                logger.warning(f"Weekly review delivery failed: {e}")

        # Log to heartbeat_events so /status can show "Weekly review: Xh ago"
        try:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    "INSERT INTO heartbeat_events (event_type, severity, message, source) "
                    "VALUES ('weekly_review', 'info', ?, 'weekly')",
                    ((result or "")[:500],),
                )
                await db.commit()
        except Exception:
            pass

        logger.info("Weekly review complete")
        return result or ""

    async def _get_weekly_stats(self) -> str:
        """Collect cost and usage stats for the past 7 days."""
        if not self._db_path:
            return "No cost data available"

        try:
            async with aiosqlite.connect(self._db_path) as db:
                cur = await db.execute("""
                    SELECT model, COUNT(*) as calls, SUM(cost_usd) as total
                    FROM cost_log WHERE timestamp >= datetime('now', '-7 days')
                    GROUP BY model ORDER BY total DESC
                """)
                rows = await cur.fetchall()

                cur2 = await db.execute("""
                    SELECT COALESCE(SUM(cost_usd), 0) FROM cost_log
                    WHERE timestamp >= datetime('now', '-14 days')
                      AND timestamp < datetime('now', '-7 days')
                """)
                prior = (await cur2.fetchone())[0]
                this_week = sum(r[2] or 0 for r in rows)

            lines = [f"This week: ${this_week:.2f} (prior week: ${prior:.2f})"]
            for model, calls, cost in rows:
                lines.append(f"  {model}: ${cost:.2f} ({calls} calls)")
            return "\n".join(lines)
        except Exception as e:
            return f"Stats query failed: {e}"

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
