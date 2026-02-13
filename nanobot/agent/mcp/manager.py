"""McpManager — manages multiple MCP server connections."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from loguru import logger

from nanobot.agent.mcp.client import McpClient, McpServerConfig
from nanobot.agent.mcp.bridge import McpToolAdapter

if TYPE_CHECKING:
    from nanobot.agent.tools.registry import ToolRegistry


class McpManager:
    """Manages MCP server connections and bridges their tools into the registry.

    Usage::

        manager = McpManager(config_dict, registry)
        await manager.connect_all()
        # Tools are now registered and available
        await manager.disconnect_all()
    """

    def __init__(
        self,
        mcp_config: dict[str, dict[str, Any]],
        registry: ToolRegistry,
    ):
        self._registry = registry
        self.configs: dict[str, McpServerConfig] = {}
        self._clients: dict[str, McpClient] = {}
        self._registered_tools: dict[str, list[str]] = {}  # server → tool names

        for name, cfg_dict in mcp_config.items():
            self.configs[name] = McpServerConfig.from_dict(name, cfg_dict)

    async def connect_all(self) -> dict[str, int]:
        """Connect to all configured MCP servers.

        Returns dict of server_name → number of tools registered.
        """
        results: dict[str, int] = {}

        for name, config in self.configs.items():
            try:
                client = McpClient(config)
                await client.connect()
                self._clients[name] = client
                count = await self._register_tools_from_client(name, client)
                results[name] = count
                logger.info(f"MCP: {name} connected, {count} tools registered")
            except Exception as e:
                logger.warning(f"MCP: failed to connect to {name}: {e}")
                results[name] = 0

        return results

    async def _register_tools_from_client(
        self, server_name: str, client: McpClient
    ) -> int:
        """Fetch tools from a connected client and register them."""
        tools = await client.list_tools()
        registered: list[str] = []

        for tool_def in tools:
            adapter = McpToolAdapter(
                tool_definition=tool_def,
                client=client,
                server_name=server_name,
            )
            self._registry.register(adapter)
            registered.append(adapter.name)
            logger.debug(f"MCP: registered tool {adapter.name}")

        self._registered_tools[server_name] = registered
        return len(registered)

    async def disconnect(self, server_name: str) -> None:
        """Disconnect from a specific server and unregister its tools."""
        # Unregister tools
        for tool_name in self._registered_tools.get(server_name, []):
            self._registry.unregister(tool_name)

        self._registered_tools.pop(server_name, None)

        # Disconnect client
        client = self._clients.pop(server_name, None)
        if client:
            await client.disconnect()

        logger.info(f"MCP: {server_name} disconnected, tools unregistered")

    async def disconnect_all(self) -> None:
        """Disconnect from all MCP servers."""
        for name in list(self._clients.keys()):
            await self.disconnect(name)

    def get_server_status(self) -> dict[str, dict[str, Any]]:
        """Get status of all configured servers."""
        status: dict[str, dict[str, Any]] = {}
        for name in self.configs:
            client = self._clients.get(name)
            status[name] = {
                "connected": client.connected if client else False,
                "transport": self.configs[name].transport,
                "tools": self._registered_tools.get(name, []),
            }
        return status
