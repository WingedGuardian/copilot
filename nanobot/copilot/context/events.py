"""Read and acknowledge heartbeat events for session context injection."""

from __future__ import annotations

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
