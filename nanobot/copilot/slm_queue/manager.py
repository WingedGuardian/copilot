"""SQLite-backed deferred work queue for SLM tasks (extraction + embedding)."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Literal

from loguru import logger

from nanobot.copilot.db import SqlitePool

WorkType = Literal["extraction", "embedding"]
WorkStatus = Literal["pending", "processing", "completed", "failed"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS slm_work_queue (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    work_type       TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'pending',
    priority        INTEGER NOT NULL DEFAULT 5,
    payload         TEXT    NOT NULL,
    dedup_hash      TEXT    NOT NULL,
    conversation_ts REAL    NOT NULL,
    queued_at       REAL    NOT NULL,
    started_at      REAL,
    completed_at    REAL,
    attempts        INTEGER NOT NULL DEFAULT 0,
    max_attempts    INTEGER NOT NULL DEFAULT 3,
    last_error      TEXT,
    session_key     TEXT    NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_slm_dedup ON slm_work_queue(dedup_hash);
CREATE INDEX IF NOT EXISTS idx_slm_pending ON slm_work_queue(status, priority, queued_at);

CREATE TABLE IF NOT EXISTS slm_queue_stats (
    id               INTEGER PRIMARY KEY CHECK (id = 1),
    total_queued     INTEGER NOT NULL DEFAULT 0,
    total_processed  INTEGER NOT NULL DEFAULT 0,
    total_failed     INTEGER NOT NULL DEFAULT 0,
    total_dropped    INTEGER NOT NULL DEFAULT 0,
    queue_size_limit INTEGER NOT NULL DEFAULT 500,
    last_drain_ts    REAL    NOT NULL DEFAULT 0.0
);
INSERT OR IGNORE INTO slm_queue_stats (id) VALUES (1);
"""


@dataclass
class WorkItem:
    """A single deferred work item."""

    id: int
    work_type: WorkType
    status: WorkStatus
    priority: int
    payload: dict[str, Any]
    conversation_ts: float
    queued_at: float
    started_at: float | None
    attempts: int
    max_attempts: int
    session_key: str
    last_error: str | None = None


class SlmWorkQueue:
    """Manages deferred SLM work: extractions + embeddings."""

    def __init__(self, pool: SqlitePool, size_limit: int = 500):
        self._pool = pool
        self._size_limit = size_limit

    async def initialize(self) -> None:
        """Create tables if they don't exist."""
        conn = await self._pool.acquire()
        try:
            await conn.executescript(_SCHEMA)
            # Migrate: add total_dropped column if missing (existing DBs)
            try:
                await conn.execute(
                    "ALTER TABLE slm_queue_stats ADD COLUMN total_dropped INTEGER NOT NULL DEFAULT 0"
                )
            except Exception:
                pass  # Column already exists
            await conn.commit()
        finally:
            await self._pool.release(conn)

    # ── Enqueue ──────────────────────────────────────────────────────

    async def enqueue_extraction(
        self,
        user_message: str,
        assistant_response: str,
        session_key: str,
        conversation_ts: float | None = None,
    ) -> int | None:
        """Queue an extraction. Returns work_id or None if queue full / deduped."""
        payload = {
            "user_message": user_message[:2000],
            "assistant_response": assistant_response[:2000],
        }
        dedup_key = f"ext:{session_key}:{user_message[:500]}:{assistant_response[:200]}"
        return await self._enqueue(
            "extraction", payload, session_key,
            conversation_ts or time.time(),
            hashlib.sha256(dedup_key.encode()).hexdigest(),
            priority=5,
        )

    async def enqueue_embedding(
        self,
        text: str,
        session_key: str,
        role: str = "exchange",
        metadata: dict[str, Any] | None = None,
        importance: float = 0.5,
        conversation_ts: float | None = None,
    ) -> int | None:
        """Queue an embedding. Returns work_id or None if queue full / deduped."""
        payload = {
            "text": text[:8000],
            "role": role,
            "metadata": metadata or {},
            "importance": importance,
        }
        dedup_key = f"emb:{session_key}:{role}:{text[:500]}"
        return await self._enqueue(
            "embedding", payload, session_key,
            conversation_ts or time.time(),
            hashlib.sha256(dedup_key.encode()).hexdigest(),
            priority=3,  # embeddings higher priority than extractions
        )

    async def _enqueue(
        self,
        work_type: WorkType,
        payload: dict[str, Any],
        session_key: str,
        conversation_ts: float,
        dedup_hash: str,
        priority: int,
    ) -> int | None:
        if await self.size() >= self._size_limit:
            logger.warning(f"SLM queue full ({self._size_limit}) — dropping {work_type}")
            try:
                await self._pool.execute(
                    "UPDATE slm_queue_stats SET total_dropped = total_dropped + 1 WHERE id = 1",
                    commit=True,
                )
                from nanobot.copilot.alerting.bus import get_alert_bus
                await get_alert_bus().alert(
                    "slm_queue", "medium",
                    f"SLM queue full ({self._size_limit}) — dropped {work_type}",
                    "queue_full",
                )
            except Exception:
                pass
            return None
        try:
            cur = await self._pool.execute(
                """INSERT OR IGNORE INTO slm_work_queue
                   (work_type, payload, dedup_hash, conversation_ts, queued_at,
                    session_key, priority)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (work_type, json.dumps(payload), dedup_hash,
                 conversation_ts, time.time(), session_key, priority),
                commit=True,
            )
            if cur.rowcount == 0:
                logger.debug(f"SLM queue dedup: {work_type} for {session_key}")
                return None
            await self._pool.execute(
                "UPDATE slm_queue_stats SET total_queued = total_queued + 1 WHERE id = 1",
                commit=True,
            )
            logger.debug(f"Queued {work_type} for {session_key}")
            return cur.lastrowid
        except Exception as e:
            logger.warning(f"SLM queue enqueue failed: {e}")
            return None

    # ── Dequeue / process ────────────────────────────────────────────

    async def dequeue_batch(self, limit: int = 5) -> list[WorkItem]:
        """Claim up to *limit* pending items for processing."""
        rows = await self._pool.fetchall(
            """SELECT id, work_type, status, priority, payload,
                      conversation_ts, queued_at, started_at,
                      attempts, max_attempts, session_key, last_error
               FROM slm_work_queue
               WHERE status IN ('pending', 'failed') AND attempts < max_attempts
               ORDER BY priority ASC, queued_at ASC
               LIMIT ?""",
            (limit,),
        )
        items: list[WorkItem] = []
        now = time.time()
        for r in rows:
            items.append(WorkItem(
                id=r[0], work_type=r[1], status=r[2], priority=r[3],
                payload=json.loads(r[4]), conversation_ts=r[5],
                queued_at=r[6], started_at=r[7], attempts=r[8],
                max_attempts=r[9], session_key=r[10], last_error=r[11],
            ))
        if items:
            placeholders = ",".join("?" * len(items))
            item_ids = [i.id for i in items]
            await self._pool.execute(
                f"UPDATE slm_work_queue SET status='processing', started_at=?, "
                f"attempts=attempts+1 WHERE id IN ({placeholders})",
                (now, *item_ids), commit=True,
            )
        return items

    async def mark_completed(self, work_id: int) -> None:
        await self._pool.execute(
            "UPDATE slm_work_queue SET status='completed', completed_at=? WHERE id=?",
            (time.time(), work_id), commit=True,
        )
        await self._pool.execute(
            "UPDATE slm_queue_stats SET total_processed = total_processed + 1 WHERE id = 1",
            commit=True,
        )

    async def mark_failed(self, work_id: int, error: str) -> None:
        await self._pool.execute(
            "UPDATE slm_work_queue SET status='failed', last_error=? WHERE id=?",
            (error[:500], work_id), commit=True,
        )
        await self._pool.execute(
            "UPDATE slm_queue_stats SET total_failed = total_failed + 1 WHERE id = 1",
            commit=True,
        )

    # ── Maintenance ──────────────────────────────────────────────────

    async def alert_abandoned(self) -> int:
        """Find items at max_attempts that will never be retried and fire alerts.

        Returns count of abandoned items found.
        """
        rows = await self._pool.fetchall(
            """SELECT id, work_type, session_key, last_error, attempts
               FROM slm_work_queue
               WHERE status = 'failed' AND attempts >= max_attempts
               LIMIT 20""",
        )
        if not rows:
            return 0

        try:
            from nanobot.copilot.alerting.bus import get_alert_bus
            bus = get_alert_bus()
            for r in rows:
                work_id, work_type, session_key, last_error, attempts = r
                await bus.alert(
                    "slm_queue", "medium",
                    f"Abandoned {work_type} (id={work_id}, session={session_key}, "
                    f"attempts={attempts}): {(last_error or 'unknown')[:100]}",
                    f"abandoned_{work_id}",
                )
        except Exception as e:
            logger.warning(f"SLM abandoned alert failed: {e}")

        logger.warning(f"SLM queue: {len(rows)} abandoned item(s) at max_attempts")
        return len(rows)

    async def reset_stuck(self, timeout_s: int = 300) -> int:
        """Reset items stuck in 'processing' longer than timeout."""
        cur = await self._pool.execute(
            "UPDATE slm_work_queue SET status='pending' "
            "WHERE status='processing' AND started_at < ?",
            (time.time() - timeout_s,), commit=True,
        )
        count = cur.rowcount
        if count:
            logger.warning(f"SLM queue: reset {count} stuck items")
        return count

    async def prune_completed(self, keep_hours: int = 24) -> int:
        """Delete completed/failed items older than keep_hours."""
        cur = await self._pool.execute(
            "DELETE FROM slm_work_queue "
            "WHERE status IN ('completed','failed') AND completed_at < ?",
            (time.time() - keep_hours * 3600,), commit=True,
        )
        return cur.rowcount

    async def pending_session_keys(self, work_type: str = "embedding") -> set[str]:
        """Session keys with pending/processing items of given type."""
        rows = await self._pool.fetchall(
            "SELECT DISTINCT session_key FROM slm_work_queue "
            "WHERE work_type=? AND status IN ('pending','processing')",
            (work_type,),
        )
        return {r[0] for r in rows}

    # ── Stats ────────────────────────────────────────────────────────

    async def size(self) -> int:
        row = await self._pool.fetchone(
            "SELECT COUNT(*) FROM slm_work_queue WHERE status IN ('pending','processing')"
        )
        return row[0] if row else 0

    async def stats(self) -> dict[str, Any]:
        row = await self._pool.fetchone("SELECT * FROM slm_queue_stats WHERE id = 1")
        if not row:
            return {}
        return {
            "total_queued": row[1],
            "total_processed": row[2],
            "total_failed": row[3],
            "total_dropped": row[4],
            "queue_size_limit": row[5],
            "last_drain_ts": row[6],
            "current_size": await self.size(),
        }

    async def breakdown(self) -> dict[str, int]:
        """Count pending items by work_type."""
        rows = await self._pool.fetchall(
            "SELECT work_type, COUNT(*) FROM slm_work_queue "
            "WHERE status IN ('pending', 'processing') GROUP BY work_type"
        )
        return {r[0]: r[1] for r in rows} if rows else {}

    async def update_drain_ts(self) -> None:
        await self._pool.execute(
            "UPDATE slm_queue_stats SET last_drain_ts = ? WHERE id = 1",
            (time.time(),), commit=True,
        )
