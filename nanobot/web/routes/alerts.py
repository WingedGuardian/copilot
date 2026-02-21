"""Alerts page — active and resolved alerts."""
from __future__ import annotations

import aiohttp_jinja2
import aiosqlite
from aiohttp import web


@aiohttp_jinja2.template("pages/alerts.html")
async def index(request: web.Request) -> dict:
    ctx = request.app.get("ctx", {})
    db_path = ctx.get("db_path", "")
    active_alerts: list[dict] = []
    resolved_alerts: list[dict] = []

    if db_path:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """SELECT id, timestamp, subsystem, severity, error_key, message, delivered
                   FROM alerts
                   WHERE resolved_at IS NULL
                   ORDER BY timestamp DESC"""
            )
            active_alerts = [dict(r) for r in await cur.fetchall()]

            cur = await db.execute(
                """SELECT id, timestamp, subsystem, severity, error_key, message,
                          delivered, resolved_at
                   FROM alerts
                   WHERE resolved_at IS NOT NULL
                   ORDER BY resolved_at DESC
                   LIMIT 50"""
            )
            resolved_alerts = [dict(r) for r in await cur.fetchall()]

    return {
        "active": "alerts",
        "active_alerts": active_alerts,
        "resolved_alerts": resolved_alerts,
    }


async def resolve_alert(request: web.Request) -> web.Response:
    """Manually resolve an active alert."""
    alert_id = int(request.match_info["id"])
    ctx = request.app.get("ctx", {})
    db_path = ctx.get("db_path", "")
    if db_path:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "UPDATE alerts SET resolved_at = CURRENT_TIMESTAMP WHERE id = ? AND resolved_at IS NULL",
                (alert_id,),
            )
            await db.commit()
    raise web.HTTPSeeOther("/alerts")


def setup(app: web.Application) -> None:
    app.router.add_get("/alerts", index)
    app.router.add_post("/alerts/{id}/resolve", resolve_alert)
