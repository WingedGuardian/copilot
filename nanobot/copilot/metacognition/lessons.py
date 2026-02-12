"""Lesson manager: CRUD, relevance matching, lifecycle for self-improvement."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import aiosqlite
from loguru import logger


@dataclass
class Lesson:
    """A single learned lesson."""

    id: int
    trigger_pattern: str
    lesson_text: str
    confidence: float
    source: str
    category: str
    active: bool
    applied_count: int
    helpful_count: int


class LessonManager:
    """CRUD + relevance scoring for lessons stored in SQLite."""

    def __init__(self, db_path: str | Path):
        self._db_path = str(db_path)

    async def create_lesson(
        self,
        trigger_pattern: str,
        lesson_text: str,
        source: str = "system",
        category: str = "general",
        confidence: float = 0.5,
    ) -> Lesson:
        """Create a new lesson or reinforce an existing similar one."""
        async with aiosqlite.connect(self._db_path) as db:
            # Check for existing similar lesson (substring match)
            cursor = await db.execute(
                "SELECT id FROM lessons WHERE active = 1 AND trigger_pattern LIKE ? LIMIT 1",
                (f"%{trigger_pattern[:60]}%",),
            )
            row = await cursor.fetchone()
            if row:
                await self.reinforce(row[0])
                logger.debug(f"Reinforced existing lesson {row[0]} instead of creating new")
                return await self._get_by_id(db, row[0])

            await db.execute(
                """INSERT INTO lessons
                   (trigger_pattern, lesson_text, confidence, source, category)
                   VALUES (?, ?, ?, ?, ?)""",
                (trigger_pattern, lesson_text, confidence, source, category),
            )
            await db.commit()
            lesson_id = (await (await db.execute("SELECT last_insert_rowid()")).fetchone())[0]
            logger.info(f"Created lesson {lesson_id}: {lesson_text[:80]}")
            return await self._get_by_id(db, lesson_id)

    async def get_relevant_lessons(
        self, context_text: str, limit: int = 3, min_confidence: float = 0.30
    ) -> list[Lesson]:
        """Fetch active lessons scored by keyword overlap with context."""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT * FROM lessons WHERE active = 1 AND confidence >= ?",
                (min_confidence,),
            )
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description]

        if not rows:
            return []

        context_words = set(context_text.lower().split())
        scored: list[tuple[float, dict]] = []
        for row in rows:
            row_dict = dict(zip(cols, row))
            trigger = (row_dict.get("trigger_pattern") or "").lower()
            trigger_words = set(trigger.split())
            overlap = len(context_words & trigger_words)
            if overlap > 0 or not trigger_words:
                score = overlap + row_dict.get("confidence", 0.5)
                scored.append((score, row_dict))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [self._row_to_lesson(r) for _, r in scored[:limit]]

    async def reinforce(self, lesson_id: int, delta: float = 0.05) -> None:
        """Bump confidence and increment reinforcement_count."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """UPDATE lessons
                   SET confidence = MIN(confidence + ?, 1.0),
                       reinforcement_count = reinforcement_count + 1
                   WHERE id = ?""",
                (delta, lesson_id),
            )
            await db.commit()

    async def penalize(self, lesson_id: int, delta: float = 0.10) -> None:
        """Reduce confidence. Deactivate if low confidence and well-tested."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE lessons SET confidence = MAX(confidence - ?, 0.0) WHERE id = ?",
                (delta, lesson_id),
            )
            # Deactivate if confidence < 0.30 and applied enough times
            await db.execute(
                """UPDATE lessons SET active = 0
                   WHERE id = ? AND confidence < 0.30 AND applied_count >= 5""",
                (lesson_id,),
            )
            await db.commit()

    async def mark_applied(self, lesson_id: int) -> None:
        """Increment applied_count and update last_applied."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """UPDATE lessons
                   SET applied_count = applied_count + 1,
                       last_applied = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (lesson_id,),
            )
            await db.commit()

    async def mark_helpful(self, lesson_id: int) -> None:
        """Increment helpful_count and reinforce."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE lessons SET helpful_count = helpful_count + 1 WHERE id = ?",
                (lesson_id,),
            )
            await db.commit()
        await self.reinforce(lesson_id)

    @staticmethod
    def format_for_injection(lessons: list[Lesson]) -> str:
        """Format lessons as a markdown block for system prompt injection."""
        if not lessons:
            return ""
        lines = ["## Active Lessons"]
        for lesson in lessons:
            pct = int(lesson.confidence * 100)
            lines.append(f"- [{pct}%] {lesson.lesson_text}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_by_id(self, db: aiosqlite.Connection, lesson_id: int) -> Lesson:
        cursor = await db.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,))
        row = await cursor.fetchone()
        cols = [d[0] for d in cursor.description]
        return self._row_to_lesson(dict(zip(cols, row)))

    @staticmethod
    def _row_to_lesson(row: dict) -> Lesson:
        return Lesson(
            id=row["id"],
            trigger_pattern=row.get("trigger_pattern", ""),
            lesson_text=row.get("lesson_text", ""),
            confidence=row.get("confidence", 0.5),
            source=row.get("source", "system"),
            category=row.get("category", "general"),
            active=bool(row.get("active", 1)),
            applied_count=row.get("applied_count", 0),
            helpful_count=row.get("helpful_count", 0),
        )
