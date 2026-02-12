"""Status aggregator: collects health, cost, memory, and channel data."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import aiosqlite
from loguru import logger


@dataclass
class SubsystemStatus:
    """Health status of a single subsystem."""

    name: str
    healthy: bool
    details: str = ""
    latency_ms: int = 0


@dataclass
class DashboardReport:
    """Aggregated status report."""

    subsystems: list[SubsystemStatus] = field(default_factory=list)
    cost_today: float = 0.0
    cost_week: float = 0.0
    cost_top_models: list[tuple[str, float]] = field(default_factory=list)
    call_count_today: int = 0
    episode_count: int = 0
    structured_items: int = 0
    session_count: int = 0

    def to_text(self) -> str:
        """Format as WhatsApp-friendly text."""
        lines = ["System Status"]
        lines.append("")

        # Health
        lines.append("Health:")
        for s in self.subsystems:
            icon = "OK" if s.healthy else "DOWN"
            latency = f" ({s.latency_ms}ms)" if s.latency_ms else ""
            detail = f" - {s.details}" if s.details else ""
            lines.append(f"  {s.name}: {icon}{latency}{detail}")

        # Cost
        lines.append("")
        lines.append("Cost:")
        lines.append(f"  Today: ${self.cost_today:.2f}")
        lines.append(f"  7-day: ${self.cost_week:.2f}")
        lines.append(f"  Calls today: {self.call_count_today}")
        if self.cost_top_models:
            lines.append("  Top models:")
            for model, cost in self.cost_top_models[:3]:
                lines.append(f"    {model}: ${cost:.2f}")

        # Memory
        lines.append("")
        lines.append("Memory:")
        lines.append(f"  Episodes: {self.episode_count}")
        lines.append(f"  Structured items: {self.structured_items}")

        return "\n".join(lines)


class StatusAggregator:
    """Collects status from all subsystems."""

    def __init__(
        self,
        db_path: str = "",
        lm_studio_url: str = "http://192.168.50.100:1234",
        qdrant_url: str = "http://localhost:6333",
        redis_url: str = "redis://localhost:6379/0",
        memory_manager: Any = None,
        cron_service: Any = None,
        channel_manager: Any = None,
        session_manager: Any = None,
    ):
        self._db_path = db_path
        self._lm_studio_url = lm_studio_url
        self._qdrant_url = qdrant_url
        self._redis_url = redis_url
        self._memory_manager = memory_manager
        self._cron_service = cron_service
        self._channel_manager = channel_manager
        self._session_manager = session_manager

    async def collect(self) -> DashboardReport:
        """Run all checks in parallel and assemble report."""
        report = DashboardReport()

        checks = await asyncio.gather(
            self._check_lm_studio(),
            self._check_qdrant(),
            self._check_redis(),
            return_exceptions=True,
        )

        for result in checks:
            if isinstance(result, SubsystemStatus):
                report.subsystems.append(result)
            elif isinstance(result, Exception):
                report.subsystems.append(SubsystemStatus(
                    name="unknown", healthy=False, details=str(result)
                ))

        # Cost data
        cost_data = await self._get_cost_data()
        report.cost_today = cost_data.get("today", 0.0)
        report.cost_week = cost_data.get("week", 0.0)
        report.cost_top_models = cost_data.get("top_models", [])
        report.call_count_today = cost_data.get("call_count", 0)

        # Memory data
        if self._memory_manager:
            try:
                report.episode_count = await self._memory_manager._episodic.count()
                items = await self._memory_manager.get_high_confidence_items(limit=100)
                report.structured_items = len(items)
            except Exception:
                pass

        return report

    async def _check_lm_studio(self) -> SubsystemStatus:
        """Check LM Studio health via /v1/models."""
        import httpx
        start = time.time()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self._lm_studio_url}/v1/models")
                latency = int((time.time() - start) * 1000)
                if r.status_code == 200:
                    data = r.json()
                    models = [m.get("id", "?") for m in data.get("data", [])]
                    return SubsystemStatus(
                        name="LM Studio", healthy=True,
                        details=f"Models: {', '.join(models[:3])}",
                        latency_ms=latency,
                    )
                return SubsystemStatus(
                    name="LM Studio", healthy=False,
                    details=f"HTTP {r.status_code}", latency_ms=latency,
                )
        except Exception as e:
            return SubsystemStatus(name="LM Studio", healthy=False, details=str(e))

    async def _check_qdrant(self) -> SubsystemStatus:
        """Check Qdrant health via /healthz."""
        import httpx
        start = time.time()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self._qdrant_url}/healthz")
                latency = int((time.time() - start) * 1000)
                return SubsystemStatus(
                    name="Qdrant",
                    healthy=(r.status_code == 200),
                    details=r.text[:50],
                    latency_ms=latency,
                )
        except Exception as e:
            return SubsystemStatus(name="Qdrant", healthy=False, details=str(e))

    async def _check_redis(self) -> SubsystemStatus:
        """Check Redis via ping."""
        start = time.time()
        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(self._redis_url, decode_responses=True)
            pong = await r.ping()
            latency = int((time.time() - start) * 1000)
            await r.close()
            return SubsystemStatus(
                name="Redis", healthy=pong, latency_ms=latency,
            )
        except Exception as e:
            return SubsystemStatus(name="Redis", healthy=False, details=str(e))

    async def _get_cost_data(self) -> dict:
        """Query cost_log for today and weekly totals."""
        if not self._db_path:
            return {}
        try:
            async with aiosqlite.connect(self._db_path) as db:
                # Today
                cur = await db.execute(
                    "SELECT COALESCE(SUM(cost_usd), 0), COUNT(*) FROM cost_log WHERE date(timestamp) = date('now')"
                )
                row = await cur.fetchone()
                today = row[0] if row else 0.0
                count = row[1] if row else 0

                # Week
                cur = await db.execute(
                    "SELECT COALESCE(SUM(cost_usd), 0) FROM cost_log WHERE timestamp >= datetime('now', '-7 days')"
                )
                row = await cur.fetchone()
                week = row[0] if row else 0.0

                # Top models
                cur = await db.execute(
                    """SELECT model, SUM(cost_usd) as total FROM cost_log
                       WHERE date(timestamp) = date('now')
                       GROUP BY model ORDER BY total DESC LIMIT 5"""
                )
                top_models = [(r[0], r[1]) for r in await cur.fetchall()]

                return {
                    "today": today, "week": week,
                    "call_count": count, "top_models": top_models,
                }
        except Exception as e:
            logger.warning(f"Cost data query failed: {e}")
            return {}
