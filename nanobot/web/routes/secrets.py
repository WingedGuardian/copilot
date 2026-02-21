"""Secrets editor — masked display and inline update."""
from __future__ import annotations

import json
import logging
import pathlib

import aiohttp_jinja2
from aiohttp import web

logger = logging.getLogger(__name__)
_SECRETS_PATH = pathlib.Path.home() / ".nanobot" / "secrets.json"


def _mask(value: str) -> str:
    """Return masked version: last 4 chars only."""
    if not value or len(value) <= 4:
        return "****"
    return "****" + value[-4:]


def _flatten(data: dict, prefix: str = "") -> list[dict]:
    """Recursively flatten nested dict into list of {path, masked, configured} dicts."""
    entries = []
    for key, val in data.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(val, dict):
            entries.extend(_flatten(val, path))
        elif isinstance(val, str):
            entries.append({
                "path": path,
                "masked": _mask(val) if val else "(empty)",
                "configured": bool(val),
            })
    return entries


def _set_dotted(data: dict, dotted_path: str, value: str) -> None:
    """Set a value in a nested dict via dotted path, creating keys as needed."""
    keys = dotted_path.split(".")
    d = data
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = value


@aiohttp_jinja2.template("pages/secrets.html")
async def get_secrets(request: web.Request) -> dict:
    entries = []
    saved_path = request.rel_url.query.get("saved", "")
    if _SECRETS_PATH.exists():
        try:
            data = json.loads(_SECRETS_PATH.read_text())
            entries = _flatten(data)
        except Exception:
            pass
    return {"active": "secrets", "entries": entries, "saved_path": saved_path}


async def post_secrets(request: web.Request) -> web.Response:
    form = await request.post()
    path = form.get("path", "").strip()
    value = form.get("value", "")
    if not path:
        raise web.HTTPSeeOther("/secrets")

    data = {}
    if _SECRETS_PATH.exists():
        try:
            data = json.loads(_SECRETS_PATH.read_text())
        except Exception:
            pass

    _set_dotted(data, path, value)
    _SECRETS_PATH.write_text(json.dumps(data, indent=2))
    logger.info("Secret updated via web UI: %s", path)
    raise web.HTTPSeeOther(f"/secrets?saved={path}")


def setup(app: web.Application) -> None:
    app.router.add_get("/secrets", get_secrets)
    app.router.add_post("/secrets", post_secrets)
