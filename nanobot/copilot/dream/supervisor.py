"""Process supervisor: restarts crashed services with exponential backoff."""

import asyncio
from typing import Callable, Awaitable
from loguru import logger


class ProcessSupervisor:
    """Register services by name + start function; auto-restart on crash."""

    def __init__(self, check_interval: float = 30.0, max_restarts: int = 5):
        self._check_interval = check_interval
        self._max_restarts = max_restarts
        self._services: dict[str, dict] = {}  # name -> {start_fn, task, restarts, backoff}
        self._running = False
        self._supervisor_task: asyncio.Task | None = None

    def register(self, name: str, start_fn: Callable[[], Awaitable[None]]) -> None:
        """Register a service to be supervised."""
        self._services[name] = {
            "start_fn": start_fn,
            "task": None,
            "restarts": 0,
            "backoff": 1.0,
        }

    async def start(self) -> None:
        """Start all registered services and the supervisor loop."""
        self._running = True
        for name, svc in self._services.items():
            svc["task"] = asyncio.create_task(
                self._run_service(name), name=f"supervisor:{name}"
            )
        self._supervisor_task = asyncio.create_task(self._health_loop())
        logger.info(f"ProcessSupervisor started with {len(self._services)} services")

    async def stop(self) -> None:
        """Stop all services and the supervisor."""
        self._running = False
        if self._supervisor_task:
            self._supervisor_task.cancel()
        for name, svc in self._services.items():
            if svc["task"] and not svc["task"].done():
                svc["task"].cancel()
        logger.info("ProcessSupervisor stopped")

    async def _run_service(self, name: str) -> None:
        """Run a service, catching crashes."""
        svc = self._services[name]
        try:
            await svc["start_fn"]()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Service '{name}' crashed: {e}")

    async def _health_loop(self) -> None:
        """Periodically check services and restart dead ones."""
        while self._running:
            await asyncio.sleep(self._check_interval)
            for name, svc in self._services.items():
                task = svc["task"]
                if task and task.done() and not task.cancelled():
                    if svc["restarts"] >= self._max_restarts:
                        logger.error(
                            f"Service '{name}' exceeded max restarts ({self._max_restarts}), giving up"
                        )
                        from nanobot.copilot.alerting.bus import get_alert_bus
                        await get_alert_bus().alert(
                            "supervisor", "high",
                            f"Service '{name}' dead — gave up after {self._max_restarts} restarts",
                            f"max_restarts_{name}",
                        )
                        continue
                    svc["restarts"] += 1
                    svc["backoff"] = min(svc["backoff"] * 2, 300.0)
                    logger.warning(
                        f"Service '{name}' is dead, restarting in {svc['backoff']}s "
                        f"(attempt {svc['restarts']}/{self._max_restarts})"
                    )
                    if svc["restarts"] >= 3:
                        from nanobot.copilot.alerting.bus import get_alert_bus
                        await get_alert_bus().alert(
                            "supervisor", "high",
                            f"Service '{name}' crashed {svc['restarts']} times, still restarting",
                            f"crash_loop_{name}",
                        )
                    await asyncio.sleep(svc["backoff"])
                    if self._running:
                        svc["task"] = asyncio.create_task(
                            self._run_service(name), name=f"supervisor:{name}"
                        )

    def get_status(self) -> dict[str, dict]:
        """Get status of all supervised services."""
        return {
            name: {
                "alive": svc["task"] is not None and not svc["task"].done(),
                "restarts": svc["restarts"],
            }
            for name, svc in self._services.items()
        }
