"""Autonomy permission editor."""
from __future__ import annotations

import logging

import aiohttp_jinja2
import aiosqlite
from aiohttp import web

logger = logging.getLogger(__name__)

PERMISSION_MODES = ["disabled", "notify", "autonomous"]


@aiohttp_jinja2.template("pages/autonomy.html")
async def get_autonomy(request: web.Request) -> dict:
    ctx = request.app.get("ctx", {})
    db_path = ctx.get("db_path", "")
    permissions = []
    observations = []

    if db_path:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            try:
                cur = await db.execute(
                    "SELECT id, category, mode, granted_at, granted_by, notes"
                    " FROM autonomy_permissions ORDER BY category"
                )
                permissions = [dict(r) for r in await cur.fetchall()]
            except Exception:
                pass
            try:
                cur = await db.execute(
                    "SELECT id, created_at, source, observation_type, content, priority"
                    " FROM dream_observations"
                    " WHERE status = 'open' ORDER BY created_at DESC LIMIT 50"
                )
                observations = [dict(r) for r in await cur.fetchall()]
            except Exception:
                pass

    return {
        "active": "autonomy",
        "permissions": permissions,
        "observations": observations,
        "modes": PERMISSION_MODES,
    }


async def post_permission(request: web.Request) -> web.Response:
    ctx = request.app.get("ctx", {})
    db_path = ctx.get("db_path", "")
    form = await request.post()
    category = form.get("category", "").strip()
    mode = form.get("mode", "").strip()

    if db_path and category and mode in PERMISSION_MODES:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "UPDATE autonomy_permissions SET mode = ? WHERE category = ?",
                (mode, category),
            )
            await db.commit()
    raise web.HTTPSeeOther("/autonomy")


async def post_observation_action(request: web.Request) -> web.Response:
    ctx = request.app.get("ctx", {})
    db_path = ctx.get("db_path", "")
    obs_id = int(request.match_info["id"])
    action = request.match_info["action"]  # "approve" or "reject"

    if db_path and action in ("approve", "reject"):
        status = "resolved" if action == "approve" else "wont_fix"
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "UPDATE dream_observations SET status = ?, resolved_at = CURRENT_TIMESTAMP,"
                " resolved_by = 'user' WHERE id = ? AND status = 'open'",
                (status, obs_id),
            )
            await db.commit()
    raise web.HTTPSeeOther("/autonomy")


def setup(app: web.Application) -> None:
    app.router.add_get("/autonomy", get_autonomy)
    app.router.add_post("/autonomy/permission", post_permission)
    app.router.add_post("/autonomy/observation/{id}/{action}", post_observation_action)
