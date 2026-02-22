"""Costs page — LLM cost breakdown."""
from __future__ import annotations

from datetime import datetime, timedelta

import aiohttp_jinja2
import aiosqlite
from aiohttp import web


@aiohttp_jinja2.template("pages/costs.html")
async def index(request: web.Request) -> dict:
    ctx = request.app.get("ctx", {})
    db_path = ctx.get("db_path", "")
    range_param = request.rel_url.query.get("range", "today")

    # Calculate date filter for selected range
    now = datetime.utcnow()
    if range_param == "30d":
        since = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")
    elif range_param == "7d":
        since = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")
    else:  # today
        since = now.strftime("%Y-%m-%dT00:00:00")

    totals = {"today": 0.0, "week": 0.0, "month": 0.0}
    by_model: list[dict] = []

    if db_path:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            # Today total — cost_log uses "timestamp" column
            cur = await db.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) FROM cost_log WHERE timestamp >= ?",
                (now.strftime("%Y-%m-%dT00:00:00"),),
            )
            totals["today"] = (await cur.fetchone())[0] or 0.0

            # Week total
            cur = await db.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) FROM cost_log WHERE timestamp >= ?",
                ((now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S"),),
            )
            totals["week"] = (await cur.fetchone())[0] or 0.0

            # Month total
            cur = await db.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) FROM cost_log WHERE timestamp >= ?",
                ((now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S"),),
            )
            totals["month"] = (await cur.fetchone())[0] or 0.0

            # Per-model breakdown for selected range
            cur = await db.execute(
                """SELECT model,
                          COUNT(*) AS calls,
                          COALESCE(SUM(tokens_input), 0) AS tok_in,
                          COALESCE(SUM(tokens_output), 0) AS tok_out,
                          COALESCE(SUM(cost_usd), 0) AS cost
                   FROM cost_log
                   WHERE timestamp >= ?
                   GROUP BY model
                   ORDER BY cost DESC""",
                (since,),
            )
            by_model = [dict(r) for r in await cur.fetchall()]

    return {
        "active": "costs",
        "totals": totals,
        "by_model": by_model,
        "range": range_param,
    }


def setup(app: web.Application) -> None:
    app.router.add_get("/costs", index)
