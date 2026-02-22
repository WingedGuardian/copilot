"""Web chat channel — browser-based chat via WebSocket at /ws/chat."""
from __future__ import annotations

from typing import Any

from aiohttp import WSMsgType, web
from loguru import logger

from nanobot.bus.events import OutboundMessage
from nanobot.channels.base import BaseChannel


class WebChatChannel(BaseChannel):
    """Serves chat over WebSocket at /ws/chat.

    Inbound messages from browser clients are forwarded to the message bus as
    ``InboundMessage`` objects (channel="web_chat").  Outbound replies are
    delivered back through :meth:`send`, which broadcasts to all open sockets
    for the originating ``chat_id``.

    The channel's ``start()`` method is a no-op — WebSocket connections arrive
    via the aiohttp router rather than a long-running background connection.
    ``stop()`` closes all open sockets.
    """

    name = "web_chat"

    def __init__(self, config: Any, bus: Any) -> None:
        super().__init__(config, bus)
        # Map chat_id -> list of open WebSocketResponse objects
        self._sockets: dict[str, list[web.WebSocketResponse]] = {}

    # ------------------------------------------------------------------
    # BaseChannel abstract interface
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """No background loop needed — connections arrive via HTTP handler."""
        self._running = True
        logger.info("WebChatChannel ready (serving /ws/chat)")

    async def stop(self) -> None:
        """Close all open WebSocket connections."""
        self._running = False
        for sockets in self._sockets.values():
            for ws in list(sockets):
                try:
                    await ws.close()
                except Exception:
                    pass
        self._sockets.clear()
        logger.info("WebChatChannel stopped")

    async def send(self, msg: OutboundMessage) -> None:
        """Deliver an outbound reply to the browser client for chat_id."""
        sockets = self._sockets.get(msg.chat_id, [])
        payload = {"type": "message", "role": "assistant", "content": msg.content}
        dead: list[web.WebSocketResponse] = []
        for ws in list(sockets):
            try:
                await ws.send_json(payload)
            except Exception as exc:
                logger.debug(f"WebChat: send failed ({exc}); removing socket")
                dead.append(ws)
        for ws in dead:
            sockets.remove(ws)

    # ------------------------------------------------------------------
    # WebSocket HTTP handler
    # ------------------------------------------------------------------

    async def handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """aiohttp WebSocket handler — registered as GET /ws/chat."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        # Use the remote peer address as the stable chat_id for this session.
        # Two tabs from the same IP share a session; this matches what
        # Telegram does (chat_id == conversation thread).
        chat_id = request.headers.get("X-Forwarded-For") or str(request.remote or "web")

        bucket = self._sockets.setdefault(chat_id, [])
        bucket.append(ws)
        logger.info(f"WebChat: client connected chat_id={chat_id} total={len(bucket)}")

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    await self._on_message(chat_id, msg.data, ws)
                elif msg.type == WSMsgType.ERROR:
                    logger.warning(f"WebChat WS error: {ws.exception()}")
        finally:
            bucket = self._sockets.get(chat_id, [])
            if ws in bucket:
                bucket.remove(ws)
            logger.info(f"WebChat: client disconnected chat_id={chat_id} remaining={len(bucket)}")

        return ws

    async def _on_message(
        self, chat_id: str, text: str, ws: web.WebSocketResponse
    ) -> None:
        """Echo user message back to the sender, then route through the bus."""
        # Echo so the sender sees their own message in the thread immediately.
        await ws.send_json({"type": "message", "role": "user", "content": text})
        # Forward to agent via the message bus — response returns via send().
        await self._handle_message(
            sender_id=chat_id,
            chat_id=chat_id,
            content=text,
        )
