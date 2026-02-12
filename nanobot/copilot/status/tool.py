"""Agent-accessible status tool."""

from __future__ import annotations

from typing import Any

from nanobot.agent.tools.base import Tool


class StatusTool(Tool):
    """Provides system status dashboard via tool interface."""

    def __init__(self, aggregator):
        self._aggregator = aggregator

    @property
    def name(self) -> str:
        return "status"

    @property
    def description(self) -> str:
        return (
            "Get system status dashboard showing health of all subsystems, "
            "cost analytics, memory stats, and channel status. "
            "Responds to /status, 'system status', 'how are you doing'."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "enum": ["all", "health", "cost", "memory"],
                    "description": "Which section to show (default: all)",
                },
            },
        }

    async def execute(self, **kwargs: Any) -> str:
        try:
            report = await self._aggregator.collect()
            return report.to_text()
        except Exception as e:
            return f"Status collection failed: {e}"
