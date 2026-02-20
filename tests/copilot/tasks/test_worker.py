"""Tests for TaskWorker with decomposition, notifications, and typed execution."""

import asyncio
import json

import pytest

from nanobot.copilot.tasks.manager import TaskManager
from nanobot.copilot.tasks.worker import TaskWorker


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def manager(db_path):
    async def _setup():
        from nanobot.copilot.cost.db import ensure_tables, migrate_phase7
        await ensure_tables(db_path)
        await migrate_phase7(db_path)
        return TaskManager(db_path)
    return asyncio.get_event_loop().run_until_complete(_setup())


def _make_execute_fn(results=None):
    """Create a mock execute_fn that records calls."""
    calls = []

    async def execute(desc, session_key, channel, tool_type, recommended_model=""):
        calls.append({"desc": desc, "session_key": session_key, "channel": channel, "tool_type": tool_type})
        if results and len(calls) <= len(results):
            return results[len(calls) - 1]
        return "done"

    return execute, calls


def _make_decompose_fn(response_json):
    """Create a mock decompose_fn that returns a JSON string."""
    calls = []

    async def decompose(description, **kwargs):
        calls.append(description)
        return json.dumps(response_json)

    return decompose, calls


def _make_notify_fn():
    """Create a mock notify_fn that records messages."""
    messages = []

    async def notify(message):
        messages.append(message)

    return notify, messages


def test_tick_no_tasks(manager):
    async def _run():
        execute, calls = _make_execute_fn()
        worker = TaskWorker(manager, execute)
        await worker._tick()
        assert len(calls) == 0
    asyncio.get_event_loop().run_until_complete(_run())


def test_tick_executes_whole_task_without_decomposition(manager):
    async def _run():
        execute, calls = _make_execute_fn()
        worker = TaskWorker(manager, execute)
        task = await manager.create_task("Do something", "Full description")
        await worker._tick()
        assert len(calls) == 1
        assert calls[0]["desc"] == "Full description"
        assert calls[0]["tool_type"] == "general"
        updated = await manager.get_task(task.id)
        assert updated.status == "completed"
    asyncio.get_event_loop().run_until_complete(_run())


def test_tick_decomposes_then_executes_first_step(manager):
    async def _run():
        decompose, d_calls = _make_decompose_fn({
            "steps": [
                {"description": "Search the web", "tool_type": "research"},
                {"description": "Write summary", "tool_type": "write"},
            ],
            "clarifying_questions": [],
        })
        execute, e_calls = _make_execute_fn()
        worker = TaskWorker(manager, execute, decompose_fn=decompose)
        task = await manager.create_task("Research VPS")
        await worker._tick()
        assert len(d_calls) == 1
        assert len(e_calls) == 1
        assert e_calls[0]["desc"] == "Search the web"
        assert e_calls[0]["tool_type"] == "research"
        updated = await manager.get_task(task.id)
        assert updated.status == "active"
        assert updated.step_count == 2
    asyncio.get_event_loop().run_until_complete(_run())


def test_tick_completes_task_after_all_steps(manager):
    async def _run():
        execute, _ = _make_execute_fn()
        worker = TaskWorker(manager, execute)
        task = await manager.create_task("Single-step task")
        await manager.add_steps_v2(task.id, [
            {"description": "Step 1", "tool_type": "research"},
        ])
        await worker._tick()
        updated = await manager.get_task(task.id)
        assert updated.status == "completed"
    asyncio.get_event_loop().run_until_complete(_run())


def test_tick_sends_progress_notification(manager):
    async def _run():
        execute, _ = _make_execute_fn()
        notify, messages = _make_notify_fn()
        worker = TaskWorker(manager, execute, notify_fn=notify)
        task = await manager.create_task("Two step task")
        await manager.add_steps_v2(task.id, [
            {"description": "Step A", "tool_type": "research"},
            {"description": "Step B", "tool_type": "write"},
        ])
        await worker._tick()
        assert len(messages) == 1
        assert "Step B" in messages[0]
    asyncio.get_event_loop().run_until_complete(_run())


def test_tick_sends_completion_notification(manager):
    async def _run():
        execute, _ = _make_execute_fn()
        notify, messages = _make_notify_fn()
        worker = TaskWorker(manager, execute, notify_fn=notify)
        task = await manager.create_task("Single step")
        await manager.add_steps_v2(task.id, [
            {"description": "Only step", "tool_type": "general"},
        ])
        await worker._tick()
        assert len(messages) == 1
        assert "Only step" in messages[0]
    asyncio.get_event_loop().run_until_complete(_run())


def test_decomposition_with_questions_sets_awaiting(manager):
    async def _run():
        decompose, _ = _make_decompose_fn({
            "steps": [],
            "clarifying_questions": ["What budget?", "Which region?"],
        })
        execute, e_calls = _make_execute_fn()
        notify, messages = _make_notify_fn()
        worker = TaskWorker(manager, execute, decompose_fn=decompose, notify_fn=notify)
        task = await manager.create_task("Research VPS")
        await worker._tick()
        assert len(e_calls) == 0
        updated = await manager.get_task(task.id)
        assert updated.status == "awaiting"
        assert "What budget?" in updated.pending_questions
        assert len(messages) == 1
        assert "What budget?" in messages[0]
    asyncio.get_event_loop().run_until_complete(_run())


def test_awaiting_task_not_picked_up(manager):
    async def _run():
        execute, calls = _make_execute_fn()
        worker = TaskWorker(manager, execute)
        task = await manager.create_task("Blocked task")
        await manager.set_pending_questions(task.id, "Need more info")
        await worker._tick()
        assert len(calls) == 0
    asyncio.get_event_loop().run_until_complete(_run())


def test_failed_step_does_not_crash_worker(manager):
    async def _run():
        async def failing_execute(desc, sk, ch, tt, recommended_model=""):
            raise RuntimeError("boom")

        worker = TaskWorker(manager, failing_execute)
        task = await manager.create_task("Fragile task")
        await manager.add_steps_v2(task.id, [
            {"description": "Will fail", "tool_type": "general"},
            {"description": "Never reached", "tool_type": "general"},
        ])
        await worker._tick()
        updated = await manager.get_task(task.id)
        failed_steps = [s for s in updated.steps if s.status == "failed"]
        assert len(failed_steps) == 1
        assert updated.status == "failed"  # Step failure fails the entire task
    asyncio.get_event_loop().run_until_complete(_run())


def test_whole_task_failure_sets_failed_status(manager):
    async def _run():
        async def failing_execute(desc, sk, ch, tt):
            raise RuntimeError("total failure")

        notify, messages = _make_notify_fn()
        worker = TaskWorker(manager, failing_execute, notify_fn=notify)
        task = await manager.create_task("Doomed task", "Will fail")
        await worker._tick()
        updated = await manager.get_task(task.id)
        assert updated.status == "failed"
        assert len(messages) == 1
        assert "failed" in messages[0].lower()
    asyncio.get_event_loop().run_until_complete(_run())


def test_decomposition_parse_error_falls_through(manager):
    async def _run():
        async def bad_decompose(desc, **kwargs):
            return "not json at all"

        execute, calls = _make_execute_fn()
        worker = TaskWorker(manager, execute, decompose_fn=bad_decompose)
        await manager.create_task("Poorly decomposed")
        await worker._tick()
        assert len(calls) == 1
        assert calls[0]["desc"] == "Poorly decomposed"
    asyncio.get_event_loop().run_until_complete(_run())


def test_execute_fn_receives_tool_type(manager):
    async def _run():
        execute, calls = _make_execute_fn()
        worker = TaskWorker(manager, execute)
        task = await manager.create_task("Typed task")
        await manager.add_steps_v2(task.id, [
            {"description": "Search something", "tool_type": "research"},
        ])
        await worker._tick()
        assert calls[0]["tool_type"] == "research"
    asyncio.get_event_loop().run_until_complete(_run())


def test_notify_fn_failure_does_not_crash_worker(manager):
    async def _run():
        execute, _ = _make_execute_fn()

        async def broken_notify(msg):
            raise ConnectionError("notification service down")

        worker = TaskWorker(manager, execute, notify_fn=broken_notify)
        task = await manager.create_task("Notify test")
        await worker._tick()
        updated = await manager.get_task(task.id)
        assert updated.status == "completed"
    asyncio.get_event_loop().run_until_complete(_run())
