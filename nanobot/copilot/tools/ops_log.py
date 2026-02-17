"""Agent tool for querying operational history (dream cycles, heartbeat, alerts, costs)."""

from __future__ import annotations

import time
from typing import Any

import aiosqlite
from loguru import logger

from nanobot.agent.tools.base import Tool


class OpsLogTool(Tool):
    """Query operational logs so the bot can answer questions about its own history."""

    def __init__(self, db_path: str):
        self._db_path = db_path

    @property
    def name(self) -> str:
        return "ops_log"

    @property
    def description(self) -> str:
        return (
            "Query your own operational history: dream cycles, heartbeat events, "
            "alerts, and cost logs. Use when asked about system health history, "
            "past dream cycles, recent alerts, or spending trends."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["dream", "heartbeat", "alerts", "cost"],
                    "description": "Which operational log to query",
                },
                "hours": {
                    "type": "integer",
                    "description": "How far back to look (default 24, max 168)",
                },
            },
            "required": ["category"],
        }

    async def execute(self, **kwargs: Any) -> str:
        category = kwargs.get("category", "")
        hours = min(int(kwargs.get("hours", 24)), 168)

        if not self._db_path:
            return "No database configured."

        try:
            handler = {
                "dream": self._query_dream,
                "heartbeat": self._query_heartbeat,
                "alerts": self._query_alerts,
                "cost": self._query_cost,
            }.get(category)
            if not handler:
                return f"Unknown category '{category}'. Use: dream, heartbeat, alerts, cost"
            return await handler(hours)
        except Exception as e:
            logger.warning(f"ops_log query failed: {e}")
            return f"Query failed: {e}"

    async def _query_dream(self, hours: int) -> str:
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                """SELECT run_at, duration_ms, episodes_consolidated,
                          items_created, items_pruned, lessons_reviewed, errors
                   FROM dream_cycle_log
                   WHERE run_at >= datetime('now', ? || ' hours')
                   ORDER BY run_at DESC LIMIT 10""",
                (f"-{hours}",),
            )
            rows = await cur.fetchall()

        if not rows:
            return f"No dream cycles in the last {hours}h."

        lines = [f"Dream Cycles (last {hours}h): {len(rows)} run(s)"]
        for run_at, dur, consolidated, created, pruned, lessons, errors in rows:
            line = f"  {run_at} ({dur}ms)"
            parts = []
            if consolidated:
                parts.append(f"{consolidated} consolidated")
            if created:
                parts.append(f"{created} created")
            if pruned:
                parts.append(f"{pruned} pruned")
            if lessons:
                parts.append(f"{lessons} lessons reviewed")
            if parts:
                line += " — " + ", ".join(parts)
            if errors:
                line += f" [ERRORS: {errors[:100]}]"
            lines.append(line)
        return "\n".join(lines)

    async def _query_heartbeat(self, hours: int) -> str:
        async with aiosqlite.connect(self._db_path) as db:
            # Recent heartbeat runs
            cur = await db.execute(
                """SELECT run_at, tasks_checked, tasks_with_results, duration_ms
                   FROM heartbeat_log
                   WHERE run_at >= datetime('now', ? || ' hours')
                   ORDER BY run_at DESC LIMIT 10""",
                (f"-{hours}",),
            )
            runs = await cur.fetchall()

            # Recent heartbeat events (all, not just unacknowledged)
            cur = await db.execute(
                """SELECT created_at, severity, message, source
                   FROM heartbeat_events
                   WHERE created_at >= datetime('now', ? || ' hours')
                   ORDER BY created_at DESC LIMIT 15""",
                (f"-{hours}",),
            )
            events = await cur.fetchall()

        lines = [f"Heartbeat (last {hours}h)"]
        if runs:
            lines.append(f"  Runs: {len(runs)}")
            for run_at, checked, results, dur in runs[:5]:
                lines.append(f"  {run_at} ({dur}ms) — {results} event(s)")
        else:
            lines.append("  No heartbeat runs recorded.")

        if events:
            lines.append(f"  Events: {len(events)}")
            for ts, sev, msg, source in events[:10]:
                lines.append(f"  [{sev}] {ts}: {msg[:120]}")
        else:
            lines.append("  No events.")
        return "\n".join(lines)

    async def _query_alerts(self, hours: int) -> str:
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                """SELECT subsystem, severity, message,
                          MAX(timestamp) as last_seen, COUNT(*) as occurrences
                   FROM alerts
                   WHERE timestamp >= datetime('now', ? || ' hours')
                   GROUP BY error_key
                   ORDER BY last_seen DESC LIMIT 15""",
                (f"-{hours}",),
            )
            rows = await cur.fetchall()

        if not rows:
            return f"No alerts in the last {hours}h."

        high = sum(1 for r in rows if r[1] == "high")
        med = sum(1 for r in rows if r[1] == "medium")
        lines = [f"Alerts (last {hours}h): {len(rows)} unique ({high} high, {med} medium)"]
        for subsystem, severity, message, last_seen, count in rows:
            suffix = f" (x{count})" if count > 1 else ""
            lines.append(f"  [{severity}] {subsystem}: {message[:100]}{suffix}")
            lines.append(f"    Last seen: {last_seen}")
        return "\n".join(lines)

    async def _query_cost(self, hours: int) -> str:
        async with aiosqlite.connect(self._db_path) as db:
            # Total
            cur = await db.execute(
                """SELECT COALESCE(SUM(cost_usd), 0), COUNT(*)
                   FROM cost_log
                   WHERE timestamp >= datetime('now', ? || ' hours')""",
                (f"-{hours}",),
            )
            total_cost, total_calls = await cur.fetchone()

            # By model
            cur = await db.execute(
                """SELECT model, COUNT(*) as calls, SUM(cost_usd) as total,
                          SUM(tokens_input) as tok_in, SUM(tokens_output) as tok_out
                   FROM cost_log
                   WHERE timestamp >= datetime('now', ? || ' hours')
                   GROUP BY model ORDER BY total DESC LIMIT 10""",
                (f"-{hours}",),
            )
            by_model = await cur.fetchall()

            # By day
            cur = await db.execute(
                """SELECT date(timestamp) as day, SUM(cost_usd), COUNT(*)
                   FROM cost_log
                   WHERE timestamp >= datetime('now', ? || ' hours')
                   GROUP BY day ORDER BY day DESC LIMIT 7""",
                (f"-{hours}",),
            )
            by_day = await cur.fetchall()

        lines = [f"Cost (last {hours}h): ${total_cost:.2f} ({total_calls} calls)"]
        if by_model:
            lines.append("  By model:")
            for model, calls, cost, tok_in, tok_out in by_model:
                lines.append(f"    {model}: ${cost:.2f} ({calls} calls, {tok_in or 0:,}+{tok_out or 0:,} tokens)")
        if by_day:
            lines.append("  By day:")
            for day, cost, calls in by_day:
                lines.append(f"    {day}: ${cost:.2f} ({calls} calls)")
        return "\n".join(lines)
