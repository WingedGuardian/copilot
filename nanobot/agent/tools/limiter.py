"""Registry-level resource limiter — wraps all tool executions with timeout + output truncation."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from loguru import logger


class ResourceLimitingWrapper:
    """Wraps tool execution with wall-clock timeout and output truncation."""

    def __init__(
        self,
        default_timeout: int = 60,
        default_output_limit: int = 50_000,
        tool_timeouts: dict[str, int] | None = None,
    ):
        self._default_timeout = default_timeout
        self._default_output_limit = default_output_limit
        self._tool_timeouts = tool_timeouts or {}

    async def execute_with_limits(
        self,
        original_execute: Callable[..., Awaitable[str]],
        name: str,
        params: dict[str, Any],
    ) -> str:
        """Run a tool's execute() with timeout and output truncation."""
        timeout = self._tool_timeouts.get(name, self._default_timeout)

        try:
            result = await asyncio.wait_for(
                original_execute(**params),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            msg = f"Error: Tool '{name}' timed out after {timeout}s"
            logger.warning(msg)
            try:
                from nanobot.copilot.alerting.bus import get_alert_bus
                await get_alert_bus().alert(
                    "tools", "high", msg, f"tool_timeout_{name}",
                )
            except Exception:
                pass
            return msg

        # Truncate output
        if len(result) > self._default_output_limit:
            result = (
                result[: self._default_output_limit]
                + f"\n... (truncated, {len(result) - self._default_output_limit} more chars)"
            )

        return result
