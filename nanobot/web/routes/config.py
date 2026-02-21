"""Config editor — read/write CopilotConfig via ~/.nanobot/config.json."""

from __future__ import annotations

import json
import logging
import pathlib
import typing

import aiohttp_jinja2
from aiohttp import web

from nanobot.copilot.config import CopilotConfig

logger = logging.getLogger(__name__)
_CONFIG_PATH = pathlib.Path.home() / ".nanobot" / "config.json"


def _get_field_type(annotation) -> str:
    """Return a simple type string for rendering the correct input widget."""
    if annotation is None:
        return "str"
    origin = getattr(annotation, "__origin__", None)
    args = getattr(annotation, "__args__", ())
    # Optional[X] / Union[X, None]
    if origin is typing.Union:
        non_none = [a for a in args if a is not type(None)]
        if non_none:
            return _get_field_type(non_none[0])
    if annotation is bool:
        return "bool"
    if annotation is int:
        return "int"
    if annotation is float:
        return "float"
    if annotation is str:
        return "str"
    if origin is list or annotation is list:
        return "list"
    if origin is dict or annotation is dict:
        return "dict"
    return "str"


def _field_section(name: str) -> str:
    """Map a field name to a display section."""
    if name in ("enabled",):
        return "General"
    if name.endswith("_model") or name in (
        "local_model",
        "routing_model",
        "fast_model",
        "big_model",
        "dream_model",
        "heartbeat_model",
        "weekly_model",
        "monthly_model",
        "task_model",
        "decomposition_model",
        "navigator_model",
        "escalation_model",
        "default_conversation_model",
        "emergency_cloud_model",
        "extraction_local_model",
        "extraction_cloud_model",
        "embedding_local_model",
        "cloud_embedding_model",
        "cloud_extraction_model",
    ):
        return "Models"
    if name in (
        "dream_cron_expr",
        "weekly_review_cron_expr",
        "monthly_review_cron_expr",
    ):
        return "Scheduling"
    if name in (
        "daily_cost_alert",
        "per_call_cost_alert",
    ):
        return "Costs"
    if name in (
        "embedding_local_dimensions",
        "cloud_embedding_api_key",
        "cloud_embedding_api_base",
        "cloud_embedding_dimensions",
        "cloud_extraction_api_key",
        "cloud_extraction_api_base",
        "qdrant_url",
        "memory_recall_limit",
        "memory_min_score",
    ):
        return "Memory"
    if name in (
        "private_mode_timeout",
        "use_override_timeout",
        "daily_session_reset",
        "daily_reset_hour",
        "daily_reset_quiet_minutes",
        "context_budget",
        "continuation_threshold",
    ):
        return "Session"
    if name in (
        "monitor_interval",
        "health_check_interval",
        "monitor_channel",
        "monitor_chat_id",
        "alert_dedup_hours",
        "alert_mute_hours",
    ):
        return "Monitoring"
    if name in (
        "navigator_enabled",
        "max_duo_rounds",
        "max_review_cycles",
    ):
        return "Navigator"
    if name in (
        "slm_queue_enabled",
        "slm_queue_size_limit",
        "slm_drain_rate",
        "task_worker_interval",
    ):
        return "Queue"
    if name in (
        "escalation_enabled",
        "escalation_marker",
        "routing_plan",
        "routing_plan_notify",
    ):
        return "Routing"
    return "Other"


# Ordered sections for display
_SECTION_ORDER = [
    "General",
    "Models",
    "Scheduling",
    "Costs",
    "Memory",
    "Session",
    "Monitoring",
    "Navigator",
    "Queue",
    "Routing",
    "Other",
]


def _build_sections(cfg: CopilotConfig) -> list[dict]:
    """Return ordered list of {title, fields: [{name, type, value}]}."""
    buckets: dict[str, list[dict]] = {s: [] for s in _SECTION_ORDER}
    for field_name, field_info in CopilotConfig.model_fields.items():
        ann = field_info.annotation
        ftype = _get_field_type(ann)
        value = getattr(cfg, field_name)
        # Render lists/dicts as JSON strings for the textarea
        if ftype in ("list", "dict"):
            display_value = json.dumps(value, indent=2)
        else:
            display_value = value
        section = _field_section(field_name)
        buckets[section].append(
            {
                "name": field_name,
                "type": ftype,
                "value": display_value,
            }
        )
    return [{"title": s, "fields": buckets[s]} for s in _SECTION_ORDER if buckets[s]]


@aiohttp_jinja2.template("pages/config.html")
async def get_config(request: web.Request) -> dict:
    raw = {}
    if _CONFIG_PATH.exists():
        raw = json.loads(_CONFIG_PATH.read_text()).get("copilot", {})
    try:
        cfg = CopilotConfig.model_validate(raw)
    except Exception:
        cfg = CopilotConfig()
    saved = request.rel_url.query.get("saved") == "1"
    return {
        "active": "config",
        "cfg": cfg,
        "sections": _build_sections(cfg),
        "saved": saved,
        "errors": [],
    }


async def post_config(request: web.Request) -> web.Response:
    form = await request.post()
    raw_new: dict = {}

    for field_name, field_info in CopilotConfig.model_fields.items():
        if field_name not in form:
            continue
        val = form[field_name]
        ann = field_info.annotation
        ftype = _get_field_type(ann)
        try:
            if ftype == "bool":
                raw_new[field_name] = val.lower() in ("1", "true", "yes", "on")
            elif ftype == "int":
                raw_new[field_name] = int(val)
            elif ftype == "float":
                raw_new[field_name] = float(val)
            elif ftype in ("list", "dict"):
                raw_new[field_name] = json.loads(val)
            else:
                raw_new[field_name] = val
        except (ValueError, TypeError, json.JSONDecodeError):
            raw_new[field_name] = val

    errors: list[str] = []
    try:
        cfg = CopilotConfig.model_validate(raw_new)
    except Exception as exc:
        errors = [str(exc)]
        cfg = CopilotConfig()

    if not errors:
        existing: dict = {}
        if _CONFIG_PATH.exists():
            existing = json.loads(_CONFIG_PATH.read_text())
        existing["copilot"] = cfg.model_dump()
        _CONFIG_PATH.write_text(json.dumps(existing, indent=2))
        logger.info("Config saved via web UI")
        raise web.HTTPSeeOther("/config?saved=1")

    response = aiohttp_jinja2.render_template(
        "pages/config.html",
        request,
        {
            "active": "config",
            "cfg": cfg,
            "sections": _build_sections(cfg),
            "saved": False,
            "errors": errors,
        },
    )
    return response


def setup(app: web.Application) -> None:
    app.router.add_get("/config", get_config)
    app.router.add_post("/config", post_config)
