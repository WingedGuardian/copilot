"""Chat page — browser-based chat interface via WebSocket."""
from __future__ import annotations

import aiohttp_jinja2
from aiohttp import web


@aiohttp_jinja2.template("pages/chat.html")
async def chat_page(request: web.Request) -> dict:
    return {"active": "chat"}


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    """Delegate to WebChatChannel stored in app context."""
    ctx = request.app.get("ctx", {})
    web_chat = ctx.get("web_chat_channel")
    if web_chat is None:
        raise web.HTTPServiceUnavailable(reason="Web chat channel not initialised")
    return await web_chat.handle_websocket(request)


def setup(app: web.Application) -> None:
    app.router.add_get("/chat", chat_page)
    app.router.add_get("/ws/chat", websocket_handler)
