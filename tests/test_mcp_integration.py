"""Tests for MCP server integration (Phase 4B)."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from nanobot.agent.mcp.bridge import McpToolAdapter
from nanobot.agent.mcp.client import McpClient, McpServerConfig
from nanobot.agent.mcp.manager import McpManager
from nanobot.agent.tools.registry import ToolRegistry


# --- McpServerConfig ---


def test_config_from_dict_stdio():
    """Parse stdio config from dict."""
    cfg = McpServerConfig.from_dict("test", {
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home"],
    })
    assert cfg.name == "test"
    assert cfg.transport == "stdio"
    assert cfg.command == "npx"
    assert "-y" in cfg.args


def test_config_from_dict_sse():
    """Parse SSE config from dict."""
    cfg = McpServerConfig.from_dict("remote", {
        "transport": "sse",
        "url": "http://localhost:8080/mcp",
    })
    assert cfg.transport == "sse"
    assert cfg.url == "http://localhost:8080/mcp"


def test_config_defaults():
    """Config defaults to stdio transport."""
    cfg = McpServerConfig.from_dict("simple", {
        "command": "my-server",
    })
    assert cfg.transport == "stdio"
    assert cfg.args == []
    assert cfg.env == {}


# --- McpToolAdapter ---


@pytest.mark.asyncio
async def test_tool_adapter_schema():
    """McpToolAdapter produces correct OpenAI function schema."""
    tool_def = {
        "name": "read_file",
        "description": "Read a file from disk",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
            },
            "required": ["path"],
        },
    }
    mock_client = MagicMock()
    adapter = McpToolAdapter(
        tool_definition=tool_def,
        client=mock_client,
        server_name="filesystem",
    )

    assert adapter.name == "mcp_filesystem_read_file"
    assert adapter.description == "Read a file from disk"
    assert "path" in adapter.parameters.get("properties", {})


@pytest.mark.asyncio
async def test_tool_adapter_execute():
    """McpToolAdapter delegates execution to client.call_tool()."""
    tool_def = {
        "name": "read_file",
        "description": "Read a file",
        "inputSchema": {"type": "object", "properties": {}},
    }
    mock_client = AsyncMock()
    mock_client.call_tool = AsyncMock(return_value="file contents here")

    adapter = McpToolAdapter(
        tool_definition=tool_def,
        client=mock_client,
        server_name="fs",
    )

    result = await adapter.execute(path="/tmp/test.txt")
    mock_client.call_tool.assert_called_once_with("read_file", {"path": "/tmp/test.txt"})
    assert result == "file contents here"


@pytest.mark.asyncio
async def test_tool_adapter_handles_error():
    """McpToolAdapter returns error string on failure."""
    tool_def = {
        "name": "broken",
        "description": "A broken tool",
        "inputSchema": {"type": "object", "properties": {}},
    }
    mock_client = AsyncMock()
    mock_client.call_tool = AsyncMock(side_effect=RuntimeError("connection lost"))

    adapter = McpToolAdapter(
        tool_definition=tool_def,
        client=mock_client,
        server_name="test",
    )

    result = await adapter.execute()
    assert "error" in result.lower()
    assert "connection lost" in result


# --- McpClient ---


def test_client_init():
    """McpClient initializes from config."""
    cfg = McpServerConfig.from_dict("test", {
        "command": "my-server",
        "args": ["--port", "8080"],
    })
    client = McpClient(cfg)
    assert client.config.name == "test"
    assert not client.connected


# --- McpManager ---


def test_manager_parse_configs():
    """McpManager parses multiple server configs."""
    config = {
        "filesystem": {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@mcp/server-filesystem"],
        },
        "database": {
            "transport": "sse",
            "url": "http://localhost:3000/mcp",
        },
    }
    registry = ToolRegistry()
    manager = McpManager(config, registry)
    assert len(manager.configs) == 2
    assert "filesystem" in manager.configs
    assert "database" in manager.configs


@pytest.mark.asyncio
async def test_manager_connect_registers_tools():
    """McpManager connects to servers and registers tool adapters."""
    config = {
        "test_server": {
            "command": "fake-server",
        },
    }
    registry = ToolRegistry()
    manager = McpManager(config, registry)

    # Mock the client's connect and list_tools
    mock_client = AsyncMock()
    mock_client.connected = True
    mock_client.list_tools = AsyncMock(return_value=[
        {
            "name": "greet",
            "description": "Say hello",
            "inputSchema": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
            },
        },
    ])
    mock_client.config = McpServerConfig.from_dict("test_server", {"command": "fake"})

    # Inject mock
    manager._clients["test_server"] = mock_client

    await manager._register_tools_from_client("test_server", mock_client)

    assert registry.has("mcp_test_server_greet")


@pytest.mark.asyncio
async def test_manager_disconnect_unregisters():
    """McpManager unregisters tools when disconnecting."""
    config = {"srv": {"command": "fake"}}
    registry = ToolRegistry()
    manager = McpManager(config, registry)

    # Register a tool manually
    mock_client = AsyncMock()
    mock_client.disconnect = AsyncMock()
    mock_client.connected = True
    manager._clients["srv"] = mock_client
    manager._registered_tools["srv"] = ["mcp_srv_tool1"]

    # Register a fake tool in the registry
    from nanobot.agent.tools.dynamic import DynamicTool
    registry.register(DynamicTool(
        tool_name="mcp_srv_tool1",
        tool_description="test",
        tool_parameters={"type": "object", "properties": {}},
        code="result = 'x'",
    ))
    assert registry.has("mcp_srv_tool1")

    await manager.disconnect("srv")
    assert not registry.has("mcp_srv_tool1")


def test_manager_empty_config():
    """McpManager handles empty config gracefully."""
    registry = ToolRegistry()
    manager = McpManager({}, registry)
    assert len(manager.configs) == 0
