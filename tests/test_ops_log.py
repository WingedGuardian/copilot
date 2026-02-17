"""Tests for ops_log tool and heartbeat summary injection."""

import asyncio
import pytest
import aiosqlite


# --- Fixture: in-memory DB with operational tables ---

@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_ops.db")


@pytest.fixture
def _create_tables(db_path):
    """Create the operational tables used by ops_log."""
    async def _setup():
        async with aiosqlite.connect(db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS dream_cycle_log (
                    id INTEGER PRIMARY KEY,
                    run_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    duration_ms INTEGER DEFAULT 0,
                    episodes_consolidated INTEGER DEFAULT 0,
                    items_created INTEGER DEFAULT 0,
                    items_pruned INTEGER DEFAULT 0,
                    lessons_reviewed INTEGER DEFAULT 0,
                    alerts_count INTEGER DEFAULT 0,
                    remediations_count INTEGER DEFAULT 0,
                    errors TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS heartbeat_log (
                    id INTEGER PRIMARY KEY,
                    run_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    tasks_checked INTEGER DEFAULT 0,
                    tasks_with_results INTEGER DEFAULT 0,
                    duration_ms INTEGER DEFAULT 0,
                    summary TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS heartbeat_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    event_type TEXT NOT NULL,
                    severity TEXT DEFAULT 'info',
                    message TEXT NOT NULL,
                    source TEXT DEFAULT 'heartbeat',
                    acknowledged INTEGER DEFAULT 0
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    subsystem TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    error_key TEXT NOT NULL,
                    message TEXT NOT NULL,
                    delivered INTEGER DEFAULT 0
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS cost_log (
                    id INTEGER PRIMARY KEY,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    model TEXT,
                    tokens_input INTEGER,
                    tokens_output INTEGER,
                    cost_usd REAL,
                    task_type TEXT,
                    thread_id TEXT
                )
            """)
            await db.commit()
    asyncio.get_event_loop().run_until_complete(_setup())
    return db_path


# --- OpsLogTool tests ---

class TestOpsLogTool:

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_dream_empty(self, _create_tables, db_path):
        from nanobot.copilot.tools.ops_log import OpsLogTool
        tool = OpsLogTool(db_path=db_path)
        result = self._run(tool.execute(category="dream", hours=24))
        assert "No dream cycles" in result

    def test_dream_with_data(self, _create_tables, db_path):
        from nanobot.copilot.tools.ops_log import OpsLogTool
        async def _insert_and_query():
            async with aiosqlite.connect(db_path) as db:
                await db.execute(
                    "INSERT INTO dream_cycle_log (duration_ms, episodes_consolidated, items_pruned, lessons_reviewed) VALUES (1500, 3, 2, 5)"
                )
                await db.commit()
            tool = OpsLogTool(db_path=db_path)
            return await tool.execute(category="dream", hours=24)
        result = self._run(_insert_and_query())
        assert "1 run" in result
        assert "3 consolidated" in result
        assert "2 pruned" in result
        assert "5 lessons reviewed" in result

    def test_dream_with_errors(self, _create_tables, db_path):
        from nanobot.copilot.tools.ops_log import OpsLogTool
        async def _insert_and_query():
            async with aiosqlite.connect(db_path) as db:
                await db.execute(
                    "INSERT INTO dream_cycle_log (duration_ms, errors) VALUES (500, 'consolidation: timeout')"
                )
                await db.commit()
            tool = OpsLogTool(db_path=db_path)
            return await tool.execute(category="dream", hours=24)
        result = self._run(_insert_and_query())
        assert "ERRORS" in result
        assert "timeout" in result

    def test_heartbeat_empty(self, _create_tables, db_path):
        from nanobot.copilot.tools.ops_log import OpsLogTool
        tool = OpsLogTool(db_path=db_path)
        result = self._run(tool.execute(category="heartbeat", hours=24))
        assert "No heartbeat runs" in result

    def test_heartbeat_with_data(self, _create_tables, db_path):
        from nanobot.copilot.tools.ops_log import OpsLogTool
        async def _insert_and_query():
            async with aiosqlite.connect(db_path) as db:
                await db.execute(
                    "INSERT INTO heartbeat_log (tasks_checked, tasks_with_results, duration_ms) VALUES (1, 2, 100)"
                )
                await db.execute(
                    "INSERT INTO heartbeat_events (event_type, severity, message, source) VALUES ('health_error', 'high', 'Redis unreachable', 'heartbeat')"
                )
                await db.commit()
            tool = OpsLogTool(db_path=db_path)
            return await tool.execute(category="heartbeat", hours=24)
        result = self._run(_insert_and_query())
        assert "Runs: 1" in result
        assert "Redis unreachable" in result

    def test_alerts_empty(self, _create_tables, db_path):
        from nanobot.copilot.tools.ops_log import OpsLogTool
        tool = OpsLogTool(db_path=db_path)
        result = self._run(tool.execute(category="alerts", hours=24))
        assert "No alerts" in result

    def test_alerts_with_data(self, _create_tables, db_path):
        from nanobot.copilot.tools.ops_log import OpsLogTool
        async def _insert_and_query():
            async with aiosqlite.connect(db_path) as db:
                await db.execute(
                    "INSERT INTO alerts (subsystem, severity, error_key, message) VALUES ('memory', 'high', 'embed_fail', 'Embedding failed')"
                )
                await db.execute(
                    "INSERT INTO alerts (subsystem, severity, error_key, message) VALUES ('memory', 'high', 'embed_fail', 'Embedding failed')"
                )
                await db.commit()
            tool = OpsLogTool(db_path=db_path)
            return await tool.execute(category="alerts", hours=24)
        result = self._run(_insert_and_query())
        assert "1 unique" in result
        assert "1 high" in result
        assert "(x2)" in result

    def test_cost_empty(self, _create_tables, db_path):
        from nanobot.copilot.tools.ops_log import OpsLogTool
        tool = OpsLogTool(db_path=db_path)
        result = self._run(tool.execute(category="cost", hours=24))
        assert "$0.00" in result

    def test_cost_with_data(self, _create_tables, db_path):
        from nanobot.copilot.tools.ops_log import OpsLogTool
        async def _insert_and_query():
            async with aiosqlite.connect(db_path) as db:
                await db.execute(
                    "INSERT INTO cost_log (model, tokens_input, tokens_output, cost_usd) VALUES ('claude-haiku', 1000, 500, 0.05)"
                )
                await db.execute(
                    "INSERT INTO cost_log (model, tokens_input, tokens_output, cost_usd) VALUES ('claude-haiku', 2000, 1000, 0.10)"
                )
                await db.commit()
            tool = OpsLogTool(db_path=db_path)
            return await tool.execute(category="cost", hours=24)
        result = self._run(_insert_and_query())
        assert "$0.15" in result
        assert "2 calls" in result
        assert "claude-haiku" in result

    def test_unknown_category(self, _create_tables, db_path):
        from nanobot.copilot.tools.ops_log import OpsLogTool
        tool = OpsLogTool(db_path=db_path)
        result = self._run(tool.execute(category="bogus"))
        assert "Unknown category" in result

    def test_hours_clamped(self, _create_tables, db_path):
        from nanobot.copilot.tools.ops_log import OpsLogTool
        tool = OpsLogTool(db_path=db_path)
        # 999 hours should be clamped to 168
        result = self._run(tool.execute(category="dream", hours=999))
        assert "168h" in result

    def test_no_db(self):
        from nanobot.copilot.tools.ops_log import OpsLogTool
        tool = OpsLogTool(db_path="")
        result = self._run(tool.execute(category="dream"))
        assert "No database" in result

    def test_tool_schema(self, _create_tables, db_path):
        from nanobot.copilot.tools.ops_log import OpsLogTool
        tool = OpsLogTool(db_path=db_path)
        assert tool.name == "ops_log"
        assert "category" in tool.parameters["properties"]
        schema = tool.to_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "ops_log"


# --- Heartbeat summary tests ---

class TestHeartbeatSummary:

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_empty_db(self, _create_tables, db_path):
        from nanobot.copilot.context.events import get_heartbeat_summary
        result = self._run(get_heartbeat_summary(db_path))
        assert result == ""

    def test_healthy_heartbeat(self, _create_tables, db_path):
        from nanobot.copilot.context.events import get_heartbeat_summary
        async def _test():
            async with aiosqlite.connect(db_path) as db:
                await db.execute(
                    "INSERT INTO heartbeat_log (tasks_checked, tasks_with_results, duration_ms) VALUES (1, 0, 50)"
                )
                await db.commit()
            return await get_heartbeat_summary(db_path)
        result = self._run(_test())
        assert "Last heartbeat:" in result
        assert "all healthy" in result

    def test_unhealthy_heartbeat(self, _create_tables, db_path):
        from nanobot.copilot.context.events import get_heartbeat_summary
        async def _test():
            async with aiosqlite.connect(db_path) as db:
                await db.execute(
                    "INSERT INTO heartbeat_log (tasks_checked, tasks_with_results, duration_ms) VALUES (1, 1, 50)"
                )
                await db.execute(
                    "INSERT INTO heartbeat_events (event_type, severity, message, source) VALUES ('health_error', 'high', 'Qdrant unreachable: connection refused', 'heartbeat')"
                )
                await db.commit()
            return await get_heartbeat_summary(db_path)
        result = self._run(_test())
        assert "Last heartbeat:" in result
        assert "[high]" in result
        assert "Qdrant unreachable" in result

    def test_no_db_path(self):
        from nanobot.copilot.context.events import get_heartbeat_summary
        result = self._run(get_heartbeat_summary(""))
        assert result == ""


# --- Status ops_summary tests ---

class TestStatusOpsSummary:

    def test_format_ago(self):
        from nanobot.copilot.status.aggregator import _format_ago
        from datetime import datetime, timedelta
        # Recent
        ts = (datetime.now(tz=None) - timedelta(seconds=30)).isoformat()
        assert "30s ago" in _format_ago(ts)
        # Minutes
        ts = (datetime.now(tz=None) - timedelta(minutes=45)).isoformat()
        assert "45m ago" in _format_ago(ts)
        # Hours
        ts = (datetime.now(tz=None) - timedelta(hours=3, minutes=15)).isoformat()
        assert "3h" in _format_ago(ts)
        # Days
        ts = (datetime.now(tz=None) - timedelta(days=3)).isoformat()
        assert "3d ago" in _format_ago(ts)
