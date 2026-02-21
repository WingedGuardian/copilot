"""Status aggregator: collects health, cost, memory, and channel data."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import aiosqlite
from loguru import logger


def _format_ago(timestamp_str: str) -> str:
    """Format a DB timestamp as a human-readable 'Xh Ym ago' string."""
    try:
        ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=None)  # treat as naive UTC
        delta = datetime.now(tz=None) - ts.replace(tzinfo=None)
        total_seconds = int(delta.total_seconds())
        if total_seconds < 120:
            return f"{total_seconds}s ago"
        minutes = total_seconds // 60
        if minutes < 120:
            return f"{minutes}m ago"
        hours = minutes // 60
        remaining_m = minutes % 60
        if hours < 48:
            return f"{hours}h {remaining_m}m ago" if remaining_m else f"{hours}h ago"
        days = hours // 24
        return f"{days}d ago"
    except Exception:
        return timestamp_str


@dataclass
class SubsystemStatus:
    """Health status of a single subsystem."""

    name: str
    healthy: bool
    details: str = ""
    latency_ms: int = 0


@dataclass
class ModelInfo:
    """Info about a configured model tier."""

    tier: str  # "fast", "big", "local"
    model: str
    provider: str = ""  # e.g. "openrouter", "venice", "lm_studio"
    healthy: bool | None = None  # None = not checked
    latency_ms: int = 0


@dataclass
class RoutingState:
    """Current routing mode and active target."""

    mode: str = "auto"  # "auto", "private", "override"
    active_tier: str = ""  # "fast", "big", "local"
    active_provider: str = ""  # e.g. "openrouter"
    active_model: str = ""
    override_detail: str = ""  # e.g. "/use venice" or "private mode"


@dataclass
class DashboardReport:
    """Aggregated status report."""

    subsystems: list[SubsystemStatus] = field(default_factory=list)
    models: list[ModelInfo] = field(default_factory=list)
    routing: RoutingState = field(default_factory=RoutingState)
    cost_today: float = 0.0
    cost_week: float = 0.0
    cost_top_models: list[tuple[str, float]] = field(default_factory=list)
    call_count_today: int = 0
    episode_count: int = 0
    structured_items: int = 0
    session_count: int = 0
    slm_queue: dict = field(default_factory=dict)  # from SlmWorkQueue.stats()
    slm_queue_connected: bool = False
    recent_alerts: list[dict] = field(default_factory=list)  # last 24h, deduped
    current_session_tokens: int = 0
    context_window: int = 0
    active_sessions: int = 0
    total_sessions: int = 0
    ops_summary: dict = field(default_factory=dict)  # last dream/heartbeat/alert counts
    extraction_stats: dict = field(default_factory=dict)  # last extraction info
    queue_breakdown: dict = field(default_factory=dict)  # by work_type
    services: dict = field(default_factory=dict)  # from ProcessSupervisor.get_status()

    def to_text(self) -> str:
        """Format as readable text."""
        lines = ["System Status"]
        lines.append("")

        # Routing
        r = self.routing
        if r.mode == "private":
            lines.append("Routing: PRIVATE MODE (local only)")
            lines.append(f"  -> {r.active_provider}: {r.active_model}")
        elif r.mode == "emergency":
            lines.append("Routing: ⚠️ EMERGENCY FALLBACK")
            lines.append(f"  -> {r.active_provider}: {r.active_model}")
            lines.append("  Configured models unavailable — check Active Alerts")
        elif r.mode == "override":
            lines.append(f"Routing: MANUAL ({r.override_detail})")
            lines.append(f"  -> {r.active_provider}: {r.active_model}")
        else:
            lines.append("Routing: auto")
            if r.active_provider:
                lines.append(f"  Last -> {r.active_provider}: {r.active_model} ({r.active_tier})")
        # Context
        if self.context_window > 0:
            pct = int((self.current_session_tokens / self.context_window) * 100)
            lines.append(f"  This session: {self.current_session_tokens:,} / {self.context_window:,} tokens ({pct}%)")
        if self.total_sessions > 0:
            lines.append(f"  Active sessions (1h): {self.active_sessions}")
            lines.append(f"  Total sessions: {self.total_sessions}")
        lines.append("")

        # Health
        lines.append("Health:")
        for s in self.subsystems:
            icon = "OK" if s.healthy else "DOWN"
            latency = f" ({s.latency_ms}ms)" if s.latency_ms else ""
            detail = f" - {s.details}" if s.details else ""
            lines.append(f"  {s.name}: {icon}{latency}{detail}")

        # Services (from ProcessSupervisor)
        if self.services:
            lines.append("")
            lines.append("Services:")
            for svc_name, svc_info in self.services.items():
                alive = svc_info.get("alive", False)
                restarts = svc_info.get("restarts", 0)
                icon = "OK" if alive else "DEAD"
                restart_note = f" ({restarts} restarts)" if restarts > 0 else ""
                lines.append(f"  {svc_name}: {icon}{restart_note}")

        # Models
        if self.models:
            lines.append("")
            lines.append("Models:")
            for m in self.models:
                if m.healthy is None:
                    icon = "?"
                elif m.healthy:
                    icon = "OK"
                else:
                    icon = "DOWN"
                latency = f" ({m.latency_ms}ms)" if m.latency_ms else ""
                lines.append(f"  {m.tier}: {m.provider}: {m.model} [{icon}]{latency}")

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

        # Extraction & Embedding
        ext = self.extraction_stats
        if ext:
            lines.append("")
            lines.append("Background Processing:")
            src = ext.get("last_source", "none")
            lines.append(f"  Extraction: {src}")
            if ext.get("extractions_today"):
                lines.append(f"  Extractions today: {ext['extractions_today']}")
            if ext.get("last_extraction_ago"):
                lines.append(f"  Last extraction: {ext['last_extraction_ago']}")
            embed_src = "local" if ext.get("embedding_local") else "cloud" if ext.get("embedding_cloud") else "down"
            lines.append(f"  Embedding: {embed_src}")

        # Active Alerts (unresolved only)
        lines.append("")
        lines.append("Active Alerts:")
        if self.recent_alerts:
            for a in self.recent_alerts:
                ts = a.get("timestamp", "?")
                sev = a.get("severity", "?").upper()
                sub = a.get("subsystem", "?")
                msg = a.get("message", "")
                count = a.get("occurrences", 1)
                suffix = f" (x{count})" if count > 1 else ""
                lines.append(f"  [{sev}] {sub}: {msg}{suffix}")
        else:
            lines.append("  All clear")

        # Last Operations
        if self.ops_summary:
            lines.append("")
            lines.append("Last Operations:")
            ops = self.ops_summary
            if ops.get("dream_ago") is not None:
                errors = ops.get("dream_errors", 0)
                err_str = f", {errors} error(s)" if errors else ""
                lines.append(f"  Dream cycle: {ops['dream_ago']}{err_str}")
            else:
                lines.append("  Dream cycle: never run")
            if ops.get("health_check_ago") is not None:
                lines.append(f"  Health check: {ops['health_check_ago']}")
            else:
                lines.append("  Health check: not yet")
            if ops.get("heartbeat_ago") is not None:
                lines.append(f"  Heartbeat: {ops['heartbeat_ago']}")
            else:
                lines.append("  Heartbeat: not yet")
            if ops.get("weekly_ago") is not None:
                lines.append(f"  Weekly review: {ops['weekly_ago']}")
            else:
                lines.append("  Weekly review: never run")
            alert_h = ops.get("alerts_high_24h", 0)
            alert_m = ops.get("alerts_med_24h", 0)
            if alert_h or alert_m:
                lines.append(f"  Alerts (24h): {alert_h} high, {alert_m} medium")
            else:
                lines.append("  Alerts (24h): none")

        # SLM Queue
        lines.append("")
        lines.append("SLM Queue:")
        if not self.slm_queue_connected:
            lines.append("  Not connected")
        elif self.slm_queue:
            q = self.slm_queue
            total = q.get("total_queued", 0)
            processed = q.get("total_processed", 0)
            rate = f"{processed}/{total}" if total else "0/0"
            pending = q.get('current_size', 0)
            lines.append(f"  Pending: {pending}")
            qb = self.queue_breakdown
            if qb and pending > 0:
                parts = []
                for wt, cnt in sorted(qb.items()):
                    if cnt > 0:
                        parts.append(f"{cnt} {wt}")
                if parts:
                    lines.append(f"    ({', '.join(parts)})")
            lines.append(f"  Processed: {rate}")
            dropped = q.get('total_dropped', 0)
            if dropped:
                lines.append(f"  Dropped (queue full): {dropped}")
            ts = q.get("last_drain_ts", 0)
            if ts:
                import time
                ago = int(time.time() - ts)
                if ago < 120:
                    lines.append(f"  Last drain: {ago}s ago")
                else:
                    lines.append(f"  Last drain: {ago // 60}m ago")
        else:
            lines.append("  Empty (local SLM handling extractions directly)")

        return "\n".join(lines)


class StatusAggregator:
    """Collects status from all subsystems."""

    def __init__(
        self,
        db_path: str = "",
        lm_studio_url: str = "http://192.168.50.100:1234",
        qdrant_url: str = "http://localhost:6333",
        memory_manager: Any = None,
        cron_service: Any = None,
        channel_manager: Any = None,
        session_manager: Any = None,
        router: Any = None,
        **kwargs,  # Accept and ignore legacy kwargs (redis_url, timezone_name, copilot_config)
    ):
        self._db_path = db_path
        self._lm_studio_url = lm_studio_url
        self._qdrant_url = qdrant_url
        self._memory_manager = memory_manager
        self._cron_service = cron_service
        self._channel_manager = channel_manager
        self._session_manager = session_manager
        self._router = router
        self._heartbeat = None  # Set externally: HeartbeatService instance
        self._supervisor = None  # Set externally: ProcessSupervisor instance

    async def collect(self, session_metadata: dict | None = None, session=None, session_manager=None) -> DashboardReport:
        """Run all checks in parallel and assemble report."""
        report = DashboardReport()

        # Routing state from session + router
        if self._router:
            report.routing = self._build_routing_state(session_metadata)

        checks = await asyncio.gather(
            self._check_lm_studio(),
            self._check_qdrant(),
            return_exceptions=True,
        )

        for result in checks:
            if isinstance(result, SubsystemStatus):
                report.subsystems.append(result)
            elif isinstance(result, Exception):
                report.subsystems.append(SubsystemStatus(
                    name="unknown", healthy=False, details=str(result)
                ))

        # Supervised service status
        if self._supervisor:
            try:
                report.services = self._supervisor.get_status()
            except Exception:
                pass

        # Model info + health
        if self._router:
            model_checks = await self._check_cloud_models()
            report.models = model_checks

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

        # Recent alerts (from AlertBus SQLite table)
        report.recent_alerts = await self._get_recent_alerts()

        # Session & token context
        if session:
            try:
                from nanobot.copilot.context.budget import TokenBudget
                budget = TokenBudget()
                history = session.get_history() if hasattr(session, 'get_history') else session.messages
                report.current_session_tokens = budget.count_messages_tokens(history)
                model = (report.routing.active_model or "anthropic/claude-sonnet-4-20250514")
                report.context_window = budget.get_window(model)
            except Exception:
                pass
        if session_manager:
            try:
                all_sessions = session_manager.list_sessions()
                report.total_sessions = len(all_sessions)
                cutoff = (datetime.now() - timedelta(hours=1)).isoformat()
                report.active_sessions = sum(
                    1 for s in all_sessions if (s.get("updated_at") or "") >= cutoff
                )
            except Exception:
                pass

        # Operational history
        report.ops_summary = await self._get_ops_summary()

        # SLM queue stats + breakdown
        slm_queue = getattr(self, "_slm_queue", None)
        if slm_queue:
            report.slm_queue_connected = True
            try:
                report.slm_queue = await slm_queue.stats()
            except Exception:
                pass
            try:
                report.queue_breakdown = await slm_queue.breakdown()
            except Exception:
                pass

        # Extraction & embedding stats
        report.extraction_stats = await self._get_extraction_stats()

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

    async def _get_extraction_stats(self) -> dict:
        """Get extraction health indicators."""
        result: dict = {}
        # Check extractor state
        extractor = getattr(self, "_extractor", None)
        if extractor:
            # Last extraction source from the extractor's internal state
            result["last_source"] = getattr(extractor, "_last_source", "unknown")

        # Check embedder state
        memory = self._memory_manager
        if memory and hasattr(memory, "_embedder"):
            embedder = memory._embedder
            result["embedding_local"] = getattr(embedder, "_local_available", False)
            result["embedding_cloud"] = bool(getattr(embedder, "_cloud_api_key", None))

        # Count extractions today from cost_log (haiku calls for extraction)
        if self._db_path:
            try:
                async with aiosqlite.connect(self._db_path) as db:
                    cur = await db.execute(
                        "SELECT COUNT(*) FROM cost_log "
                        "WHERE date(timestamp) = date('now') "
                        "AND model LIKE '%haiku%'"
                    )
                    row = await cur.fetchone()
                    if row and row[0]:
                        result["extractions_today"] = row[0]
            except Exception:
                pass

        return result

    async def _get_recent_alerts(self) -> list[dict]:
        """Query alerts table for unresolved (active) warnings/errors, deduped."""
        if not self._db_path:
            return []
        try:
            async with aiosqlite.connect(self._db_path) as db:
                db.row_factory = aiosqlite.Row
                cur = await db.execute(
                    """SELECT subsystem, severity, message,
                              MAX(timestamp) as timestamp, COUNT(*) as occurrences
                       FROM alerts
                       WHERE resolved_at IS NULL
                         AND severity IN ('high', 'medium')
                       GROUP BY error_key
                       ORDER BY timestamp DESC
                       LIMIT 10"""
                )
                rows = await cur.fetchall()
                return [
                    {
                        "subsystem": r["subsystem"],
                        "severity": r["severity"],
                        "message": r["message"][:120],
                        "timestamp": r["timestamp"],
                        "occurrences": r["occurrences"],
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.debug(f"Alert query failed: {e}")
            return []

    async def _check_cloud_models(self) -> list[ModelInfo]:
        """Check configured model tiers and probe cloud provider health."""
        import httpx

        router = self._router
        # Show plan-based routing info if available, otherwise default/escalation
        if hasattr(router, '_routing_plan') and router._routing_plan:
            tiers = []
            for entry in router._routing_plan:
                tiers.append((f"plan:{entry.get('provider', '?')}", entry.get("model", "?")))
            tiers.append(("escalation", getattr(router, "_escalation_model", "?")))
            tiers.append(("local", router._local_model))
        else:
            tiers = [
                ("default", getattr(router, "_default_model", router._fast_model)),
                ("escalation", getattr(router, "_escalation_model", router._big_model)),
                ("local", router._local_model),
            ]

        # Collect unique cloud provider base URLs to probe
        provider_health: dict[str, bool | None] = {}
        provider_latency: dict[str, int] = {}

        for name, provider in router._cloud.items():
            if name in provider_health:
                continue
            base_url = getattr(provider, "api_base", "") or ""
            if not base_url:
                provider_health[name] = None
                continue
            # Probe /v1/models (works for OpenRouter, OpenAI-compatible APIs)
            try:
                start = time.time()
                async with httpx.AsyncClient(timeout=5.0) as client:
                    r = await client.get(
                        f"{base_url.rstrip('/')}/models",
                        headers={"Authorization": f"Bearer {getattr(provider, 'api_key', '') or ''}"},
                    )
                latency = int((time.time() - start) * 1000)
                provider_health[name] = r.status_code == 200
                provider_latency[name] = latency
            except Exception:
                provider_health[name] = False

        # Also check local provider
        if router._local:
            local_base = getattr(router._local, "api_base", "") or self._lm_studio_url
            try:
                start = time.time()
                async with httpx.AsyncClient(timeout=5.0) as client:
                    r = await client.get(f"{local_base.rstrip('/')}/v1/models")
                latency = int((time.time() - start) * 1000)
                provider_health["local"] = r.status_code == 200
                provider_latency["local"] = latency
            except Exception:
                provider_health["local"] = False

        # Map tiers to health
        first_cloud = next(iter(router._cloud), None) or "cloud"
        results = []
        for tier, model in tiers:
            if tier == "local":
                healthy = provider_health.get("local")
                latency = provider_latency.get("local", 0)
                provider_name = "lm_studio"
            else:
                healthy = provider_health.get(first_cloud) if first_cloud else None
                latency = provider_latency.get(first_cloud, 0) if first_cloud else 0
                provider_name = first_cloud
            results.append(ModelInfo(
                tier=tier, model=model, provider=provider_name,
                healthy=healthy, latency_ms=latency,
            ))

        return results

    async def _get_ops_summary(self) -> dict:
        """Query last dream cycle, last heartbeat, and recent alert counts."""
        if not self._db_path:
            return {}
        result: dict = {}
        try:
            async with aiosqlite.connect(self._db_path) as db:
                # Last dream cycle
                cur = await db.execute(
                    "SELECT run_at, errors FROM dream_cycle_log ORDER BY run_at DESC LIMIT 1"
                )
                row = await cur.fetchone()
                if row:
                    result["dream_ago"] = _format_ago(row[0])
                    result["dream_errors"] = len(row[1].split(";")) if row[1] else 0

                # Health check (programmatic, 30m interval)
                if getattr(self, '_health_check', None) and getattr(self._health_check, 'last_tick_at', None):
                    result["health_check_ago"] = _format_ago(
                        self._health_check.last_tick_at.strftime("%Y-%m-%d %H:%M:%S")
                    )

                # Nanobot heartbeat (HEARTBEAT.md agent check-in, 2h interval)
                if self._heartbeat and self._heartbeat.last_tick_at:
                    result["heartbeat_ago"] = _format_ago(
                        self._heartbeat.last_tick_at.strftime("%Y-%m-%d %H:%M:%S")
                    )

                # Last weekly review
                cur = await db.execute(
                    "SELECT created_at FROM heartbeat_events "
                    "WHERE event_type = 'weekly_review' ORDER BY created_at DESC LIMIT 1"
                )
                row = await cur.fetchone()
                if row:
                    result["weekly_ago"] = _format_ago(row[0])

                # Alert counts (24h)
                cur = await db.execute(
                    """SELECT severity, COUNT(*) FROM alerts
                       WHERE timestamp >= datetime('now', '-24 hours')
                         AND severity IN ('high', 'medium')
                       GROUP BY severity"""
                )
                for sev, cnt in await cur.fetchall():
                    if sev == "high":
                        result["alerts_high_24h"] = cnt
                    elif sev == "medium":
                        result["alerts_med_24h"] = cnt
        except Exception as e:
            logger.debug(f"Ops summary query failed: {e}")
        return result

    def _build_routing_state(self, session_metadata: dict | None) -> RoutingState:
        """Determine current routing mode from session metadata and router."""
        router = self._router
        meta = session_metadata or {}
        first_cloud = next(iter(router._cloud), None) or ""

        if meta.get("private_mode"):
            return RoutingState(
                mode="private", active_tier="local",
                active_provider="lm_studio", active_model=router._local_model,
            )

        force_provider = meta.get("force_provider")
        if force_provider:
            tier = meta.get("force_tier", "big")
            default_m = getattr(router, "_default_model", router._fast_model)
            escalation_m = getattr(router, "_escalation_model", router._big_model)
            model = meta.get("force_model") or (
                default_m if tier == "fast" else escalation_m
            )
            return RoutingState(
                mode="override", active_tier=tier,
                active_provider=force_provider, active_model=model,
                override_detail=f"/use {force_provider}",
            )

        # Auto mode — show last decision if available
        last = router.last_decision
        if last:
            winning = getattr(router, "_last_winning_provider", "")
            is_emergency = winning.startswith("emergency:")
            if winning:
                clean_provider = winning.removeprefix("plan:").removeprefix("safety:")
            else:
                clean_provider = "lm_studio" if last.target == "local" else first_cloud
            provider = clean_provider
            if is_emergency:
                # Emergency routing fired — show the actual fallback that was used
                actual_provider = winning.removeprefix("emergency:")
                return RoutingState(
                    mode="emergency", active_tier=last.target,
                    active_provider=actual_provider, active_model=last.model,
                    override_detail="EMERGENCY FALLBACK (configured models unavailable)",
                )
            return RoutingState(
                mode="auto", active_tier=last.target,
                active_provider=provider, active_model=last.model,
            )

        # No in-memory decision (e.g. after restart) — check routing_log DB
        if self._db_path:
            try:
                import sqlite3 as _sqlite3
                with _sqlite3.connect(self._db_path) as db:
                    row = db.execute(
                        "SELECT routed_to, provider, model_used FROM routing_log "
                        "ORDER BY timestamp DESC LIMIT 1"
                    ).fetchone()
                    if row:
                        return RoutingState(
                            mode="auto", active_tier=row[0] or "",
                            active_provider=row[1] or first_cloud,
                            active_model=row[2] or "",
                        )
            except Exception:
                pass

        return RoutingState(mode="auto")
