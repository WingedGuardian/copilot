"""Services page — periodic service status."""
from __future__ import annotations

import aiohttp_jinja2
from aiohttp import web
from loguru import logger


@aiohttp_jinja2.template("pages/services.html")
async def index(request: web.Request) -> dict:
    ctx = request.app.get("ctx", {})
    aggregator = ctx.get("status_aggregator")
    report = None
    if aggregator is not None:
        try:
            report = await aggregator.collect()
        except Exception as exc:
            logger.warning(f"StatusAggregator.collect() failed in services: {exc}")
    return {"active": "services", "report": report}


def setup(app: web.Application) -> None:
    app.router.add_get("/services", index)
