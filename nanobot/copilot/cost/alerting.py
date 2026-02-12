"""Cost alerting: per-call and daily threshold alerts via message bus."""

from __future__ import annotations

from pathlib import Path

import aiosqlite
from loguru import logger

from nanobot.bus.events import OutboundMessage


class CostAlerter:
    """Monitors LLM costs and sends alerts when thresholds are exceeded."""

    def __init__(
        self,
        db_path: str | Path,
        bus,
        daily_threshold: float = 50.0,
        per_call_threshold: float = 0.50,
        alert_channel: str = "whatsapp",
        alert_chat_id: str = "",
    ):
        self._db_path = str(db_path)
        self._bus = bus
        self._daily_threshold = daily_threshold
        self._per_call_threshold = per_call_threshold
        self._channel = alert_channel
        self._chat_id = alert_chat_id
        self._daily_alert_sent = False
        self._last_alert_date: str = ""

    async def check_call(self, cost_usd: float, model: str) -> bool:
        """Check a single call's cost. Returns True if alert was sent."""
        if cost_usd < self._per_call_threshold:
            return False

        daily_total = await self._get_daily_total()
        alert_msg = (
            f"[Cost Alert] Single call: ${cost_usd:.2f} (model: {model}). "
            f"Daily total: ${daily_total:.2f} / ${self._daily_threshold:.2f}"
        )
        await self._send_alert(alert_msg)
        return True

    async def check_daily(self) -> bool:
        """Check daily total against threshold. Returns True if alert was sent."""
        import datetime
        today = datetime.date.today().isoformat()

        # Reset daily flag on new day
        if today != self._last_alert_date:
            self._daily_alert_sent = False
            self._last_alert_date = today

        if self._daily_alert_sent:
            return False

        daily_total = await self._get_daily_total()
        if daily_total < self._daily_threshold:
            return False

        self._daily_alert_sent = True
        alert_msg = (
            f"[Cost Alert] Daily threshold reached: ${daily_total:.2f} / ${self._daily_threshold:.2f}. "
            f"Consider switching to local models for remaining tasks."
        )
        await self._send_alert(alert_msg)
        return True

    async def _get_daily_total(self) -> float:
        """Query today's total cost from cost_log."""
        try:
            async with aiosqlite.connect(self._db_path) as db:
                cursor = await db.execute(
                    "SELECT COALESCE(SUM(cost_usd), 0) FROM cost_log WHERE date(timestamp) = date('now')"
                )
                row = await cursor.fetchone()
                return row[0] if row else 0.0
        except Exception as e:
            logger.warning(f"Failed to get daily cost: {e}")
            return 0.0

    async def _send_alert(self, message: str) -> None:
        """Send alert via message bus."""
        if not self._chat_id:
            logger.warning(f"Cost alert (no chat_id configured): {message}")
            return

        try:
            await self._bus.publish_outbound(OutboundMessage(
                channel=self._channel,
                chat_id=self._chat_id,
                content=message,
            ))
            logger.info(f"Cost alert sent: {message[:80]}")
        except Exception as e:
            logger.warning(f"Failed to send cost alert: {e}")
