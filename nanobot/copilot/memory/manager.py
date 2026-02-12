"""Memory manager: orchestrates all three tiers (Redis, Qdrant, SQLite)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import aiosqlite
from loguru import logger

from nanobot.copilot.memory.embedder import Embedder
from nanobot.copilot.memory.episodic import Episode, EpisodicStore
from nanobot.copilot.memory.working import WorkingMemory


class MemoryManager:
    """Orchestrates Redis working memory, Qdrant episodic store, and SQLite structured items."""

    def __init__(
        self,
        embedder: Embedder,
        qdrant_url: str = "http://localhost:6333",
        redis_url: str = "redis://localhost:6379/0",
        db_path: str | Path = "data/sqlite/copilot.db",
        dimensions: int = 768,
    ):
        self._embedder = embedder
        self._episodic = EpisodicStore(embedder, qdrant_url, dimensions=dimensions)
        self._working = WorkingMemory(redis_url)
        self._db_path = str(db_path)

    async def initialize(self) -> None:
        """Connect to all backends."""
        await self._working.connect()
        try:
            await self._episodic._ensure_client()
        except Exception as e:
            logger.warning(f"Qdrant init failed (degraded mode): {e}")

    async def remember_exchange(
        self, user_msg: str, assistant_msg: str, session_key: str
    ) -> str:
        """Store a full user/assistant exchange as episodic memory."""
        combined = f"User: {user_msg}\nAssistant: {assistant_msg}"
        try:
            return await self._episodic.store(
                text=combined, session_key=session_key, role="exchange",
            )
        except Exception as e:
            logger.warning(f"Exchange storage failed: {e}")
            return ""

    async def remember_extractions(
        self, extractions: dict[str, Any], session_key: str
    ) -> list[str]:
        """Store extractions to both Qdrant + SQLite structured items."""
        ids = []
        try:
            ids = await self._episodic.store_extractions(extractions, session_key)
        except Exception as e:
            logger.warning(f"Extraction storage failed: {e}")

        # Also upsert into SQLite structured items
        for key in ("facts", "decisions", "entities"):
            for item in extractions.get(key, []):
                category = key.rstrip("s")
                await self._upsert_item(
                    category=category,
                    key=item[:100],
                    value=item,
                    session_key=session_key,
                    source="extraction",
                )
        return ids

    async def recall(
        self, query: str, session_key: str, limit: int = 5
    ) -> list[Episode]:
        """Check Redis cache first, then Qdrant."""
        # Check Redis cache
        cached = await self._working.get_cached_recall(session_key)
        if cached:
            return [Episode(**ep) for ep in cached[:limit]]

        episodes = await self._episodic.recall(query, limit=limit, session_key=session_key)

        # Cache the results
        if episodes:
            await self._working.cache_recall(
                session_key,
                [{"id": e.id, "text": e.text, "session_key": e.session_key,
                  "role": e.role, "timestamp": e.timestamp, "score": e.score}
                 for e in episodes],
            )
        return episodes

    async def proactive_recall(
        self, current_message: str, session_key: str, limit: int = 3
    ) -> str:
        """Anticipate needed context and format as injection block.

        Searches across all sessions for relevant memories.
        """
        episodes = await self._episodic.recall_global(current_message, limit=limit)
        if not episodes:
            return ""

        # Update working memory with topic/entities from recall
        if episodes:
            top_text = episodes[0].text
            await self._working.set_topic(session_key, top_text[:100])

        return self._format_for_injection(episodes)

    @staticmethod
    def _format_for_injection(episodes: list[Episode], budget_tokens: int = 800) -> str:
        """Format recalled episodes as context injection block."""
        if not episodes:
            return ""

        lines = ["## Recalled Memories"]
        total_chars = 0
        for ep in episodes:
            text = ep.text
            # Rough budget: 4 chars per token
            if total_chars + len(text) > budget_tokens * 4:
                text = text[:200] + "..."
            score_pct = int(ep.score * 100)
            lines.append(f"- [{score_pct}%] {text}")
            total_chars += len(text)
            if total_chars > budget_tokens * 4:
                break

        return "\n".join(lines)

    async def _upsert_item(
        self,
        category: str,
        key: str,
        value: str,
        session_key: str,
        source: str,
    ) -> None:
        """SQLite INSERT ON CONFLICT with confidence boost."""
        try:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    """INSERT INTO memory_items (category, key, value, session_key, source)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(category, key) DO UPDATE SET
                           value = excluded.value,
                           confidence = MIN(confidence + 0.1, 1.0),
                           access_count = access_count + 1,
                           updated_at = CURRENT_TIMESTAMP""",
                    (category, key, value, session_key, source),
                )
                await db.commit()
        except Exception as e:
            logger.warning(f"Memory item upsert failed: {e}")

    async def get_high_confidence_items(
        self, min_confidence: float = 0.6, limit: int = 20
    ) -> list[dict]:
        """Fetch high-confidence structured memory items."""
        try:
            async with aiosqlite.connect(self._db_path) as db:
                cursor = await db.execute(
                    """SELECT category, key, value, confidence, access_count
                       FROM memory_items WHERE confidence >= ?
                       ORDER BY confidence DESC LIMIT ?""",
                    (min_confidence, limit),
                )
                rows = await cursor.fetchall()
                cols = [d[0] for d in cursor.description]
                return [dict(zip(cols, row)) for row in rows]
        except Exception as e:
            logger.warning(f"Memory items query failed: {e}")
            return []

    async def health(self) -> dict[str, bool]:
        """Check health of all memory backends."""
        redis_ok = await self._working.health()
        qdrant_ok = False
        try:
            count = await self._episodic.count()
            qdrant_ok = True
        except Exception:
            pass
        return {"redis": redis_ok, "qdrant": qdrant_ok}
