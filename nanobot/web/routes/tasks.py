"""Tasks page — task board and detail view."""
from __future__ import annotations

import aiohttp_jinja2
import aiosqlite
from aiohttp import web


@aiohttp_jinja2.template("pages/tasks.html")
async def index(request: web.Request) -> dict:
    ctx = request.app.get("ctx", {})
    db_path = ctx.get("db_path", "")
    status_filter = request.rel_url.query.get("status", "")
    tasks: list[dict] = []

    if db_path:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            if status_filter:
                cur = await db.execute(
                    "SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC",
                    (status_filter,),
                )
            else:
                cur = await db.execute(
                    "SELECT * FROM tasks ORDER BY created_at DESC LIMIT 100"
                )
            tasks = [dict(r) for r in await cur.fetchall()]

    return {"active": "tasks", "tasks": tasks, "status_filter": status_filter}


@aiohttp_jinja2.template("pages/task_detail.html")
async def task_detail(request: web.Request) -> dict:
    task_id = request.match_info["id"]
    ctx = request.app.get("ctx", {})
    db_path = ctx.get("db_path", "")
    task = None
    steps: list[dict] = []
    logs: list[dict] = []

    if db_path:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row

            cur = await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = await cur.fetchone()
            task = dict(row) if row else None

            if task:
                cur = await db.execute(
                    "SELECT * FROM task_steps WHERE task_id = ? ORDER BY step_index",
                    (task_id,),
                )
                steps = [dict(r) for r in await cur.fetchall()]

                cur = await db.execute(
                    "SELECT * FROM task_log WHERE task_id = ? ORDER BY timestamp DESC LIMIT 50",
                    (task_id,),
                )
                logs = [dict(r) for r in await cur.fetchall()]

    return {"active": "tasks", "task": task, "steps": steps, "logs": logs}


async def cancel_task(request: web.Request) -> web.Response:
    """Cancel an in-progress or pending task."""
    task_id = request.match_info["id"]
    ctx = request.app.get("ctx", {})
    db_path = ctx.get("db_path", "")
    if db_path:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "UPDATE tasks SET status = 'failed' WHERE id = ? AND status NOT IN ('completed', 'failed')",
                (task_id,),
            )
            await db.commit()
    raise web.HTTPSeeOther("/tasks")


def setup(app: web.Application) -> None:
    app.router.add_get("/tasks", index)
    app.router.add_get("/tasks/{id}", task_detail)
    app.router.add_post("/tasks/{id}/cancel", cancel_task)
