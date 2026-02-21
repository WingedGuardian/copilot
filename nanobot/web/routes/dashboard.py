"""Dashboard route — main landing page showing system status."""

from __future__ import annotations

import aiohttp_jinja2
from aiohttp import web
from loguru import logger


@aiohttp_jinja2.template("pages/dashboard.html")
async def index(request: web.Request) -> dict:
    """Render the dashboard page with a live status report."""
    ctx = request.app.get("ctx", {})
    aggregator = ctx.get("status_aggregator")
    report = None
    if aggregator is not None:
        try:
            report = await aggregator.collect()
        except Exception as exc:
            logger.warning(f"StatusAggregator.collect() failed: {exc}")
    return {"report": report, "active": "dashboard"}


def setup(app: web.Application) -> None:
    """Register dashboard routes on *app*."""
    app.router.add_get("/", index, name="dashboard")
