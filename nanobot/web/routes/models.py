"""Models page — model tier assignments and routing log."""
from __future__ import annotations

import aiohttp_jinja2
import aiosqlite
from aiohttp import web


@aiohttp_jinja2.template("pages/models.html")
async def index(request: web.Request) -> dict:
    ctx = request.app.get("ctx", {})
    config = ctx.get("config")
    db_path = ctx.get("db_path", "")

    # Model tier assignments from CopilotConfig
    model_tiers: dict[str, str] = {}
    if config and hasattr(config, "copilot"):
        c = config.copilot
        model_tiers = {
            "Local": c.local_model,
            "Routing": c.routing_model,
            "Fast": c.fast_model,
            "Big": c.big_model,
            "Default Conversation": c.default_conversation_model,
            "Dream": c.dream_model,
            "Heartbeat": c.resolved_heartbeat_model,
            "Weekly Review": c.resolved_weekly_model,
            "Monthly Review": c.resolved_monthly_model,
            "Navigator": c.resolved_navigator_model,
            "Decomposition": c.resolved_decomposition_model,
            "Emergency": c.emergency_cloud_model,
        }

    # routing_log columns: id, timestamp, input_length, has_images, routed_to,
    #   provider, model_used, route_reason, success, latency_ms,
    #   failure_reason, cost_usd, thread_id
    routing_log: list[dict] = []
    if db_path:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """SELECT id, timestamp, routed_to, provider, model_used,
                          route_reason, success, latency_ms, cost_usd
                   FROM routing_log
                   ORDER BY timestamp DESC
                   LIMIT 20"""
            )
            routing_log = [dict(r) for r in await cur.fetchall()]

    return {
        "active": "models",
        "model_tiers": model_tiers,
        "routing_log": routing_log,
    }


def setup(app: web.Application) -> None:
    app.router.add_get("/models", index)
