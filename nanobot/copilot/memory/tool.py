"""Agent-accessible memory tool for search, store, and stats."""

from __future__ import annotations

from typing import Any

from nanobot.agent.tools.base import Tool


class MemoryTool(Tool):
    """Tool that gives the agent access to the memory system."""

    def __init__(self, memory_manager):
        self._manager = memory_manager

    @property
    def name(self) -> str:
        return "memory"

    @property
    def description(self) -> str:
        return (
            "Search, store, or query the memory system. "
            "Actions: 'search' (semantic search across memories), "
            "'store' (save a fact/preference), 'stats' (memory health)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["search", "store", "stats"],
                    "description": "Action to perform",
                },
                "query": {
                    "type": "string",
                    "description": "Search query (for 'search' action)",
                },
                "category": {
                    "type": "string",
                    "description": "Category for storing (preference, fact, entity)",
                },
                "content": {
                    "type": "string",
                    "description": "Content to store",
                },
                "session_key": {
                    "type": "string",
                    "description": "Session key for scoped search (optional)",
                },
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "search")

        if action == "search":
            query = kwargs.get("query", "")
            if not query:
                return "Error: 'query' is required for search action."
            session_key = kwargs.get("session_key")
            episodes = await self._manager.recall(query, session_key or "", limit=5)
            if not episodes:
                return "No memories found matching your query."
            lines = [f"Found {len(episodes)} memories:"]
            for ep in episodes:
                score_pct = int(ep.score * 100)
                text = ep.text[:200]
                lines.append(f"  [{score_pct}%] {text}")
            return "\n".join(lines)

        elif action == "store":
            content = kwargs.get("content", "")
            category = kwargs.get("category", "fact")
            if not content:
                return "Error: 'content' is required for store action."
            session_key = kwargs.get("session_key", "agent:direct")
            await self._manager._upsert_item(
                category=category,
                key=content[:100],
                value=content,
                session_key=session_key,
                source="agent",
            )
            return f"Stored {category}: {content[:100]}"

        elif action == "stats":
            health = await self._manager.health()
            episode_count = await self._manager._episodic.count()
            items = await self._manager.get_high_confidence_items(limit=5)
            lines = [
                f"Redis: {'connected' if health['redis'] else 'disconnected'}",
                f"Qdrant: {'connected' if health['qdrant'] else 'disconnected'}",
                f"Episodes: {episode_count}",
                f"High-confidence items: {len(items)}",
            ]
            return "\n".join(lines)

        return f"Unknown action: {action}"
