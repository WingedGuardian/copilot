"""Read and acknowledge heartbeat events for session context injection."""

from __future__ import annotations

from datetime import datetime

import aiosqlite
from loguru import logger


async def get_unacknowledged_events(db_path: str, limit: int = 10) -> str:
    """Read unacknowledged heartbeat events and mark them acknowledged.

    Returns a formatted context string for injection into the system prompt,
    or empty string if no events exist.  Budget target: <150 tokens.
    """
    if not db_path:
        return ""

    try:
        async with aiosqlite.connect(db_path) as db:
            cur = await db.execute(
                """SELECT id, severity, message, created_at
                   FROM heartbeat_events
                   WHERE acknowledged = 0
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (limit,),
            )
            rows = await cur.fetchall()
            if not rows:
                return ""

            # Mark as acknowledged
            ids = [r[0] for r in rows]
            placeholders = ",".join("?" * len(ids))
            await db.execute(
                f"UPDATE heartbeat_events SET acknowledged = 1 WHERE id IN ({placeholders})",
                ids,
            )
            await db.commit()

            # Format for context injection
            lines = ["## Recent Events"]
            for _, severity, message, created_at in rows:
                # Truncate long messages
                msg = message[:200] if len(message) > 200 else message
                lines.append(f"- [{severity}] {msg}")

            return "\n".join(lines)

    except Exception as e:
        logger.debug(f"Failed to read heartbeat events: {e}")
        return ""


async def get_heartbeat_summary(db_path: str) -> str:
    """Always-on heartbeat status for system prompt injection (~20 tokens).

    Returns a brief one-liner like:
      "Last heartbeat: 45m ago, all healthy"
      "Last heartbeat: 2h ago — [high] Redis unreachable"
    """
    if not db_path:
        return ""

    try:
        async with aiosqlite.connect(db_path) as db:
            # Last heartbeat run
            cur = await db.execute(
                "SELECT run_at, tasks_with_results FROM heartbeat_log ORDER BY run_at DESC LIMIT 1"
            )
            run = await cur.fetchone()
            if not run:
                return ""

            ago = _format_ago_short(run[0])
            event_count = run[1] or 0

            # If events were recorded, grab the most severe recent one
            if event_count > 0:
                cur = await db.execute(
                    """SELECT severity, message FROM heartbeat_events
                       WHERE created_at >= datetime('now', '-4 hours')
                         AND severity IN ('high', 'medium')
                       ORDER BY created_at DESC LIMIT 1"""
                )
                event = await cur.fetchone()
                if event:
                    return f"Last heartbeat: {ago} — [{event[0]}] {event[1][:80]}"

            return f"Last heartbeat: {ago}, all healthy"

    except Exception as e:
        logger.debug(f"Heartbeat summary failed: {e}")
        return ""


def _format_ago_short(timestamp_str: str) -> str:
    """Format a DB timestamp as a compact 'Xm ago' or 'Xh ago' string."""
    try:
        ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        delta = datetime.now(tz=None) - ts.replace(tzinfo=None)
        total_seconds = int(delta.total_seconds())
        if total_seconds < 120:
            return f"{total_seconds}s ago"
        minutes = total_seconds // 60
        if minutes < 120:
            return f"{minutes}m ago"
        hours = minutes // 60
        return f"{hours}h ago"
    except Exception:
        return timestamp_str
