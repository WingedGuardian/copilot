"""Memory system: MEMORY.md scratchpad + HISTORY.md fallback log."""

from pathlib import Path

from nanobot.utils.helpers import ensure_dir


class MemoryStore:
    """MEMORY.md (lean scratchpad) + HISTORY.md (non-copilot fallback log).

    In copilot mode, session summaries go to FTS5+Qdrant via MemoryManager.store_fact().
    HISTORY.md is only used as fallback when MemoryManager is unavailable.
    """

    def __init__(self, workspace: Path):
        self.memory_dir = ensure_dir(workspace / "memory")
        self.memory_file = self.memory_dir / "MEMORY.md"
        self.history_file = self.memory_dir / "HISTORY.md"

    def read_long_term(self) -> str:
        if self.memory_file.exists():
            return self.memory_file.read_text(encoding="utf-8")
        return ""

    def append_history(self, entry: str) -> None:
        with open(self.history_file, "a", encoding="utf-8") as f:
            f.write(entry.rstrip() + "\n\n")

    def get_memory_context(self) -> str:
        long_term = self.read_long_term()
        return f"## Long-term Memory\n{long_term}" if long_term else ""
