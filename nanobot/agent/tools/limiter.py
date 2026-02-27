"""Registry-level resource limiter — wraps all tool executions with timeout + output truncation.

Also provides `log_guardrail_block()` for unified block observability across all guardrails.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from loguru import logger


async def log_guardrail_block(
    tool: str,
    reason: str,
    value: str | int | float,
    threshold: str | int | float,
) -> None:
    """Log a structured guardrail block event for observability.

    Called by any guardrail (allowlist, size limit, timeout) so the
    heartbeat/dream cycle can surface patterns and recommend config changes.
    """
    logger.warning(
        "Guardrail block: tool={tool} reason={reason} value={value} threshold={threshold}",
        tool=tool, reason=reason, value=value, threshold=threshold,
    )
    try:
        from nanobot.copilot.alerting.bus import get_alert_bus
        await get_alert_bus().alert(
            "guardrail", "medium",
            f"Guardrail blocked {tool}: {reason} (value={value}, limit={threshold})",
            f"guardrail_{tool}_{reason}",
        )
    except Exception:
        pass


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
            await log_guardrail_block(name, "timeout", f"{timeout}s", f"{timeout}s")
            return msg

        # Truncate output
        if len(result) > self._default_output_limit:
            await log_guardrail_block(name, "output_truncated", len(result), self._default_output_limit)
            result = (
                result[: self._default_output_limit]
                + f"\n... (truncated, {len(result) - self._default_output_limit} more chars)"
            )

        return result
