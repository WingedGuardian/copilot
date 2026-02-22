"""Agent tool for creating and managing routing plans."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.agent.tools.base import Tool


class PlanRoutingTool(Tool):
    """Create or update the routing plan for conversations.

    The LLM uses this tool to propose, validate, and activate a routing plan.
    A mandatory safety net is always appended automatically by the router.
    """

    def __init__(self, router: Any, config_path: Path, copilot_config: Any):
        self._router = router
        self._config_path = config_path
        self._copilot = copilot_config

    @property
    def name(self) -> str:
        return "plan_routing"

    @property
    def description(self) -> str:
        return (
            "Create or update the routing plan for conversations. "
            "Pass a list of provider/model entries in order of preference. "
            "The system will pre-flight test each entry (API probe) and report "
            "which ones work. A mandatory safety net is always appended automatically. "
            "Use action='propose' to validate without activating. "
            "Use action='activate' to activate a validated plan. "
            "Use action='show' to see the current plan. "
            "Use action='clear' to revert to default routing."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "One of: propose, activate, show, clear",
                    "enum": ["propose", "activate", "show", "clear"],
                },
                "plan": {
                    "type": "array",
                    "description": "List of routing entries (for propose/activate). "
                    "Each entry: {provider: string, model: string, reason: string}",
                    "items": {
                        "type": "object",
                        "properties": {
                            "provider": {"type": "string"},
                            "model": {"type": "string"},
                            "reason": {"type": "string"},
                        },
                        "required": ["provider", "model"],
                    },
                },
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "")
        plan = kwargs.get("plan", [])

        if action == "show":
            return self._show()
        elif action == "clear":
            return await self._clear()
        elif action == "propose":
            return await self._propose(plan)
        elif action == "activate":
            return await self._activate(plan)
        else:
            return f"Error: unknown action '{action}'. Use: propose, activate, show, clear"

    def _show(self) -> str:
        """Show the current routing plan."""
        plan = self._router._routing_plan if self._router else []
        if not plan:
            default = getattr(self._router, "_default_model", "?")
            return f"No routing plan configured. Using default: {default} on all cloud providers."

        lines = ["Current routing plan:"]
        for i, entry in enumerate(plan, 1):
            reason = entry.get("reason", "")
            lines.append(
                f"  {i}. {entry.get('provider', '?')}: {entry.get('model', '?')}"
                + (f" — {reason}" if reason else "")
            )

        lines.append("\nMandatory safety net (always appended):")
        lkw = getattr(self._router, "_last_known_working", None)
        if lkw:
            lines.append(f"  1. Last working: {lkw[0]} / {lkw[1]}")
        lines.append("  2. LM Studio local (when online)")
        em = getattr(self._router, "_emergency_cloud_model", "?")
        lines.append(f"  3. Emergency: {em} on all providers")
        return "\n".join(lines)

    async def _propose(self, plan: list[dict]) -> str:
        """Validate plan entries with API probes."""
        if not plan:
            return "Error: 'plan' is required for propose action."

        if not self._router or not hasattr(self._router, "_cloud"):
            return "Error: router not available."

        cloud = self._router._cloud
        results = []

        for entry in plan:
            provider_name = entry.get("provider", "")
            model = entry.get("model", "")
            reason = entry.get("reason", "")

            if provider_name not in cloud:
                results.append({
                    "provider": provider_name, "model": model,
                    "status": "failed", "error": f"Provider '{provider_name}' not configured",
                })
                continue

            provider = cloud[provider_name]
            start = time.time()
            try:
                resp = await asyncio.wait_for(
                    provider.chat(
                        messages=[{"role": "user", "content": "hi"}],
                        model=model,
                        max_tokens=1,
                    ),
                    timeout=10,
                )
                latency_ms = int((time.time() - start) * 1000)
                # Check for error responses
                if resp.content and resp.content.startswith("Error calling LLM:"):
                    results.append({
                        "provider": provider_name, "model": model,
                        "status": "failed", "error": resp.content[:200],
                        "latency_ms": latency_ms,
                    })
                else:
                    results.append({
                        "provider": provider_name, "model": model,
                        "status": "ok", "latency_ms": latency_ms,
                    })
            except asyncio.TimeoutError:
                results.append({
                    "provider": provider_name, "model": model,
                    "status": "failed", "error": "Timeout (10s)",
                })
            except Exception as e:
                latency_ms = int((time.time() - start) * 1000)
                results.append({
                    "provider": provider_name, "model": model,
                    "status": "failed", "error": str(e)[:200],
                    "latency_ms": latency_ms,
                })

        lines = ["Probe results:"]
        for r in results:
            status = r["status"].upper()
            latency = f" ({r.get('latency_ms', '?')}ms)" if r.get("latency_ms") else ""
            error = f" — {r.get('error', '')}" if r.get("error") else ""
            lines.append(f"  {r['provider']}/{r['model']}: {status}{latency}{error}")

        ok_count = sum(1 for r in results if r["status"] == "ok")
        lines.append(f"\n{ok_count}/{len(results)} providers passed. "
                      "Use action='activate' with the same plan to enable it.")
        return "\n".join(lines)

    async def _activate(self, plan: list[dict]) -> str:
        """Activate a routing plan."""
        if not plan:
            return "Error: 'plan' is required for activate action."

        if not self._router:
            return "Error: router not available."

        # Validate structure
        for entry in plan:
            if not entry.get("provider") or not entry.get("model"):
                return f"Error: each plan entry needs 'provider' and 'model'. Invalid: {entry}"

        self._router.set_routing_plan(plan)

        # Persist to config
        self._copilot.routing_plan = plan
        self._persist_plan(plan)

        lines = [f"Routing plan activated ({len(plan)} entries):"]
        for i, entry in enumerate(plan, 1):
            lines.append(f"  {i}. {entry['provider']}: {entry['model']}")
        return "\n".join(lines)

    async def _clear(self) -> str:
        """Clear the routing plan, revert to default."""
        if self._router:
            self._router.set_routing_plan([])

        self._copilot.routing_plan = []
        self._persist_plan([])

        default = getattr(self._router, "_default_model", "?") if self._router else "?"
        return f"Routing plan cleared. Reverted to default: {default} on all cloud providers."

    def _persist_plan(self, plan: list[dict]) -> None:
        """Persist routing plan to config.json."""
        try:
            if not self._config_path.exists():
                return
            with open(self._config_path) as f:
                data = json.load(f)
            copilot = data.setdefault("copilot", {})
            copilot["routingPlan"] = plan
            with open(self._config_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to persist routing plan: {e}")
