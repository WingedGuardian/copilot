"""Monitor service: periodic health checks with state-transition alerting."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Awaitable

from loguru import logger


class MonitorService:
    """Periodic health monitoring with self-heal, degrade, and nag behavior.

    - On failure: attempt auto-remediation, then notify
    - State-transition alerting: only alerts on healthy<->unhealthy transitions
    - Morning nag: once per day for unresolved issues
    """

    def __init__(
        self,
        status_aggregator: Any = None,
        deliver_fn: Callable | None = None,
        delivery_channel: str = "whatsapp",
        delivery_chat_id: str = "",
        interval_s: int = 300,
        remediation_fns: dict[str, Callable] | None = None,
        silent_subsystems: set[str] | None = None,
    ):
        self._status = status_aggregator
        self._deliver = deliver_fn
        self._channel = delivery_channel
        self._chat_id = delivery_chat_id
        self._interval = interval_s
        self._remediation_fns = remediation_fns or {}
        self._silent = silent_subsystems or set()

        # State tracking
        self._prev_health: dict[str, bool] = {}  # name -> was_healthy
        self._unresolved: dict[str, float] = {}  # name -> first_seen timestamp
        self._last_nag_date: str = ""

        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the monitoring loop."""
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(f"Monitor service started (interval={self._interval}s)")

    def stop(self) -> None:
        """Stop the monitor."""
        self._running = False
        if self._task:
            self._task.cancel()

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor tick failed: {e}")
            await asyncio.sleep(self._interval)

    async def _tick(self) -> None:
        """Run health checks and handle state transitions."""
        if not self._status:
            return

        report = await self._status.collect()

        for sub in report.subsystems:
            was_healthy = self._prev_health.get(sub.name, True)

            if was_healthy and not sub.healthy:
                # Transition: healthy -> unhealthy
                self._unresolved[sub.name] = time.time()

                if sub.name not in self._silent:
                    # Attempt remediation
                    remediated = False
                    if sub.name in self._remediation_fns:
                        try:
                            await self._remediation_fns[sub.name]()
                            remediated = True
                        except Exception:
                            pass

                    # Notify
                    if remediated:
                        await self._notify(f"[Fixed] {sub.name} restarted automatically", sub.name)
                    else:
                        await self._notify(f"[Down] {sub.name}: {sub.details}", sub.name)

            elif not was_healthy and sub.healthy:
                # Transition: unhealthy -> healthy (recovery)
                down_since = self._unresolved.pop(sub.name, time.time())
                if sub.name not in self._silent:
                    duration = time.time() - down_since
                    hours = int(duration // 3600)
                    minutes = int((duration % 3600) // 60)
                    await self._notify(f"[Recovered] {sub.name} back online after {hours}h{minutes}m", sub.name)

            self._prev_health[sub.name] = sub.healthy

        # Morning nag check
        await self._morning_nag()

    async def _morning_nag(self) -> None:
        """Once per day, summarize all unresolved issues."""
        import datetime
        now = datetime.datetime.now()
        today = now.date().isoformat()

        if today == self._last_nag_date:
            return
        if now.hour != 7:  # Only nag at 7 AM
            return
        nag_items = {k: v for k, v in self._unresolved.items() if k not in self._silent}
        if not nag_items:
            return

        self._last_nag_date = today
        lines = ["[Morning Health Summary]"]
        for name, since in nag_items.items():
            duration = time.time() - since
            hours = int(duration // 3600)
            lines.append(f"  {name}: down for {hours}h")
        await self._notify("\n".join(lines))

    async def _notify(self, message: str, subsystem: str = "monitor") -> None:
        """Send notification via message bus and record in AlertBus."""
        # Always write to AlertBus so state transitions surface in /status
        try:
            from nanobot.copilot.alerting.bus import get_alert_bus
            severity = "high" if "[Down]" in message else "medium"
            error_key = f"monitor_{subsystem}"
            await get_alert_bus().alert(subsystem, severity, message, error_key)
        except Exception as e:
            logger.debug(f"Monitor AlertBus write failed: {e}")

        if not self._deliver or not self._chat_id:
            logger.warning(f"Monitor alert (no delivery): {message}")
            return
        try:
            await self._deliver(self._channel, self._chat_id, message)
        except Exception as e:
            logger.warning(f"Monitor notification failed: {e}")
