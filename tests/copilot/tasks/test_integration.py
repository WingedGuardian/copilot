"""Integration test: full task lifecycle with mocked LLM calls."""

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


def test_full_lifecycle_create_decompose_execute_complete(manager):
    """End-to-end: create → decompose → execute steps → complete → notify."""
    async def _run():
        notifications = []

        async def mock_decompose(description, **kwargs):
            return json.dumps({
                "steps": [
                    {"description": "Search for VPS providers", "tool_type": "research"},
                    {"description": "Compare pricing tiers", "tool_type": "research"},
                    {"description": "Format comparison table", "tool_type": "write"},
                ],
                "clarifying_questions": [],
            })

        step_results = []

        async def mock_execute(desc, sk, ch, tool_type, recommended_model=""):
            result = f"Result for: {desc}"
            step_results.append({"desc": desc, "tool_type": tool_type})
            return result

        async def mock_notify(message):
            notifications.append(message)

        worker = TaskWorker(
            task_manager=manager,
            execute_fn=mock_execute,
            decompose_fn=mock_decompose,
            notify_fn=mock_notify,
            interval_s=60,
        )

        # 1. Create task
        task = await manager.create_task(
            title="Research VPS providers",
            description="Find top 3 VPS providers under $20/month and compare",
        )
        assert task.status == "pending"

        # 2. First tick: decomposes + executes first step
        await worker._tick()
        updated = await manager.get_task(task.id)
        assert updated.step_count == 3
        assert updated.steps_completed == 1
        assert len(step_results) == 1
        assert step_results[0]["tool_type"] == "research"

        # 3. Second tick: executes second step
        await worker._tick()
        updated = await manager.get_task(task.id)
        assert updated.steps_completed == 2
        assert len(step_results) == 2

        # 4. Third tick: executes third step → completes
        await worker._tick()
        updated = await manager.get_task(task.id)
        assert updated.status == "completed"
        assert updated.steps_completed == 3
        assert len(step_results) == 3
        assert step_results[2]["tool_type"] == "write"

        # 5. Verify notifications were sent
        assert len(notifications) >= 2  # progress + completion

        # 6. No more work
        await worker._tick()
        assert len(step_results) == 3  # no new executions

    asyncio.get_event_loop().run_until_complete(_run())


def test_clarifying_questions_flow(manager):
    """Create → decompose returns questions → awaiting → resume → complete."""
    async def _run():
        notifications = []
        decompose_calls = []

        async def mock_decompose(description, **kwargs):
            decompose_calls.append(description)
            if len(decompose_calls) == 1:
                # First call: ask questions
                return json.dumps({
                    "steps": [],
                    "clarifying_questions": ["What budget range?", "Which region?"],
                })
            # Second call: after resume, return steps
            return json.dumps({
                "steps": [{"description": "Execute task", "tool_type": "general"}],
                "clarifying_questions": [],
            })

        async def mock_execute(desc, sk, ch, tool_type, recommended_model=""):
            return "done"

        async def mock_notify(message):
            notifications.append(message)

        worker = TaskWorker(
            task_manager=manager,
            execute_fn=mock_execute,
            decompose_fn=mock_decompose,
            notify_fn=mock_notify,
        )

        # 1. Create task
        task = await manager.create_task("Research VPS", "Find providers")

        # 2. First tick: decompose returns questions → awaiting
        await worker._tick()
        updated = await manager.get_task(task.id)
        assert updated.status == "awaiting"
        assert "What budget range?" in updated.pending_questions

        # 3. Worker should NOT pick up awaiting tasks
        await worker._tick()
        assert len(decompose_calls) == 1  # no second decompose call

        # 4. Simulate user answering questions (via TaskTool resume)
        await manager.clear_pending_questions(task.id)
        updated = await manager.get_task(task.id)
        assert updated.status == "active"
        assert updated.pending_questions is None

        # 5. Next tick: re-decomposes (now with context), executes
        await worker._tick()
        assert len(decompose_calls) == 2
        updated = await manager.get_task(task.id)
        assert updated.step_count == 1

        # 6. Final tick: completes
        await worker._tick()
        updated = await manager.get_task(task.id)
        assert updated.status == "completed"

    asyncio.get_event_loop().run_until_complete(_run())


def test_task_tool_resume_action(manager):
    """Test the TaskTool 'resume' action integration."""
    async def _run():
        from nanobot.copilot.tasks.tool import TaskTool
        tool = TaskTool(manager)

        # Create task and set questions
        task = await manager.create_task("Test task")
        await manager.set_pending_questions(task.id, "What region?")

        # Resume via tool
        result = await tool.execute(action="resume", task_id=task.id)
        assert "resumed" in result.lower()

        # Verify state
        updated = await manager.get_task(task.id)
        assert updated.status == "active"
        assert updated.pending_questions is None

        # Resume again should say no questions
        result = await tool.execute(action="resume", task_id=task.id)
        assert "no pending questions" in result.lower()

    asyncio.get_event_loop().run_until_complete(_run())


def test_task_tool_status_summary(manager):
    """Test the TaskTool 'status_summary' action."""
    async def _run():
        from nanobot.copilot.tasks.tool import TaskTool
        tool = TaskTool(manager)

        # No tasks
        result = await tool.execute(action="status_summary")
        assert "no active" in result.lower()

        # Create some tasks
        await manager.create_task("Task A")
        t2 = await manager.create_task("Task B")
        await manager.set_pending_questions(t2.id, "Question?")

        result = await tool.execute(action="status_summary")
        assert "2 active" in result
        assert "Task A" in result
        assert "awaiting" in result

    asyncio.get_event_loop().run_until_complete(_run())
