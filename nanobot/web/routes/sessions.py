"""Sessions page — active session overview."""
from __future__ import annotations

import aiohttp_jinja2
from aiohttp import web


@aiohttp_jinja2.template("pages/sessions.html")
async def index(request: web.Request) -> dict:
    ctx = request.app.get("ctx", {})
    session_manager = ctx.get("session_manager")

    sessions: list[dict] = []
    if session_manager is not None:
        try:
            sessions = session_manager.list_sessions()
        except Exception:
            sessions = []

    return {
        "active": "sessions",
        "sessions": sessions,
    }


def setup(app: web.Application) -> None:
    app.router.add_get("/sessions", index)
