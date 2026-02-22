"""Timezone-aware datetime helpers for copilot services.

Call tz.init(config.timezone) once at copilot startup.
Falls back to America/New_York if not initialized.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

_tz: ZoneInfo | None = None


def init(timezone_str: str) -> None:
    """Call once at startup from copilot init. Reads config.copilot.timezone."""
    global _tz
    _tz = ZoneInfo(timezone_str)


def get_tz() -> ZoneInfo:
    return _tz or ZoneInfo("America/New_York")


def local_now() -> datetime:
    return datetime.now(tz=get_tz())


def local_date(offset_days: int = 0) -> date:
    return (local_now() + timedelta(days=offset_days)).date()


def local_date_str(offset_days: int = 0) -> str:
    """YYYY-MM-DD string for use as SQL parameter."""
    return local_date(offset_days).isoformat()


def local_datetime_str(offset_days: int = 0, offset_hours: int = 0, offset_minutes: int = 0) -> str:
    """ISO datetime string for use as SQL parameter."""
    dt = local_now() + timedelta(days=offset_days, hours=offset_hours, minutes=offset_minutes)
    return dt.strftime("%Y-%m-%d %H:%M:%S")
