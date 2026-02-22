"""Routing page — routing log and preferences."""
from __future__ import annotations

import aiohttp_jinja2
import aiosqlite
from aiohttp import web


@aiohttp_jinja2.template("pages/routing.html")
async def index(request: web.Request) -> dict:
    ctx = request.app.get("ctx", {})
    db_path = ctx.get("db_path", "")

    routing_log: list[dict] = []
    routing_preferences: list[dict] = []
    pref_columns: list[str] = []

    if db_path:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row

            try:
                cur = await db.execute(
                    """SELECT id, timestamp, input_length, has_images, routed_to,
                              provider, model_used, route_reason, success,
                              latency_ms, failure_reason, cost_usd, thread_id
                       FROM routing_log
                       ORDER BY id DESC
                       LIMIT 50"""
                )
                routing_log = [dict(r) for r in await cur.fetchall()]
            except Exception:
                routing_log = []

            try:
                cur = await db.execute("SELECT * FROM routing_preferences ORDER BY rowid DESC LIMIT 100")
                rows = await cur.fetchall()
                if rows:
                    pref_columns = list(rows[0].keys())
                    routing_preferences = [dict(r) for r in rows]
            except Exception:
                routing_preferences = []
                pref_columns = []

    return {
        "active": "routing",
        "routing_log": routing_log,
        "routing_preferences": routing_preferences,
        "pref_columns": pref_columns,
    }


def setup(app: web.Application) -> None:
    app.router.add_get("/routing", index)
