"""WhatsApp channel implementation using Node.js bridge."""

import asyncio
import json
from collections import OrderedDict
from typing import Any

from loguru import logger

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.config.schema import WhatsAppConfig


class WhatsAppChannel(BaseChannel):
    """
    WhatsApp channel that connects to a Node.js bridge.

    The bridge uses @whiskeysockets/baileys to handle the WhatsApp Web protocol.
    Communication between Python and Node.js is via WebSocket.
    """

    name = "whatsapp"

    def __init__(self, config: WhatsAppConfig, bus: MessageBus, transcriber=None):
        super().__init__(config, bus)
        self.config: WhatsAppConfig = config
        self._ws = None
        self._connected = False
        self._transcriber = transcriber  # VoiceTranscriber or None
        self._composing_tasks: dict[str, asyncio.Task] = {}  # jid -> refresh task
        self._processed_message_ids: OrderedDict[str, None] = OrderedDict()
        self._max_message_id_cache = 1000  # Prevent unbounded growth
    
    async def start(self) -> None:
        """Start the WhatsApp channel by connecting to the bridge."""
        import websockets
        
        bridge_url = self.config.bridge_url
        
        logger.info(f"Connecting to WhatsApp bridge at {bridge_url}...")
        
        self._running = True
        attempt = 0

        while self._running:
            try:
                async with websockets.connect(bridge_url) as ws:
                    self._ws = ws
                    # Send auth token if configured
                    if self.config.bridge_token:
                        await ws.send(json.dumps({"type": "auth", "token": self.config.bridge_token}))
                    self._connected = True
                    attempt = 0  # Reset on successful connection
                    logger.info("Connected to WhatsApp bridge")

                    # Listen for messages
                    async for message in ws:
                        try:
                            await self._handle_bridge_message(message)
                        except Exception as e:
                            logger.error(f"Error handling bridge message: {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._connected = False
                self._ws = None
                self._stop_all_composing()
                logger.warning(f"WhatsApp bridge connection error: {e}")

                if self._running:
                    import random
                    delay = min(5 * (2 ** attempt) + random.uniform(0, 1), 120)
                    logger.info(f"Reconnecting in {delay:.1f}s (attempt {attempt + 1})...")
                    await asyncio.sleep(delay)
                    attempt += 1
    
    async def stop(self) -> None:
        """Stop the WhatsApp channel."""
        self._running = False
        self._connected = False
        self._stop_all_composing()

        if self._ws:
            await self._ws.close()
            self._ws = None
    
    async def send(self, msg: OutboundMessage) -> None:
        """Send a message through WhatsApp."""
        if not self._ws or not self._connected:
            logger.warning("WhatsApp bridge not connected")
            return

        try:
            # Stop composing refresh loop and indicator before sending
            self._stop_composing(msg.chat_id)
            await self._send_presence(msg.chat_id, "paused")
            payload = {
                "type": "send",
                "to": msg.chat_id,
                "text": msg.content
            }
            await self._ws.send(json.dumps(payload))
        except Exception as e:
            logger.error(f"Error sending WhatsApp message: {e}")

    async def _send_read_receipt(self, jid: str, message_id: str) -> None:
        """Mark a message as read (blue checkmarks)."""
        if not self._ws or not self._connected:
            return
        try:
            await self._ws.send(json.dumps({
                "type": "read", "to": jid, "messageIds": [message_id],
            }))
        except Exception as e:
            logger.debug(f"Failed to send read receipt: {e}")

    async def _send_presence(self, jid: str, presence: str) -> None:
        """Send composing/paused presence to a chat."""
        if not self._ws or not self._connected:
            return
        try:
            await self._ws.send(json.dumps({
                "type": "presence", "to": jid, "presence": presence,
            }))
        except Exception as e:
            logger.debug(f"Failed to send presence: {e}")

    def _start_composing(self, jid: str) -> None:
        """Start composing indicator with periodic refresh (WhatsApp times out after ~15s)."""
        self._stop_composing(jid)
        self._composing_tasks[jid] = asyncio.create_task(self._composing_loop(jid))

    def _stop_composing(self, jid: str) -> None:
        """Cancel the composing refresh loop for a chat."""
        task = self._composing_tasks.pop(jid, None)
        if task and not task.done():
            task.cancel()

    def _stop_all_composing(self) -> None:
        """Cancel all composing tasks (cleanup on disconnect)."""
        for jid in list(self._composing_tasks):
            self._stop_composing(jid)

    async def _composing_loop(self, jid: str) -> None:
        """Re-send composing presence every 10s to keep the indicator alive.

        Auto-stops after 5 minutes to prevent infinite '...' if the system hangs.
        """
        try:
            elapsed = 0
            max_duration = 300  # 5 minutes
            while elapsed < max_duration:
                await self._send_presence(jid, "composing")
                await asyncio.sleep(10)
                elapsed += 10
            # Timed out — clear composing indicator
            await self._send_presence(jid, "paused")
            logger.warning(f"Composing indicator timed out for {jid} after {max_duration}s")
        except asyncio.CancelledError:
            pass
    
    async def _handle_bridge_message(self, raw: str) -> None:
        """Handle a message from the bridge."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON from bridge: {raw[:100]}")
            return
        
        msg_type = data.get("type")
        
        if msg_type == "message":
            # Incoming message from WhatsApp
            # Deprecated by whatsapp: old phone number style typically: <phone>@s.whatspp.net
            pn = data.get("pn", "")
            # New LID sytle typically: 
            sender = data.get("sender", "")
            content = data.get("content", "")
            
            # Extract just the phone number or lid as chat_id
            user_id = pn if pn else sender
            sender_id = user_id.split("@")[0] if "@" in user_id else user_id
            logger.info(f"Sender {sender}")
            
            # Handle voice transcription if it's a voice message
            audio_path = data.get("audioPath")
            if content == "[Voice Message]" and audio_path and self._transcriber:
                from pathlib import Path
                logger.info(f"Transcribing voice message from {sender_id}: {audio_path}")
                transcribed = await self._transcriber.transcribe(Path(audio_path))
                if transcribed and not transcribed.startswith("["):
                    content = transcribed
                else:
                    content = transcribed or "[Voice message could not be transcribed]"
            elif content == "[Voice Message]":
                content = "[Voice message: transcription not configured]"

            # Collect media paths (documents, images) from bridge
            media: list[str] = []
            doc_path = data.get("documentPath")
            if doc_path:
                media.append(doc_path)
                logger.info(f"Document received from {sender_id}: {doc_path}")
            img_path = data.get("imagePath")
            if img_path:
                media.append(img_path)
                logger.info(f"Image received from {sender_id}: {img_path}")

            # Prefer phone-number JID for replies (Baileys can't send to @lid)
            reply_jid = pn if pn else sender

            # Deduplicate messages by ID (prevents double-processing during reconnects)
            message_id = data.get("id")
            if message_id:
                if message_id in self._processed_message_ids:
                    logger.debug(f"Skipping duplicate message {message_id}")
                    return
                self._processed_message_ids[message_id] = None

                # Prevent unbounded cache growth (FIFO eviction)
                if len(self._processed_message_ids) > self._max_message_id_cache:
                    to_remove = len(self._processed_message_ids) // 2
                    for _ in range(to_remove):
                        self._processed_message_ids.popitem(last=False)

                await self._send_read_receipt(reply_jid, message_id)
            self._start_composing(reply_jid)

            # Append rejected file info so the LLM can respond naturally
            for rejected in data.get("rejectedFiles", []):
                size_mb = rejected.get("size", 0) / (1024 * 1024)
                name = rejected.get("filename", "file")
                reason = rejected.get("reason", "unknown")
                content += f"\n[File rejected: {name} ({size_mb:.1f}MB) — {reason}]"

            await self._handle_message(
                sender_id=sender_id,
                chat_id=reply_jid,
                content=content,
                media=media if media else None,
                metadata={
                    "message_id": data.get("id"),
                    "timestamp": data.get("timestamp"),
                    "is_group": data.get("isGroup", False)
                }
            )
            # Media files persist in ~/.nanobot/media/ (same as Telegram/Discord).
            # Periodic cleanup deferred to heartbeat or cron.
        
        elif msg_type == "status":
            # Connection status update
            status = data.get("status")
            logger.info(f"WhatsApp status: {status}")
            
            if status == "connected":
                self._connected = True
            elif status == "disconnected":
                self._connected = False
        
        elif msg_type == "qr":
            # QR code for authentication
            logger.info("Scan QR code in the bridge terminal to connect WhatsApp")
        
        elif msg_type == "error":
            logger.error(f"WhatsApp bridge error: {data.get('error')}")
