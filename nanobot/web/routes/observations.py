"""Observations page — dream cycle observations with manual resolution."""
from __future__ import annotations

import aiohttp_jinja2
import aiosqlite
from aiohttp import web


@aiohttp_jinja2.template("pages/observations.html")
async def index(request: web.Request) -> dict:
    ctx = request.app.get("ctx", {})
    db_path = ctx.get("db_path", "")
    open_obs: list[dict] = []
    resolved_obs: list[dict] = []
    category_filter = request.query.get("category", "")

    if db_path:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row

            where_cat = "AND category = ?" if category_filter else ""
            params_open: tuple = (category_filter,) if category_filter else ()

            cur = await db.execute(
                f"""SELECT id, created_at, source, observation_type, category,
                          content, priority, status, expires_at
                   FROM dream_observations
                   WHERE status = 'open' {where_cat}
                   ORDER BY
                     CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
                     created_at DESC""",
                params_open,
            )
            open_obs = [dict(r) for r in await cur.fetchall()]

            cur = await db.execute(
                f"""SELECT id, created_at, source, observation_type, category,
                          content, priority, status, resolved_at, resolved_by,
                          resolution_note
                   FROM dream_observations
                   WHERE status != 'open' {where_cat}
                   ORDER BY resolved_at DESC
                   LIMIT 50""",
                params_open,
            )
            resolved_obs = [dict(r) for r in await cur.fetchall()]

    return {
        "active": "observations",
        "open_obs": open_obs,
        "resolved_obs": resolved_obs,
        "category_filter": category_filter,
    }


async def resolve_observation(request: web.Request) -> web.Response:
    """Resolve an observation with optional note."""
    obs_id = int(request.match_info["id"])
    data = await request.post()
    note = data.get("note", "")
    ctx = request.app.get("ctx", {})
    db_path = ctx.get("db_path", "")
    if db_path:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                """UPDATE dream_observations
                   SET status = 'resolved', resolved_at = CURRENT_TIMESTAMP,
                       resolved_by = 'user', resolution_note = ?
                   WHERE id = ? AND status = 'open'""",
                (note, obs_id),
            )
            await db.commit()
    raise web.HTTPSeeOther("/observations")


async def update_status(request: web.Request) -> web.Response:
    """Set observation to wont_fix or duplicate."""
    obs_id = int(request.match_info["id"])
    new_status = request.match_info["status"]
    if new_status not in ("wont_fix", "duplicate"):
        raise web.HTTPBadRequest(text="Invalid status")
    data = await request.post()
    note = data.get("note", "")
    ctx = request.app.get("ctx", {})
    db_path = ctx.get("db_path", "")
    if db_path:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                """UPDATE dream_observations
                   SET status = ?, resolved_at = CURRENT_TIMESTAMP,
                       resolved_by = 'user', resolution_note = ?
                   WHERE id = ? AND status = 'open'""",
                (new_status, note, obs_id),
            )
            await db.commit()
    raise web.HTTPSeeOther("/observations")


def setup(app: web.Application) -> None:
    app.router.add_get("/observations", index)
    app.router.add_post("/observations/{id}/resolve", resolve_observation)
    app.router.add_post("/observations/{id}/{status}", update_status)
