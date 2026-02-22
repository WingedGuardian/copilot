"""Conversation thread tagging and topic tracking."""

import re
import time
from dataclasses import dataclass, field

from nanobot.copilot.extraction.schemas import ExtractionResult


def _slug(text: str, max_len: int = 30) -> str:
    """Convert text to a URL-safe slug."""
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:max_len]


@dataclass
class ThreadTracker:
    """Tracks the current conversation thread/topic.

    Topics shift either by explicit user command (``> TopicName``) or by
    the background extractor detecting a shift.
    """

    session_key: str = ""
    current_thread_id: str = ""
    current_thread_label: str = ""

    def _make_id(self, label: str) -> str:
        ts = str(int(time.time()))[-6:]  # last 6 digits
        return f"{self.session_key}:{ts}:{_slug(label)}"

    def check_message(self, content: str) -> tuple[str | None, str | None]:
        """Detect explicit topic override ``> TopicName``.

        Returns (thread_id, label) if found, else (None, None).
        Also strips the prefix from the message so downstream sees clean text.
        """
        match = re.match(r"^>\s*(.+?)(?:\n|$)", content)
        if not match:
            return None, None

        label = match.group(1).strip()
        thread_id = self._make_id(label)
        self.current_thread_id = thread_id
        self.current_thread_label = label
        return thread_id, label

    def strip_topic_prefix(self, content: str) -> str:
        """Remove the ``> TopicName`` prefix line from *content*."""
        return re.sub(r"^>[^\n]*\n?", "", content, count=1).strip()

    def update_from_extraction(
        self, extraction: ExtractionResult
    ) -> tuple[str | None, str | None]:
        """Update thread based on background extraction results.

        Returns (thread_id, label) if topic shifted, else (None, None).
        """
        if not extraction.topic_shift or not extraction.suggested_topic:
            return None, None

        label = extraction.suggested_topic
        thread_id = self._make_id(label)
        self.current_thread_id = thread_id
        self.current_thread_label = label
        return thread_id, label

    def get_current(self) -> tuple[str, str]:
        """Return (current_thread_id, current_thread_label)."""
        return self.current_thread_id, self.current_thread_label
