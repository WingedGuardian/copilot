"""Unified alert bus — deduplicated, severity-aware notifications."""

import time
from typing import Callable, Awaitable

import aiosqlite
from loguru import logger


class AlertBus:
    """Global alert bus with dedup, mute, and SQLite persistence.

    Severity levels:
        high   — immediate delivery (bypasses dedup window)
        medium — delivered if outside dedup window
        low    — SQLite only, no notification
    """

    def __init__(
        self,
        db_path: str,
        deliver_fn: Callable[[str], Awaitable[None]] | None = None,
        dedup_hours: float = 4.0,
    ):
        self._db_path = db_path
        self._deliver_fn = deliver_fn
        self._dedup_seconds = dedup_hours * 3600
        self._mute_until: float = 0.0
        self._last_sent: dict[str, float] = {}  # "subsystem:error_key" -> timestamp
        self._alert_count: int = 0

    # ── Public API ────────────────────────────────────────────────────

    async def alert(
        self,
        subsystem: str,
        severity: str,
        message: str,
        error_key: str = "",
    ) -> None:
        """Record an alert and optionally deliver it."""
        dedup_key = f"{subsystem}:{error_key}"
        now = time.time()
        delivered = False

        # Lazy prune expired dedup entries every 100 alerts
        self._alert_count += 1
        if self._alert_count % 100 == 0:
            self._last_sent = {
                k: ts for k, ts in self._last_sent.items()
                if (now - ts) < self._dedup_seconds
            }

        should_deliver = self._should_deliver(severity, dedup_key, now)
        if should_deliver:
            delivered = await self._deliver(message)
            if delivered:
                self._last_sent[dedup_key] = now

        await self._persist(subsystem, severity, error_key, message, delivered)

    def set_frequency(self, hours: float) -> None:
        """Change the dedup window at runtime."""
        self._dedup_seconds = max(1.0, min(hours, 24.0)) * 3600

    def mute_until(self, timestamp: float) -> None:
        """Suppress all notifications until the given Unix timestamp."""
        self._mute_until = timestamp

    def unmute(self) -> None:
        """Resume notifications immediately."""
        self._mute_until = 0.0

    def get_config(self) -> dict:
        """Return current frequency + mute status."""
        now = time.time()
        muted = self._mute_until > now
        return {
            "dedup_hours": round(self._dedup_seconds / 3600, 1),
            "muted": muted,
            "mute_until": self._mute_until if muted else None,
        }

    # ── Internals ─────────────────────────────────────────────────────

    def _should_deliver(self, severity: str, dedup_key: str, now: float) -> bool:
        if severity == "low":
            return False
        if now < self._mute_until:
            return False
        if severity == "high":
            return True
        # medium: check dedup window
        last = self._last_sent.get(dedup_key, 0.0)
        return (now - last) >= self._dedup_seconds

    async def _deliver(self, message: str) -> bool:
        if not self._deliver_fn:
            return False
        try:
            await self._deliver_fn(message)
            return True
        except Exception as e:
            logger.warning(f"Alert delivery failed: {e}")
            return False

    async def _persist(
        self,
        subsystem: str,
        severity: str,
        error_key: str,
        message: str,
        delivered: bool,
    ) -> None:
        try:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    "INSERT INTO alerts (subsystem, severity, error_key, message, delivered) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (subsystem, severity, error_key, message, 1 if delivered else 0),
                )
                await db.commit()
        except Exception as e:
            logger.debug(f"Alert persistence failed: {e}")


# ── Singleton ─────────────────────────────────────────────────────────

_alert_bus: AlertBus | None = None


def init_alert_bus(
    db_path: str,
    deliver_fn: Callable[[str], Awaitable[None]] | None = None,
    dedup_hours: float = 4.0,
) -> AlertBus:
    """Create and set the global AlertBus singleton."""
    global _alert_bus
    _alert_bus = AlertBus(db_path, deliver_fn, dedup_hours)
    return _alert_bus


_warned_uninitialized = False


def get_alert_bus() -> AlertBus:
    """Return the global AlertBus (lazy no-op if not initialised)."""
    global _alert_bus, _warned_uninitialized
    if _alert_bus is None:
        if not _warned_uninitialized:
            logger.warning("AlertBus not initialized — alerts will not be delivered")
            _warned_uninitialized = True
        _alert_bus = AlertBus(":memory:")
    return _alert_bus
