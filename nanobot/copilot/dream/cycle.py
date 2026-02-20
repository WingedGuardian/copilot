"""Dream cycle: nightly maintenance orchestrator."""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Awaitable

import aiosqlite
from loguru import logger

from nanobot.copilot.memory.episodic import EpisodicStore


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
        """Format as a concise summary."""
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
        weekly_execute_fn: Callable[[str], Awaitable[str]] | None = None,
        monthly_execute_fn: Callable[[str], Awaitable[str]] | None = None,
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
        self._weekly_execute_fn = weekly_execute_fn or execute_fn
        self._monthly_execute_fn = monthly_execute_fn or execute_fn
        self._backup_dir = Path(backup_dir)
        self._deliver = deliver_fn
        self._channel = delivery_channel
        self._chat_id = delivery_chat_id
        self._docs_dir = docs_dir
        self._emergency_cloud_model = emergency_cloud_model

    async def run(self) -> DreamReport:
        """Run all maintenance jobs and return report."""
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

        # Surface errors in AlertBus so they appear in /status Active Alerts
        if report.errors:
            try:
                from nanobot.copilot.alerting.bus import get_alert_bus
                bus = get_alert_bus()
                for err in report.errors:
                    job_name = err.split(":")[0] if ":" in err else "unknown"
                    await bus.alert(
                        "dream", "medium",
                        f"Dream cycle job failed: {err[:200]}",
                        f"dream_job_{job_name}",
                    )
            except Exception as e:
                logger.debug(f"Dream AlertBus write failed: {e}")

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
            # LM Studio is optional local infra — not alertworthy when down
            if not sub.healthy and sub.name != "LM Studio":
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
                        collection_name=EpisodicStore.COLLECTION,
                        limit=max_per_cycle,
                        with_payload=False,
                    )
                    points = result[0] if result else []
                    orphan_ids = [p.id for p in points if str(p.id) not in db_ids]
                    if orphan_ids:
                        await self._memory._qdrant.delete(
                            collection_name=EpisodicStore.COLLECTION,
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
            zero_ids = []
            skipped = 0
            offset = None  # Qdrant scroll cursor
            while True:
                scroll_kwargs = {
                    "collection_name": EpisodicStore.COLLECTION,
                    "limit": 100,
                    "with_vectors": True,
                    "with_payload": True,
                }
                if offset is not None:
                    scroll_kwargs["offset"] = offset
                result = await self._memory._qdrant.scroll(**scroll_kwargs)
                points, next_offset = result if result else ([], None)
                for p in points:
                    if p.vector and isinstance(p.vector, list):
                        magnitude = sum(v * v for v in p.vector) ** 0.5
                        if magnitude < 0.01:
                            session_key = (p.payload or {}).get("session_key", "")
                            if session_key in protected_sessions:
                                skipped += 1
                                continue
                            zero_ids.append(p.id)
                if not next_offset:
                    break
                offset = next_offset

            if skipped:
                logger.info(f"Dream: skipped {skipped} zero-vectors (pending re-embed)")
            if zero_ids:
                await self._memory._qdrant.delete(
                    collection_name=EpisodicStore.COLLECTION,
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

        prompt = f"""You are performing a nightly operational self-reflection. Here is today's data:

{recent_context}

Give a high-level summary of what happened tonight. Keep it operational — the weekly review handles strategy.

- What broke or degraded? What recovered?
- What needs user attention or approval? (be specific — recommended changes, actions required, decisions pending)
- Any data quality or resource concerns?

Be as long as you need to be, but stay high-level. Only go into detail on items that require user action or approval.
Do NOT use headers or markdown formatting. Plain sentences.
Do NOT suggest new features or capability gaps — that's the weekly review's job."""

        try:
            result = await self._execute_fn(prompt)
            # Take the substantive content, strip formatting artifacts
            text = (result or "").strip()
            # Remove common LLM formatting wrappers
            for prefix in ("*Reflection Complete:*", "*Reflection:*", "Reflection:", "**Reflection:**"):
                if text.startswith(prefix):
                    text = text[len(prefix):].strip()
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

        # Memory health: file budget status
        import json as _json
        workspace = Path("/home/ubuntu/.nanobot/workspace")
        budgets_path = workspace / "budgets.json"
        try:
            budgets = _json.loads(budgets_path.read_text()) if budgets_path.exists() else {}
            over = []
            for fname in ["SOUL.md", "USER.md", "AGENTS.md", "POLICY.md", "memory/MEMORY.md"]:
                fp = workspace / fname
                if fp.exists():
                    est = int(len(fp.read_text().split()) * 1.3)
                    limit = budgets.get(fname)
                    if isinstance(limit, int) and est > limit:
                        over.append(f"{fname}: ~{est} tok (budget: {limit})")
            if over:
                sections.append("Files over budget: " + "; ".join(over))
        except Exception:
            pass

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
                             AND message NOT LIKE '%lm_studio%'
                             AND message NOT LIKE '%LM Studio%'
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
        """Warn if any identity file exceeds its token budget.

        Reads budgets from ``~/.nanobot/workspace/budgets.json``.
        Does NOT truncate — only logs warnings as heartbeat events so the
        LLM (or a review cycle) can decide what to trim.
        """
        import json

        workspace = Path("/home/ubuntu/.nanobot/workspace")
        budgets_path = workspace / "budgets.json"

        # Default budgets if config file missing
        defaults = {
            "SOUL.md": 250, "USER.md": 250, "AGENTS.md": 600,
            "POLICY.md": 200, "memory/MEMORY.md": 150,
        }

        try:
            if budgets_path.exists():
                raw = json.loads(budgets_path.read_text())
                budgets = {k: v for k, v in raw.items() if not k.startswith("_") and isinstance(v, int)}
            else:
                budgets = defaults
        except Exception:
            budgets = defaults

        over_budget: list[str] = []
        for filename, limit in budgets.items():
            file_path = workspace / filename
            if not file_path.exists():
                continue
            text = file_path.read_text(encoding="utf-8")
            word_count = len(text.split())
            estimated_tokens = int(word_count * 1.3)
            if estimated_tokens > limit:
                over_budget.append(
                    f"{filename}: ~{estimated_tokens} tokens (budget: {limit})"
                )

        if not over_budget:
            return

        msg = "File budget exceeded (warn only): " + "; ".join(over_budget)
        logger.warning(msg)

        if self._db_path:
            try:
                async with aiosqlite.connect(self._db_path) as db:
                    await db.execute(
                        """INSERT INTO heartbeat_events
                           (event_type, severity, message, source)
                           VALUES (?, ?, ?, ?)""",
                        ("file_budget", "medium", msg, "dream_cycle"),
                    )
                    await db.commit()
            except Exception as e:
                logger.warning(f"Failed to write budget event: {e}")

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
        """Weekly strategic review (Manager role).

        Oversees dream cycle, manages architecture/code quality, audits models,
        trims over-budget files, implements monthly findings.
        """
        if not self._weekly_execute_fn:
            return "No execute function configured"

        pool_path = Path(self._docs_dir) / "models.md"
        pool_content = pool_path.read_text() if pool_path.exists() else "(no model pool file found)"

        weekly_stats = await self._get_weekly_stats()
        dream_health = await self._get_dream_errors()

        # Read monthly findings if they exist
        import json as _json
        findings_path = Path("/home/ubuntu/.nanobot/workspace/monthly_review_findings.json")
        monthly_findings = ""
        if findings_path.exists():
            try:
                data = _json.loads(findings_path.read_text())
                items = data.get("findings", [])
                if items:
                    monthly_findings = "The monthly review left these findings for you to implement:\n"
                    for f in items:
                        monthly_findings += f"  - [{f.get('priority', '?')}] {f.get('category', '?')}: {f.get('finding', '')}\n"
            except Exception:
                pass

        prompt = f"""You are performing a weekly strategic review (MANAGER role). This runs every Sunday.
Your job: oversee the daily dream cycle, manage architecture and code quality, audit models,
optimize costs, and implement any findings from the monthly audit.

## Dream Cycle Health (last 7 days)
{dream_health}

{"## Monthly Review Findings (ACTION REQUIRED)" + chr(10) + monthly_findings + chr(10) + "Address each finding below. After processing, delete the file ~/.nanobot/workspace/monthly_review_findings.json." if monthly_findings else "## Monthly Review Findings" + chr(10) + "No pending findings from the monthly review."}

## This Week's Stats
{weekly_stats}

## Current Model Pool
{pool_content}

## EMERGENCY FALLBACK (DO NOT MODIFY)
`{self._emergency_cloud_model}` is the hardcoded emergency fallback model. Never change it.

## Review Checklist

### 1. Dream Cycle Oversight
Review the dream cycle health data above.
- Are any jobs consistently failing? Investigate and fix the root cause.
- Is the dream cycle running daily? If it missed days, investigate why.
- Are cleanup decisions appropriate? (pruning too much or too little?)

### 2. Architecture & Code Quality
- Read `~/.nanobot/CHANGELOG.local` for this week's changes. Look for patterns or instability.
- Check workspace identity files (SOUL.md, USER.md, AGENTS.md, POLICY.md) for drift:
  stale info, contradictions, information in the wrong file.
- Review recent alerts: `ops_log(category="alerts", hours=168)`
- If changes are needed, make them. For significant code changes, suggest to the user first via `message` tool.

### 3. Memory Health
- Check each identity file's token count vs budget in `~/.nanobot/workspace/budgets.json`.
- If any file is over budget, trim it (use LLM judgment about what to cut).
- Do NOT adjust the budgets themselves — that's the monthly review's job.
- Check MEMORY.md specifically — is it a lean scratchpad or bloated with resolved items?

### 4. Model Pool & Routing
a) Verify routing config in `~/.nanobot/config.json` (fast_model, big_model), `nanobot/agent/loop.py` (MODEL_ALIASES), and `nanobot/copilot/tools/use_model.py` (_ALIASES).
b) Use `web_search` to check for deprecated or renamed model IDs.
c) Audit `data/copilot/models.md` for obsolete models or better alternatives.
d) Check free tier usage — can any paid calls shift to free options?

### 5. Cost Trends
Compare this week vs. last week. Flag overspending by tier or model.

### 6. Strategic Direction
- What should nanobot focus on this week? Any priorities that need shifting?
- Are there patterns in errors or user requests that suggest a capability gap?
- Set direction for the coming week's dream cycles.

## After Making Changes
- Commit all file changes to git with a descriptive message.
- Append to `~/.nanobot/CHANGELOG.local`:
  `[YYYY-MM-DD HH:MM] nanobot-weekly: brief description`
- If you edited code, suggest significant changes to the user first via message tool.

## Response Format
Provide a weekly report. Be thorough but stay high-level:
- Dream cycle health (clean / N errors)
- Monthly findings addressed (or "none pending")
- Architecture/code changes made
- Memory health (all within budget / trimmed X)
- Model/routing changes (or "no changes needed")
- Cost trend (1-2 sentences)
- Top 3 priorities for next week
- Note current date as "Last Reviewed" in the model pool"""

        try:
            result = await self._weekly_execute_fn(prompt)
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

    async def _get_dream_errors(self) -> str:
        """Summarize dream cycle health for weekly oversight."""
        if not self._db_path:
            return "No dream cycle data available"

        try:
            async with aiosqlite.connect(self._db_path) as db:
                cur = await db.execute("""
                    SELECT run_at, duration_ms, errors
                    FROM dream_cycle_log
                    WHERE run_at >= datetime('now', '-7 days')
                    ORDER BY run_at DESC
                """)
                rows = await cur.fetchall()

            if not rows:
                return "No dream cycles ran in the past 7 days."

            error_runs = [(r[0], r[2]) for r in rows if r[2]]
            lines = [f"Dream cycles (last 7 days): {len(rows)} runs"]
            if error_runs:
                lines.append(f"  Runs with errors: {len(error_runs)}")
                for run_at, errors in error_runs[:5]:
                    lines.append(f"  {run_at}: {errors[:200]}")
            else:
                lines.append("  All runs clean — no errors.")
            return "\n".join(lines)
        except Exception as e:
            return f"Dream log query failed: {e}"

    async def _get_monthly_stats(self) -> str:
        """Collect cost and usage stats for the past 30 days with weekly breakdown."""
        if not self._db_path:
            return "No cost data available"

        try:
            async with aiosqlite.connect(self._db_path) as db:
                # Total this month
                cur = await db.execute("""
                    SELECT model, COUNT(*) as calls, SUM(cost_usd) as total
                    FROM cost_log WHERE timestamp >= datetime('now', '-30 days')
                    GROUP BY model ORDER BY total DESC
                """)
                rows = await cur.fetchall()

                # Prior 30 days for comparison
                cur2 = await db.execute("""
                    SELECT COALESCE(SUM(cost_usd), 0) FROM cost_log
                    WHERE timestamp >= datetime('now', '-60 days')
                      AND timestamp < datetime('now', '-30 days')
                """)
                prior = (await cur2.fetchone())[0]
                this_month = sum(r[2] or 0 for r in rows)

                # Week-by-week breakdown
                cur3 = await db.execute("""
                    SELECT strftime('%Y-W%W', timestamp) as week,
                           COUNT(*) as calls, SUM(cost_usd) as total
                    FROM cost_log
                    WHERE timestamp >= datetime('now', '-30 days')
                    GROUP BY week ORDER BY week
                """)
                weekly_rows = await cur3.fetchall()

            lines = [f"This month: ${this_month:.2f} (prior month: ${prior:.2f})"]
            if rows:
                lines.append("By model:")
                for model, calls, cost in rows:
                    lines.append(f"  {model}: ${cost:.2f} ({calls} calls)")
            if weekly_rows:
                lines.append("By week:")
                for week, calls, cost in weekly_rows:
                    lines.append(f"  {week}: ${cost:.2f} ({calls} calls)")
            return "\n".join(lines)
        except Exception as e:
            return f"Monthly stats query failed: {e}"

    async def run_monthly(self) -> str:
        """Monthly comprehensive audit (Director role).

        Reviews weekly reports, adjusts budget policy, audits architecture
        (but doesn't fix — writes findings for weekly), analyzes cost structure.
        """
        if not self._monthly_execute_fn:
            return "No execute function configured"

        import json
        workspace = Path("/home/ubuntu/.nanobot/workspace")

        # Gather file sizes
        file_report: list[str] = []
        budgets_path = workspace / "budgets.json"
        budgets = {}
        if budgets_path.exists():
            try:
                budgets = json.loads(budgets_path.read_text())
            except Exception:
                pass

        for filename in ["SOUL.md", "USER.md", "AGENTS.md", "POLICY.md", "memory/MEMORY.md"]:
            fp = workspace / filename
            if fp.exists():
                words = len(fp.read_text().split())
                tokens = int(words * 1.3)
                limit = budgets.get(filename, "?")
                status = "OVER" if isinstance(limit, int) and tokens > limit else "ok"
                file_report.append(f"  {filename}: ~{tokens} tok (budget: {limit}) [{status}]")

        monthly_stats = await self._get_monthly_stats()

        # Gather weekly review summaries from the past 30 days
        weekly_summaries = ""
        if self._db_path:
            try:
                async with aiosqlite.connect(self._db_path) as db:
                    cur = await db.execute(
                        """SELECT created_at, message FROM heartbeat_events
                           WHERE event_type = 'weekly_review'
                             AND created_at >= datetime('now', '-30 days')
                           ORDER BY created_at DESC LIMIT 5"""
                    )
                    rows = await cur.fetchall()
                    if rows:
                        weekly_summaries = "\n".join(
                            f"  [{r[0]}] {r[1]}" for r in rows
                        )
            except Exception:
                pass

        prompt = f"""You are performing a MONTHLY comprehensive audit (DIRECTOR role). This runs on the 1st of each month.
You are NOT the implementer — you are the auditor. You review the weekly review's work, assess
long-term health, adjust policies, and write findings for the weekly review to implement.

## Weekly Review Summaries (last 30 days)
{weekly_summaries or "No weekly reviews found in the past 30 days."}

## File Budget Report
{chr(10).join(file_report)}
Current budgets.json: {json.dumps(budgets, indent=2) if budgets else "(missing)"}

## Cost Data (30 days)
{monthly_stats}

## Audit Checklist

### 1. Review Weekly Reports
Look at the weekly review summaries above. Assess:
- Is weekly making good strategic decisions?
- Are the model/routing changes appropriate?
- Is weekly catching and fixing issues effectively?
- Any patterns in what weekly is missing?

### 2. File Budget Policy (YOU are the ONLY cycle that adjusts budgets)
For each identity file, assess whether the current budget is right:
- Too tight? Weekly keeps having to trim content that should stay.
- Too loose? Files have persistent stale content.
- Adjust `~/.nanobot/workspace/budgets.json` if needed.
- This is a POLICY decision — you set the limits, weekly enforces them.

### 3. Architecture Audit (DO NOT FIX — write findings for weekly)
Read the key workspace files (SOUL.md, USER.md, AGENTS.md, POLICY.md).
Look for:
- Stale information (resolved issues, outdated references)
- Contradictions between files
- Information in the wrong file (user prefs in AGENTS.md, ops rules in SOUL.md)
- Duplication across files
**Do NOT fix these yourself.** Write findings to the findings file (see below).

### 4. Codebase Patterns
Read `~/.nanobot/CHANGELOG.local` for the past month's changes.
Look for patterns: recurring fixes, areas of instability, features that keep changing.
Flag anything that suggests a deeper architectural issue.
Check episodic memory health: `ops_log(category="heartbeat", hours=720)`

### 5. Cost Structure
This is NOT about trends (weekly handles that). Assess:
- Are we spending on the right tiers? Is the tier structure itself correct?
- Should any workloads move between tiers?
- Are the dream/weekly/monthly model assignments cost-effective?

### 6. Self-Reflection
- What needs rethinking long-term?
- Is the weekly review moving nanobot in the right direction?
- Are the automated cycles (dream/weekly/heartbeat) serving the user well?
- What would you change about how this system operates?

## Writing Findings for Weekly
After your audit, write actionable findings to `~/.nanobot/workspace/monthly_review_findings.json`:
```json
{{
  "generated": "YYYY-MM-DD",
  "findings": [
    {{"category": "budget|architecture|code|cost|strategic", "finding": "description", "priority": "high|medium|low"}}
  ]
}}
```
Weekly will read this file, implement the findings, and clear it.
Only include findings that need ACTION — not observations.

## After Making Changes
- Commit budgets.json changes to git if you modified budgets.
- Append to `~/.nanobot/CHANGELOG.local`:
  `[YYYY-MM-DD HH:MM] nanobot-monthly: brief description`
- Do NOT commit architecture fixes — weekly handles implementation.

## Response Format
Provide a comprehensive monthly audit report:
- Weekly review assessment (doing well / needs attention)
- Budget policy changes (with reasoning, or "no changes")
- Architecture findings written for weekly (count + summary)
- Codebase health patterns
- Cost structure assessment
- Self-reflection (2-3 sentences)
- Top 3 long-term recommendations"""

        try:
            result = await self._monthly_execute_fn(prompt)
        except Exception as e:
            logger.error(f"Monthly review agent call failed: {e}")
            return f"Monthly review failed: {e}"

        if self._deliver and self._chat_id:
            try:
                await self._deliver(self._channel, self._chat_id, f"Monthly Review\n\n{result}")
            except Exception as e:
                logger.warning(f"Monthly review delivery failed: {e}")

        try:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    "INSERT INTO heartbeat_events (event_type, severity, message, source) "
                    "VALUES ('monthly_review', 'info', ?, 'monthly')",
                    ((result or "")[:500],),
                )
                await db.commit()
        except Exception:
            pass

        logger.info("Monthly review complete")
        return result or ""

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
