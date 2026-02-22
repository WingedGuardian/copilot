"""McpToolAdapter — wraps an MCP server tool as a nanobot Tool."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from loguru import logger

from nanobot.agent.tools.base import Tool

if TYPE_CHECKING:
    from nanobot.agent.mcp.client import McpClient


class McpToolAdapter(Tool):
    """Wraps a tool from an MCP server as a nanobot Tool.

    The tool name is prefixed with ``mcp_{server_name}_`` to avoid
    conflicts with built-in tools.
    """

    def __init__(
        self,
        tool_definition: dict[str, Any],
        client: McpClient,
        server_name: str,
    ):
        self._tool_def = tool_definition
        self._client = client
        self._server_name = server_name

        # Build prefixed name
        raw_name = tool_definition.get("name", "unknown")
        self._name = f"mcp_{server_name}_{raw_name}"
        self._raw_name = raw_name
        self._description = tool_definition.get("description", "")
        self._parameters = tool_definition.get("inputSchema", {
            "type": "object",
            "properties": {},
        })

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._parameters

    async def execute(self, **kwargs: Any) -> str:
        """Execute the MCP tool by calling the server."""
        try:
            result = await self._client.call_tool(self._raw_name, kwargs)
            return result
        except Exception as e:
            logger.error(f"MCP tool {self._name} failed: {e}")
            return f"Error calling MCP tool {self._raw_name}: {e}"
