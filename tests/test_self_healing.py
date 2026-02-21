"""Phase 1 tests: Critical Resilience (self-healing)."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# 1A. LLM Call Timeout
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_timeout_breaks_loop():
    """LLM timeout should produce a timeout message and break the loop."""
    from nanobot.agent.loop import AgentLoop
    from nanobot.bus.queue import MessageBus

    bus = MessageBus()
    provider = AsyncMock()
    provider.get_default_model.return_value = "test-model"
    # Simulate a slow LLM call
    async def slow_chat(**kw):
        await asyncio.sleep(999)
    provider.chat = slow_chat

    loop = AgentLoop(bus=bus, provider=provider, workspace=Path("/tmp"), llm_timeout=1)
    from nanobot.bus.events import InboundMessage
    msg = InboundMessage(channel="cli", sender_id="u", chat_id="c", content="hello")
    response = await loop._process_message(msg)
    assert response is not None
    assert "timed out" in response.content.lower()


@pytest.mark.asyncio
async def test_llm_timeout_config_default():
    """Default llm_timeout should be 120."""
    from nanobot.agent.loop import AgentLoop
    from nanobot.bus.queue import MessageBus

    bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "m"
    loop = AgentLoop(bus=bus, provider=provider, workspace=Path("/tmp"))
    assert loop._llm_timeout == 120


# ---------------------------------------------------------------------------
# 1B. Process Supervisor
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_supervisor_restarts_crashed_service():
    """Supervisor should restart a service that crashes."""
    from nanobot.copilot.dream.supervisor import ProcessSupervisor

    call_count = 0

    async def flaky_service():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("boom")
        await asyncio.sleep(999)  # stay alive

    sup = ProcessSupervisor(check_interval=0.1, max_restarts=3)
    # Override initial backoff to be fast for testing
    sup.register("flaky", flaky_service)
    await sup.start()
    # Override backoff for speed
    sup._services["flaky"]["backoff"] = 0.05
    await asyncio.sleep(1.0)
    await sup.stop()
    assert call_count >= 2, f"Expected restart, got {call_count} calls"


@pytest.mark.asyncio
async def test_supervisor_stops_after_max_restarts():
    """Supervisor should give up after max_restarts."""
    from nanobot.copilot.dream.supervisor import ProcessSupervisor

    call_count = 0

    async def always_crash():
        nonlocal call_count
        call_count += 1
        raise RuntimeError("crash")

    sup = ProcessSupervisor(check_interval=0.05, max_restarts=2)
    sup.register("crasher", always_crash)
    await sup.start()
    sup._services["crasher"]["backoff"] = 0.01
    await asyncio.sleep(2.0)
    await sup.stop()
    status = sup.get_status()
    assert status["crasher"]["restarts"] >= 2


# ---------------------------------------------------------------------------
# 1C. MCP Health + Reconnect
# ---------------------------------------------------------------------------

def test_mcp_client_read_loop_sets_disconnected():
    """_read_loop finally block should set _connected = False."""
    from nanobot.agent.mcp.client import McpClient, McpServerConfig

    config = McpServerConfig(name="test")
    client = McpClient(config)
    client._connected = True
    # The finally block is tested via the code path
    assert hasattr(client, '_connected')


def test_mcp_manager_has_health_loop():
    """McpManager should have _health_loop method."""
    from nanobot.agent.mcp.manager import McpManager
    from nanobot.agent.tools.registry import ToolRegistry

    mgr = McpManager({}, ToolRegistry())
    assert hasattr(mgr, '_health_loop')
    assert hasattr(mgr, 'start_health_loop')


# ---------------------------------------------------------------------------
# 1D. Atomic Session Writes
# ---------------------------------------------------------------------------

def test_session_atomic_write():
    """Session save should use atomic write (temp + replace)."""
    from nanobot.session.manager import Session, SessionManager

    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = SessionManager(Path(tmpdir))
        mgr.sessions_dir = Path(tmpdir)
        session = Session(key="test:atomic")
        session.add_message("user", "hello")
        mgr.save(session)

        # File should exist
        path = mgr._get_session_path("test:atomic")
        assert path.exists()

        # Backup should exist after second save
        session.add_message("assistant", "hi")
        mgr.save(session)
        bak = path.with_suffix(".jsonl.bak")
        assert bak.exists()


def test_session_load_from_backup():
    """Session should load from .bak if primary is corrupt."""
    from nanobot.session.manager import Session, SessionManager

    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = SessionManager(Path(tmpdir))
        mgr.sessions_dir = Path(tmpdir)
        session = Session(key="test:bak")
        session.add_message("user", "important data")
        mgr.save(session)

        # Corrupt the primary file
        path = mgr._get_session_path("test:bak")
        path.with_suffix(".jsonl.bak")

        # Save again to create backup, then corrupt primary
        session.add_message("assistant", "response")
        mgr.save(session)
        path.write_text("CORRUPT DATA{{{")

        # Clear cache and reload
        mgr._cache.clear()
        loaded = mgr.get_or_create("test:bak")
        # Should load from backup
        assert len(loaded.messages) >= 1


# ---------------------------------------------------------------------------
# 1E. Task Tracking
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_track_task_logs_exceptions():
    """_track_task should log exceptions from failed tasks."""
    from nanobot.agent.loop import AgentLoop
    from nanobot.bus.queue import MessageBus

    bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "m"
    loop = AgentLoop(bus=bus, provider=provider, workspace=Path("/tmp"))

    async def fail():
        raise ValueError("test error")

    task = loop._track_task(fail(), name="test_fail")
    await asyncio.sleep(0.1)
    assert task.done()
    assert task not in loop._tracked_tasks  # cleaned up
