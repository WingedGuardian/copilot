"""Tests for the unified alert bus."""

import asyncio
import time

import pytest

from nanobot.copilot.alerting.bus import AlertBus
from nanobot.copilot.alerting.commands import detect_alert_command


@pytest.fixture
def bus(tmp_path):
    """Create an AlertBus with in-memory delivery tracking."""
    import aiosqlite

    db_path = str(tmp_path / "test.db")

    # Create table
    async def _setup():
        async with aiosqlite.connect(db_path) as db:
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    subsystem TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    error_key TEXT NOT NULL,
                    message TEXT NOT NULL,
                    delivered INTEGER DEFAULT 0
                );
            """)
            await db.commit()

    asyncio.get_event_loop().run_until_complete(_setup())

    delivered = []

    async def deliver(msg):
        delivered.append(msg)

    b = AlertBus(db_path, deliver_fn=deliver, dedup_hours=4.0)
    b._delivered = delivered  # attach for test inspection
    return b


@pytest.mark.asyncio
async def test_alert_dedup_within_window(bus):
    """Second HIGH alert with same key within window is suppressed."""
    await bus.alert("memory", "high", "Qdrant failed", "qdrant_store")
    await bus.alert("memory", "high", "Qdrant failed again", "qdrant_store")
    assert len(bus._delivered) == 1


@pytest.mark.asyncio
async def test_alert_dedup_after_window(bus):
    """HIGH alert after window expires is delivered."""
    await bus.alert("memory", "high", "fail 1", "qdrant_store")
    # Simulate window expiry
    bus._last_sent["memory:qdrant_store"] -= bus._dedup_seconds + 1
    await bus.alert("memory", "high", "fail 2", "qdrant_store")
    assert len(bus._delivered) == 2


@pytest.mark.asyncio
async def test_alert_medium_not_delivered(bus):
    """MEDIUM alerts are stored but not delivered via WhatsApp."""
    await bus.alert("memory", "medium", "minor issue", "qdrant_store")
    assert len(bus._delivered) == 0


@pytest.mark.asyncio
async def test_alert_severity_low_no_deliver(bus):
    """LOW alerts stored but not delivered."""
    await bus.alert("memory", "low", "minor issue", "access_count")
    assert len(bus._delivered) == 0


@pytest.mark.asyncio
async def test_alert_mute(bus):
    """Muted alerts stored but not delivered."""
    bus.mute_until(time.time() + 3600)
    await bus.alert("memory", "high", "critical", "qdrant_store")
    assert len(bus._delivered) == 0
    # Unmute and verify delivery resumes
    bus.unmute()
    await bus.alert("memory", "high", "critical 2", "qdrant_store")
    assert len(bus._delivered) == 1


@pytest.mark.asyncio
async def test_alert_set_frequency(bus):
    """Changing frequency affects dedup window."""
    bus.set_frequency(1.0)
    assert bus._dedup_seconds == 3600
    bus.set_frequency(0.5)  # clamped to 1h min
    assert bus._dedup_seconds == 3600
    bus.set_frequency(48.0)  # clamped to 24h max
    assert bus._dedup_seconds == 24 * 3600


def test_alert_command_detection():
    """Regex patterns match natural language."""
    assert detect_alert_command("notify me less often please") == "less"
    assert detect_alert_command("I want more alerts") == "more"
    assert detect_alert_command("mute alerts for now") == "mute"
    assert detect_alert_command("unmute alerts") == "unmute"
    assert detect_alert_command("show me the alert status") == "status"
    assert detect_alert_command("hello world") is None


@pytest.mark.asyncio
async def test_alert_sqlite_persistence(bus):
    """Alerts persisted to SQLite."""
    import aiosqlite

    await bus.alert("cron", "high", "job failed", "job_exec")

    async with aiosqlite.connect(bus._db_path) as db:
        cursor = await db.execute("SELECT subsystem, severity, error_key, message, delivered FROM alerts")
        rows = await cursor.fetchall()

    assert len(rows) == 1
    assert rows[0] == ("cron", "high", "job_exec", "job failed", 1)
