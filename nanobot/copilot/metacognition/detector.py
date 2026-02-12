"""Satisfaction detector: regex + extraction-based sentiment analysis."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from nanobot.copilot.metacognition.lessons import LessonManager

# Pre-compiled patterns for fast inline checks
_NEGATIVE_RE = re.compile(
    r"try again|that'?s wrong|no that'?s not|you'?re wrong|not what i asked"
    r"|terrible|awful|useless|wrong answer|completely wrong|that sucks",
    re.IGNORECASE,
)
_POSITIVE_RE = re.compile(
    r"perfect|thanks|great|exactly|well done|nice|good job|that'?s right"
    r"|awesome|brilliant|love it|nailed it",
    re.IGNORECASE,
)


class SatisfactionDetector:
    """Detects user satisfaction signals from messages and extraction results."""

    def __init__(self, lesson_manager: LessonManager | None):
        self._lesson_manager = lesson_manager
        self._recently_applied: list[int] = []  # lesson IDs applied in current exchange

    def detect_regex(self, text: str) -> tuple[str, float] | None:
        """Fast regex check for obvious satisfaction/dissatisfaction signals.

        Returns ``("positive", confidence)`` or ``("negative", confidence)`` or None.
        """
        if _NEGATIVE_RE.search(text):
            return ("negative", 0.9)
        if _POSITIVE_RE.search(text):
            return ("positive", 0.8)
        return None

    def note_applied_lessons(self, lesson_ids: list[int]) -> None:
        """Track which lessons were injected for the current exchange."""
        self._recently_applied = list(lesson_ids)

    async def handle_signal(
        self, signal: tuple[str, float], session_key: str
    ) -> None:
        """Process a detected satisfaction signal."""
        polarity, confidence = signal
        if not self._lesson_manager:
            return

        if polarity == "positive" and self._recently_applied:
            for lid in self._recently_applied:
                await self._lesson_manager.mark_helpful(lid)
            logger.debug(f"Reinforced {len(self._recently_applied)} lessons from positive signal")
        self._recently_applied = []

    async def on_extraction_result(
        self,
        session_key: str,
        result,
        last_user_msg: str = "",
        last_assistant_msg: str = "",
    ) -> None:
        """Called by background extractor's on_result callback chain.

        Checks extraction sentiment and creates lessons for negative outcomes.
        """
        if not self._lesson_manager:
            return

        sentiment = getattr(result, "sentiment", None) or result.get("sentiment", "neutral") if isinstance(result, dict) else getattr(result, "sentiment", "neutral")

        if sentiment in ("negative", "frustrated"):
            trigger = last_user_msg[:100] if last_user_msg else session_key
            await self._lesson_manager.create_lesson(
                trigger_pattern=trigger,
                lesson_text=f"Previous response was unsatisfactory. Context: {trigger}",
                source="dissatisfaction",
                category="general",
                confidence=0.5,
            )
            logger.info(f"Created lesson from {sentiment} sentiment in {session_key}")

        elif sentiment == "positive" and self._recently_applied:
            for lid in self._recently_applied:
                await self._lesson_manager.mark_helpful(lid)
            self._recently_applied = []
