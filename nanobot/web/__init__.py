"""Nanobot web UI — aiohttp application factory."""

from __future__ import annotations

import pathlib

import aiohttp_jinja2
import jinja2
from aiohttp import web

_TEMPLATES_DIR = pathlib.Path(__file__).parent / "templates"
_STATIC_DIR = pathlib.Path(__file__).parent / "static"


def create_web_app(**ctx) -> web.Application:
    """Create and configure the aiohttp web application.

    Args:
        **ctx: Runtime context passed through to request handlers via
               ``app["ctx"]``.  Expected keys when running in copilot mode:
               ``status_aggregator``, ``session_manager``, etc.

    Returns:
        Configured :class:`aiohttp.web.Application`.
    """
    app = web.Application()

    aiohttp_jinja2.setup(
        app,
        loader=jinja2.FileSystemLoader(str(_TEMPLATES_DIR)),
    )

    app.router.add_static("/static", str(_STATIC_DIR), name="static")

    app["ctx"] = ctx

    from nanobot.web.routes import dashboard
    dashboard.setup(app)

    return app
