"""Lessons page — metacognitive lessons viewer."""
from __future__ import annotations

import logging

import aiohttp_jinja2
import aiosqlite
from aiohttp import web

logger = logging.getLogger(__name__)


@aiohttp_jinja2.template("pages/lessons.html")
async def index(request: web.Request) -> dict:
    ctx = request.app.get("ctx", {})
    db_path = ctx.get("db_path", "")
    active_filter = request.rel_url.query.get("active", "")
    category_filter = request.rel_url.query.get("category", "")
    try:
        min_conf = float(request.rel_url.query.get("min_conf", "0.0"))
    except ValueError:
        min_conf = 0.0

    lessons: list[dict] = []
    categories: list[str] = []

    if db_path:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row

            # lessons columns (base + phase3 additions):
            #   id, trigger_pattern, lesson_text, confidence, reinforcement_count,
            #   active, created_at, last_applied,
            #   source, category, applied_count, helpful_count
            conditions = ["confidence >= ?"]
            params: list = [min_conf]

            if active_filter in ("0", "1"):
                conditions.append("active = ?")
                params.append(int(active_filter))
            if category_filter:
                conditions.append("category = ?")
                params.append(category_filter)

            where = " AND ".join(conditions)
            cur = await db.execute(
                f"SELECT * FROM lessons WHERE {where} ORDER BY confidence DESC LIMIT 200",
                params,
            )
            lessons = [dict(r) for r in await cur.fetchall()]

            # Distinct categories for filter dropdown
            try:
                cur = await db.execute(
                    "SELECT DISTINCT category FROM lessons WHERE category IS NOT NULL ORDER BY category"
                )
                categories = [r[0] for r in await cur.fetchall() if r[0]]
            except Exception:
                categories = []

    return {
        "active": "lessons",
        "lessons": lessons,
        "categories": categories,
        "active_filter": active_filter,
        "category_filter": category_filter,
        "min_conf": min_conf,
    }


async def toggle_active(request: web.Request) -> web.Response:
    """Toggle lesson active/inactive."""
    lesson_id = int(request.match_info["id"])
    ctx = request.app.get("ctx", {})
    db_path = ctx.get("db_path", "")
    if db_path:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "UPDATE lessons SET active = NOT active WHERE id = ?", (lesson_id,)
            )
            await db.commit()
    raise web.HTTPSeeOther("/lessons")


async def delete_lesson(request: web.Request) -> web.Response:
    """Delete a lesson permanently."""
    lesson_id = int(request.match_info["id"])
    ctx = request.app.get("ctx", {})
    db_path = ctx.get("db_path", "")
    if db_path:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))
            await db.commit()
        logger.info(f"Lesson {lesson_id} deleted via web UI")
    raise web.HTTPSeeOther("/lessons")


def setup(app: web.Application) -> None:
    app.router.add_get("/lessons", index)
    app.router.add_post("/lessons/{id}/toggle-active", toggle_active)
    app.router.add_post("/lessons/{id}/delete", delete_lesson)
