"""MD file browser and editor."""
from __future__ import annotations

import logging
import pathlib
import urllib.parse

import aiohttp_jinja2
from aiohttp import web

logger = logging.getLogger(__name__)

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_ALLOWED_DIRS = [
    _REPO_ROOT / "data" / "copilot",
    _REPO_ROOT / "workspace",
]
_ALLOWED_FILES = [
    _REPO_ROOT / "CLAUDE.md",
]


def _is_allowed(path: pathlib.Path) -> bool:
    resolved = path.resolve()
    for d in _ALLOWED_DIRS:
        try:
            resolved.relative_to(d.resolve())
            return True
        except ValueError:
            pass
    for f in _ALLOWED_FILES:
        if resolved == f.resolve():
            return True
    return False


def _list_files() -> list[dict]:
    """Return grouped list of MD files."""
    groups: list[dict] = []
    for d in _ALLOWED_DIRS:
        if d.exists():
            files = sorted(d.glob("*.md"))
            if files:
                groups.append({
                    "label": d.name,
                    "files": [{"name": f.name, "path": str(f)} for f in files],
                })
    for f in _ALLOWED_FILES:
        if f.exists():
            project = next((g for g in groups if g["label"] == "project"), None)
            if project is None:
                project = {"label": "project", "files": []}
                groups.append(project)
            project["files"].append({"name": f.name, "path": str(f)})
    return groups


@aiohttp_jinja2.template("pages/files.html")
async def list_files(request: web.Request) -> dict:
    return {"active": "files", "groups": _list_files()}


@aiohttp_jinja2.template("pages/file_edit.html")
async def edit_file(request: web.Request) -> dict:
    raw_path = urllib.parse.unquote(request.match_info.get("path", ""))
    file_path = pathlib.Path(raw_path)
    if not _is_allowed(file_path):
        raise web.HTTPForbidden(reason="Path not in allowlist")

    content = file_path.read_text(encoding="utf-8") if file_path.exists() else ""
    return {
        "active": "files",
        "file_path": str(file_path),
        "file_name": file_path.name,
        "content": content,
        "groups": _list_files(),
        "saved": "saved" in request.rel_url.query,
    }


async def save_file(request: web.Request) -> web.Response:
    raw_path = urllib.parse.unquote(request.match_info.get("path", ""))
    file_path = pathlib.Path(raw_path)
    if not _is_allowed(file_path):
        raise web.HTTPForbidden(reason="Path not in allowlist")

    form = await request.post()
    content = form.get("content", "")
    file_path.write_text(content, encoding="utf-8")
    logger.info("File saved via web UI: %s", file_path)

    encoded = urllib.parse.quote(str(file_path), safe="")
    raise web.HTTPSeeOther(f"/files/{encoded}?saved=1")


def setup(app: web.Application) -> None:
    app.router.add_get("/files", list_files)
    app.router.add_get("/files/{path:.+}", edit_file)
    app.router.add_post("/files/{path:.+}", save_file)
