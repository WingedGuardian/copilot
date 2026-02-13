"""Tests for heartbeat self-repair: stuck subagent and task detection."""

import time
import pytest

from nanobot.agent.subagent import SubagentInfo, SubagentManager


def test_subagent_info_idle():
    """SubagentInfo tracks idle time correctly."""
    info = SubagentInfo(task_id="test", label="test task")
    # Just created — should be near-zero idle
    assert info.idle_seconds < 1.0


def test_subagent_info_touch():
    """touch() resets idle time."""
    info = SubagentInfo(task_id="test", label="test task")
    # Simulate old activity
    info.last_activity = time.time() - 1000
    assert info.idle_seconds > 999
    info.touch()
    assert info.idle_seconds < 1.0


def test_get_stuck_subagents_empty():
    """No stuck subagents when none are running."""
    from unittest.mock import MagicMock
    mgr = SubagentManager.__new__(SubagentManager)
    mgr._subagent_info = {}
    mgr._running_tasks = {}
    assert mgr.get_stuck_subagents() == []


def test_get_stuck_subagents_detects_idle():
    """Detects subagents that have been idle too long."""
    mgr = SubagentManager.__new__(SubagentManager)
    mgr._running_tasks = {}

    # Create an info with old last_activity
    info = SubagentInfo(task_id="stuck-1", label="stuck task")
    info.last_activity = time.time() - 900  # 15 min ago
    mgr._subagent_info = {"stuck-1": info}

    stuck = mgr.get_stuck_subagents(threshold_seconds=600)
    assert len(stuck) == 1
    assert stuck[0].task_id == "stuck-1"


def test_get_stuck_subagents_ignores_active():
    """Does not flag recently active subagents."""
    mgr = SubagentManager.__new__(SubagentManager)
    mgr._running_tasks = {}

    info = SubagentInfo(task_id="active-1", label="active task")
    info.last_activity = time.time() - 60  # 1 min ago
    mgr._subagent_info = {"active-1": info}

    stuck = mgr.get_stuck_subagents(threshold_seconds=600)
    assert len(stuck) == 0


@pytest.mark.asyncio
async def test_cancel_stuck():
    """cancel_stuck cancels idle subagent tasks."""
    import asyncio

    mgr = SubagentManager.__new__(SubagentManager)

    # Create a mock asyncio task
    async def slow():
        await asyncio.sleep(3600)

    task = asyncio.create_task(slow())
    info = SubagentInfo(task_id="stuck-2", label="stuck task 2")
    info.last_activity = time.time() - 900

    mgr._running_tasks = {"stuck-2": task}
    mgr._subagent_info = {"stuck-2": info}

    cancelled = await mgr.cancel_stuck(threshold_seconds=600)
    assert "stuck-2" in cancelled
    # Allow event loop to process the cancellation
    await asyncio.sleep(0)
    assert task.cancelled() or task.done()
