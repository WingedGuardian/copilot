"""n8n webhook integration tool."""

from __future__ import annotations

import os
from typing import Any

from nanobot.agent.tools.base import Tool


class N8NTool(Tool):
    """Tool for triggering n8n workflows via webhooks."""

    def __init__(self, base_url: str = "http://localhost:5678"):
        self._base_url = base_url.rstrip("/")

    @property
    def name(self) -> str:
        return "n8n"

    @property
    def description(self) -> str:
        return (
            "Interact with n8n workflow automation. "
            "Actions: 'trigger' (fire a webhook with payload), "
            "'list' (show registered workflows). "
            "All triggers require approval."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["trigger", "list"],
                    "description": "n8n action to perform",
                },
                "webhook_path": {
                    "type": "string",
                    "description": "Webhook path to trigger (e.g. '/webhook/my-workflow')",
                },
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST"],
                    "description": "HTTP method for webhook (default: POST)",
                },
                "payload": {
                    "type": "object",
                    "description": "JSON payload to send with the webhook",
                },
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "list")

        try:
            if action == "trigger":
                return await self._trigger(kwargs)
            elif action == "list":
                return await self._list()
            else:
                return f"Unknown n8n action: {action}"
        except Exception as e:
            return f"n8n error: {e}"

    async def _trigger(self, kwargs: dict) -> str:
        """Fire a webhook."""
        import httpx

        webhook_path = kwargs.get("webhook_path", "")
        if not webhook_path:
            return "Error: webhook_path required"

        method = kwargs.get("method", "POST").upper()
        payload = kwargs.get("payload", {})

        url = f"{self._base_url}{webhook_path}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            if method == "GET":
                r = await client.get(url, params=payload if isinstance(payload, dict) else {})
            else:
                r = await client.post(url, json=payload)

        body = r.text[:2000]
        return f"n8n webhook {method} {webhook_path}: HTTP {r.status_code}\n{body}"

    async def _list(self) -> str:
        """List registered n8n workflows."""
        import httpx

        api_key = os.environ.get("N8N_API_KEY", "")
        headers = {}
        if api_key:
            headers["X-N8N-API-KEY"] = api_key

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    f"{self._base_url}/api/v1/workflows",
                    headers=headers,
                )
                if r.status_code != 200:
                    return f"n8n API returned HTTP {r.status_code}: {r.text[:500]}"

                data = r.json()
                workflows = data.get("data", [])
                if not workflows:
                    return "No workflows found."

                lines = [f"n8n Workflows ({len(workflows)}):"]
                for wf in workflows[:30]:
                    active = "active" if wf.get("active") else "inactive"
                    lines.append(f"  [{wf.get('id')}] {wf.get('name')} ({active})")
                return "\n".join(lines)

        except httpx.ConnectError:
            return f"Cannot connect to n8n at {self._base_url}. Is it running?"
