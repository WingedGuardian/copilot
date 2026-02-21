"""Logs page — tail and filter gateway.log."""
from __future__ import annotations

import pathlib

import aiohttp_jinja2
from aiohttp import web

_LOG_PATH = pathlib.Path.home() / ".nanobot" / "logs" / "gateway.log"
_TAIL_LINES = 500


@aiohttp_jinja2.template("pages/logs.html")
async def index(request: web.Request) -> dict:
    q = request.rel_url.query.get("q", "").strip()
    level = request.rel_url.query.get("level", "").strip().upper()

    lines: list[str] = []
    if _LOG_PATH.exists():
        try:
            raw = _LOG_PATH.read_text(errors="replace").splitlines()
            # Take last N lines then reverse for newest-first display
            lines = list(reversed(raw[-_TAIL_LINES:]))
        except OSError:
            lines = []

    # Filter
    if level:
        lines = [ln for ln in lines if f" {level} " in ln or f"{level}:" in ln]
    if q:
        q_lower = q.lower()
        lines = [ln for ln in lines if q_lower in ln.lower()]

    return {
        "active": "logs",
        "lines": lines,
        "q": q,
        "level": level,
        "log_exists": _LOG_PATH.exists(),
    }


def setup(app: web.Application) -> None:
    app.router.add_get("/logs", index)
