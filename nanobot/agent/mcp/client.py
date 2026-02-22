"""MCP client — connects to MCP servers via stdio or SSE transport."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from loguru import logger


@dataclass
class McpServerConfig:
    """Configuration for a single MCP server."""

    name: str
    transport: str = "stdio"  # "stdio" or "sse"
    command: str = ""  # For stdio: command to launch
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str = ""  # For SSE: endpoint URL

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> McpServerConfig:
        """Parse config from a dict (e.g. from nanobot.toml/config.json)."""
        return cls(
            name=name,
            transport=data.get("transport", "stdio"),
            command=data.get("command", ""),
            args=data.get("args", []),
            env=data.get("env", {}),
            url=data.get("url", ""),
        )


class McpClient:
    """Client for a single MCP server.

    Manages the connection lifecycle and provides methods to list tools
    and call tools via the MCP protocol (JSON-RPC over stdio or SSE).

    Uses asyncio.create_subprocess_exec (argument-list based, no shell)
    for stdio transport to safely launch MCP server processes.
    """

    def __init__(self, config: McpServerConfig):
        self.config = config
        self._process: asyncio.subprocess.Process | None = None
        self._connected = False
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        """Connect to the MCP server."""
        if self.config.transport == "stdio":
            await self._connect_stdio()
        elif self.config.transport == "sse":
            await self._connect_sse()
        else:
            raise ValueError(f"Unknown transport: {self.config.transport}")

    async def _connect_stdio(self) -> None:
        """Launch subprocess and connect via stdin/stdout.

        Uses asyncio.create_subprocess_exec which takes arguments as a
        list (not a shell string), preventing command injection.
        """
        if not self.config.command:
            raise ValueError(f"No command specified for stdio server '{self.config.name}'")

        cmd = [self.config.command] + self.config.args
        env = dict(self.config.env) if self.config.env else None

        logger.info(f"MCP: starting {self.config.name}: {' '.join(cmd)}")
        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        # Start reader task
        self._reader_task = asyncio.create_task(self._read_loop())

        # Send initialize request
        result = await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "nanobot", "version": "0.1.0"},
        })
        logger.info(f"MCP: {self.config.name} initialized: {json.dumps(result)[:200]}")

        # Send initialized notification
        await self._send_notification("notifications/initialized", {})
        self._connected = True

    async def _connect_sse(self) -> None:
        """Connect via SSE transport (placeholder for future implementation)."""
        logger.warning(
            f"MCP: SSE transport for '{self.config.name}' not yet implemented. "
            "Use stdio transport for now."
        )
        raise NotImplementedError("SSE transport not yet implemented")

    async def disconnect(self) -> None:
        """Disconnect from the MCP server."""
        self._connected = False

        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):
                pass
            self._reader_task = None

        if self._process:
            try:
                self._process.stdin.close()
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except Exception as e:
                logger.warning(f"MCP: error stopping {self.config.name}: {e}")
                self._process.kill()
            self._process = None

        logger.info(f"MCP: disconnected from {self.config.name}")

    async def list_tools(self) -> list[dict[str, Any]]:
        """Get the list of tools from the server."""
        result = await self._send_request("tools/list", {})
        return result.get("tools", [])

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Call a tool on the server and return the text result."""
        result = await self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })

        # Extract text from content array
        content = result.get("content", [])
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(item.get("text", ""))
                elif item.get("type") == "image":
                    parts.append("[image]")
                else:
                    parts.append(json.dumps(item))
            elif isinstance(item, str):
                parts.append(item)

        return "\n".join(parts) if parts else json.dumps(result)

    async def _send_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC request and wait for the response."""
        if not self._process or not self._process.stdin:
            raise RuntimeError(f"Not connected to {self.config.name}")

        self._request_id += 1
        req_id = self._request_id

        request = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }

        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = future

        line = json.dumps(request) + "\n"
        self._process.stdin.write(line.encode())
        await self._process.stdin.drain()

        try:
            result = await asyncio.wait_for(future, timeout=30.0)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise RuntimeError(f"MCP request timed out: {method}")

        if "error" in result:
            err = result["error"]
            raise RuntimeError(f"MCP error: {err.get('message', err)}")

        return result.get("result", {})

    async def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        if not self._process or not self._process.stdin:
            return

        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        line = json.dumps(notification) + "\n"
        self._process.stdin.write(line.encode())
        await self._process.stdin.drain()

    async def _read_loop(self) -> None:
        """Read JSON-RPC responses from stdout."""
        if not self._process or not self._process.stdout:
            return

        try:
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    break

                line_str = line.decode().strip()
                if not line_str:
                    continue

                try:
                    msg = json.loads(line_str)
                except json.JSONDecodeError:
                    continue

                # Match response to pending request
                msg_id = msg.get("id")
                if msg_id is not None and msg_id in self._pending:
                    self._pending.pop(msg_id).set_result(msg)
                # Notifications from server (no id) — log and ignore
                elif "method" in msg:
                    logger.debug(f"MCP notification from {self.config.name}: {msg.get('method')}")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"MCP reader error for {self.config.name}: {e}")
        finally:
            self._connected = False
            # Resolve all pending futures with errors
            for req_id, future in list(self._pending.items()):
                if not future.done():
                    future.set_exception(
                        RuntimeError(f"MCP connection to {self.config.name} lost")
                    )
            self._pending.clear()
            logger.warning(f"MCP: {self.config.name} read loop ended, marked disconnected")
