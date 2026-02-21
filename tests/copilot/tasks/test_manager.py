"""Tests for TaskManager with V2.1 schema extensions."""

import asyncio

import pytest

from nanobot.copilot.tasks.manager import TaskManager


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


def test_create_task_with_pending_questions(manager):
    async def _run():
        task = await manager.create_task(title="Research VPS providers")
        await manager.set_pending_questions(task.id, "What budget range?")
        fetched = await manager.get_task(task.id)
        assert fetched.pending_questions == "What budget range?"
    asyncio.get_event_loop().run_until_complete(_run())


def test_get_tasks_with_pending_questions(manager):
    async def _run():
        t1 = await manager.create_task(title="Task with question")
        await manager.create_task(title="Task without question")
        await manager.set_pending_questions(t1.id, "What region?")
        blocked = await manager.get_tasks_with_questions()
        assert len(blocked) == 1
        assert blocked[0].id == t1.id
    asyncio.get_event_loop().run_until_complete(_run())


def test_clear_pending_questions(manager):
    async def _run():
        task = await manager.create_task(title="Blocked task")
        await manager.set_pending_questions(task.id, "Clarify scope?")
        await manager.clear_pending_questions(task.id)
        blocked = await manager.get_tasks_with_questions()
        assert len(blocked) == 0
        # Status should be active
        updated = await manager.get_task(task.id)
        assert updated.status == "active"
    asyncio.get_event_loop().run_until_complete(_run())


def test_add_steps_with_tool_type(manager):
    async def _run():
        task = await manager.create_task(title="Multi-step task")
        steps = await manager.add_steps_v2(task.id, [
            {"description": "Search for providers", "tool_type": "research"},
            {"description": "Compare pricing", "tool_type": "research"},
            {"description": "Format table", "tool_type": "write"},
        ])
        assert len(steps) == 3
        assert steps[0].tool_type == "research"
        assert steps[2].tool_type == "write"
        # Verify step_count updated
        updated = await manager.get_task(task.id)
        assert updated.step_count == 3
    asyncio.get_event_loop().run_until_complete(_run())


def test_awaiting_tasks_not_returned_by_get_next_pending(manager):
    async def _run():
        task = await manager.create_task(title="Awaiting task")
        await manager.set_pending_questions(task.id, "Question?")
        next_task = await manager.get_next_pending()
        assert next_task is None or next_task.id != task.id
    asyncio.get_event_loop().run_until_complete(_run())
