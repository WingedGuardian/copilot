"""Agent tool for changing copilot runtime preferences via natural language."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from loguru import logger

from nanobot.agent.tools.base import Tool

# Fields the LLM is allowed to change (no secrets, no security settings)
_ALLOWED_KEYS = {
    "fast_model", "big_model", "local_model",
    "default_conversation_model", "escalation_model", "routing_plan_notify",
    "dream_model", "heartbeat_model", "weekly_model", "monthly_model",
    "dream_cron_expr", "weekly_review_cron_expr", "monthly_review_cron_expr", "health_check_interval",
    "use_override_timeout", "daily_cost_alert", "per_call_cost_alert",
    "context_budget", "continuation_threshold",
    "lesson_injection_count", "lesson_min_confidence",
    "memory_recall_limit", "memory_min_score",
}

# Type coercion map (field name → target type)
_TYPE_MAP: dict[str, type] = {
    "health_check_interval": int,
    "use_override_timeout": int,
    "context_budget": int,
    "lesson_injection_count": int,
    "daily_cost_alert": float,
    "per_call_cost_alert": float,
    "lesson_min_confidence": float,
    "memory_min_score": float,
    "memory_recall_limit": int,
    "continuation_threshold": float,
}


_AUTONOMY_MODES = {"notify", "autonomous", "disabled"}
_AUTONOMY_CATEGORIES = {
    "task_management", "identity_evolution", "config_changes",
    "proactive_notifications", "memory_management", "scheduling",
}


class SetPreferenceTool(Tool):
    """Change a copilot runtime preference. Changes take effect immediately and persist."""

    def __init__(
        self,
        config_path: Path,
        copilot_config: Any,
        router: Any = None,
        reschedule_callbacks: dict[str, Callable] | None = None,
        db_path: str = "",
    ):
        self._config_path = config_path
        self._copilot = copilot_config
        self._router = router
        self._reschedule = reschedule_callbacks or {}
        self._db_path = db_path

    @property
    def name(self) -> str:
        return "set_preference"

    @property
    def description(self) -> str:
        return (
            "Change a copilot runtime preference. "
            "Supported keys: default_conversation_model, escalation_model, "
            "fast_model, big_model, local_model, routing_plan_notify, "
            "dream_cron_expr, health_check_interval, use_override_timeout, "
            "daily_cost_alert, per_call_cost_alert, context_budget, "
            "lesson_injection_count, lesson_min_confidence, "
            "memory_recall_limit, memory_min_score. "
            "Also supports 'autonomy:<category>' keys (e.g. autonomy:task_management) "
            "with values: notify, autonomous, disabled. "
            "Changes take effect immediately and persist across restarts."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Config field name"},
                "value": {"type": "string", "description": "New value (string representation)"},
            },
            "required": ["key", "value"],
        }

    async def execute(self, **kwargs: Any) -> str:
        key = kwargs.get("key", "")
        value = kwargs.get("value", "")

        # Handle autonomy: prefix
        if key.startswith("autonomy:"):
            return await self._set_autonomy(key, value)

        if key not in _ALLOWED_KEYS:
            return f"Error: '{key}' is not a configurable preference. Allowed: {', '.join(sorted(_ALLOWED_KEYS))}"

        # Type-coerce
        target_type = _TYPE_MAP.get(key, str)
        try:
            typed_value = target_type(value)
        except (ValueError, TypeError):
            return f"Error: cannot convert '{value}' to {target_type.__name__} for '{key}'"

        # Validate ranges for numeric fields
        if isinstance(typed_value, (int, float)):
            if key == "health_check_interval" and typed_value < 60:
                return f"Error: health_check_interval must be >= 60 seconds, got {typed_value}"
            if key == "use_override_timeout" and typed_value < 60:
                return f"Error: use_override_timeout must be >= 60 seconds, got {typed_value}"
            if key in ("lesson_min_confidence", "memory_min_score", "continuation_threshold"):
                if not (0.0 <= typed_value <= 1.0):
                    return f"Error: {key} must be between 0.0 and 1.0, got {typed_value}"
            if key in ("daily_cost_alert", "per_call_cost_alert") and typed_value < 0:
                return f"Error: {key} must be >= 0, got {typed_value}"
            if key in ("context_budget", "lesson_injection_count", "memory_recall_limit") and typed_value < 1:
                return f"Error: {key} must be >= 1, got {typed_value}"

        # Update in-memory config
        old_value = getattr(self._copilot, key, None)
        setattr(self._copilot, key, typed_value)

        # Hot-swap router models
        _model_tier_map = {
            "fast_model": "fast",
            "big_model": "big",
            "local_model": "local",
            "default_conversation_model": "default",
            "escalation_model": "escalation",
        }
        if self._router and key in _model_tier_map:
            self._router.set_model(_model_tier_map[key], typed_value)

        # Trigger reschedule callbacks (dream cron, heartbeat interval, etc.)
        if key in self._reschedule:
            try:
                self._reschedule[key](typed_value)
            except Exception as e:
                logger.warning(f"Reschedule callback for {key} failed: {e}")

        # Persist to config.json
        try:
            self._persist(key, typed_value)
        except Exception as e:
            logger.warning(f"Config persist failed: {e}")
            return f"Set {key}={typed_value} (in-memory only, persist failed: {e})"

        logger.info(f"Preference changed: {key} = {typed_value} (was {old_value})")
        return f"Updated {key}: {old_value} → {typed_value}"

    async def _set_autonomy(self, key: str, value: str) -> str:
        """Handle autonomy:<category> preference changes."""
        category = key.split(":", 1)[1]
        if category not in _AUTONOMY_CATEGORIES:
            return f"Error: unknown autonomy category '{category}'. Valid: {', '.join(sorted(_AUTONOMY_CATEGORIES))}"
        mode = value.lower().strip()
        if mode not in _AUTONOMY_MODES:
            return f"Error: autonomy mode must be one of {sorted(_AUTONOMY_MODES)}, got '{mode}'"

        if not self._db_path:
            return "Error: no database configured for autonomy permissions"

        import aiosqlite
        try:
            async with aiosqlite.connect(self._db_path) as db:
                cur = await db.execute(
                    "SELECT mode FROM autonomy_permissions WHERE category = ?",
                    (category,),
                )
                row = await cur.fetchone()
                old_mode = row[0] if row else "notify"
                await db.execute(
                    """INSERT INTO autonomy_permissions (category, mode, granted_at, granted_by)
                       VALUES (?, ?, CURRENT_TIMESTAMP, 'user')
                       ON CONFLICT(category) DO UPDATE SET
                         mode = excluded.mode,
                         granted_at = excluded.granted_at,
                         granted_by = excluded.granted_by""",
                    (category, mode),
                )
                await db.commit()
        except Exception as e:
            return f"Error updating autonomy permission: {e}"

        logger.info(f"Autonomy changed: {category} = {mode} (was {old_mode})")
        return f"Autonomy updated: {category}: {old_mode} → {mode}"

    def _persist(self, key: str, value: Any) -> None:
        """Update the copilot section in config.json."""
        if not self._config_path.exists():
            return
        with open(self._config_path) as f:
            data = json.load(f)

        from nanobot.config.loader import snake_to_camel
        camel_key = snake_to_camel(key)
        copilot = data.setdefault("copilot", {})
        copilot[camel_key] = value

        with open(self._config_path, "w") as f:
            json.dump(data, f, indent=2)
