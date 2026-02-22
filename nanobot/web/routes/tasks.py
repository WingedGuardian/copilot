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


async def send_message(request: web.Request) -> web.Response:
    """Post a user message to an active task's activity stream."""
    task_id = request.match_info["id"]
    data = await request.post()
    message = data.get("message", "").strip()
    ctx = request.app.get("ctx", {})
    db_path = ctx.get("db_path", "")

    if message and db_path:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO task_log (task_id, event, details) VALUES (?, 'user_message', ?)",
                (task_id, message),
            )
            await db.commit()

    raise web.HTTPSeeOther(f"/tasks/{task_id}")


async def pause_task(request: web.Request) -> web.Response:
    """Pause an active task."""
    task_id = request.match_info["id"]
    ctx = request.app.get("ctx", {})
    db_path = ctx.get("db_path", "")
    if db_path:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "UPDATE tasks SET status = 'paused', updated_at = CURRENT_TIMESTAMP "
                "WHERE id = ? AND status IN ('active','pending','planning','awaiting')",
                (task_id,),
            )
            if db.total_changes:
                await db.execute(
                    "INSERT INTO task_log (task_id, event, details) VALUES (?, 'paused', '')",
                    (task_id,),
                )
            await db.commit()
    raise web.HTTPSeeOther(f"/tasks/{task_id}")


async def resume_task(request: web.Request) -> web.Response:
    """Resume a paused task."""
    task_id = request.match_info["id"]
    ctx = request.app.get("ctx", {})
    db_path = ctx.get("db_path", "")
    if db_path:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "UPDATE tasks SET status = 'pending', updated_at = CURRENT_TIMESTAMP "
                "WHERE id = ? AND status = 'paused'",
                (task_id,),
            )
            if db.total_changes:
                await db.execute(
                    "INSERT INTO task_log (task_id, event, details) VALUES (?, 'resumed', '')",
                    (task_id,),
                )
            await db.commit()
    raise web.HTTPSeeOther(f"/tasks/{task_id}")


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


async def task_events(request: web.Request) -> web.Response:
    """Return task_log events since a timestamp for live polling."""
    task_id = request.match_info["id"]
    since = request.rel_url.query.get("since", "1970-01-01T00:00:00")
    ctx = request.app.get("ctx", {})
    db_path = ctx.get("db_path", "")
    events: list[dict] = []

    if db_path:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM task_log WHERE task_id = ? AND timestamp > ? "
                "ORDER BY timestamp ASC LIMIT 50",
                (task_id, since),
            )
            events = [dict(r) for r in await cur.fetchall()]

    return web.json_response(events)


def setup(app: web.Application) -> None:
    app.router.add_get("/tasks", index)
    app.router.add_get("/tasks/{id}", task_detail)
    app.router.add_get("/tasks/{id}/events", task_events)
    app.router.add_post("/tasks/{id}/message", send_message)
    app.router.add_post("/tasks/{id}/pause", pause_task)
    app.router.add_post("/tasks/{id}/resume", resume_task)
    app.router.add_post("/tasks/{id}/cancel", cancel_task)
