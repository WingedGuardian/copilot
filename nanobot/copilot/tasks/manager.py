"""Task manager: CRUD + step management for persistent task queue."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiosqlite
from loguru import logger


@dataclass
class TaskStep:
    """A single step within a task."""

    id: int = 0
    task_id: str = ""
    step_index: int = 0
    description: str = ""
    status: str = "pending"
    depends_on: str | None = None
    result: str | None = None
    tool_type: str = "general"
    recommended_model: str = ""


@dataclass
class Task:
    """A persistent task with optional decomposition into steps."""

    id: str = ""
    title: str = ""
    description: str = ""
    status: str = "pending"
    priority: int = 3
    session_key: str = ""
    steps: list[TaskStep] = field(default_factory=list)
    parent_id: str | None = None
    deadline: str | None = None
    step_count: int = 0
    steps_completed: int = 0
    pending_questions: str | None = None


class TaskManager:
    """CRUD + step management for tasks stored in SQLite."""

    def __init__(self, db_path: str | Path):
        self._db_path = str(db_path)

    async def create_task(
        self,
        title: str,
        description: str = "",
        session_key: str = "",
        priority: int = 3,
        parent_id: str | None = None,
        deadline: str | None = None,
    ) -> Task:
        """Create a new task. Returns the created Task."""
        task_id = str(uuid.uuid4())[:8]
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO tasks (id, title, description, status, priority,
                   session_key, parent_id, deadline)
                   VALUES (?, ?, ?, 'pending', ?, ?, ?, ?)""",
                (task_id, title, description, priority, session_key, parent_id, deadline),
            )
            await db.commit()
            await self._log_event(task_id, "created", title, db=db)

        logger.info(f"Created task {task_id}: {title}")
        return Task(
            id=task_id, title=title, description=description,
            status="pending", priority=priority, session_key=session_key,
            parent_id=parent_id, deadline=deadline,
        )

    async def add_steps(self, task_id: str, step_descriptions: list[str]) -> list[TaskStep]:
        """Decompose a task into steps."""
        steps = []
        async with aiosqlite.connect(self._db_path) as db:
            for i, desc in enumerate(step_descriptions):
                await db.execute(
                    """INSERT OR IGNORE INTO task_steps (task_id, step_index, description)
                       VALUES (?, ?, ?)""",
                    (task_id, i, desc),
                )
                steps.append(TaskStep(task_id=task_id, step_index=i, description=desc))

            await db.execute(
                "UPDATE tasks SET step_count = ? WHERE id = ?",
                (len(step_descriptions), task_id),
            )
            await db.commit()
        return steps

    async def get_task(self, task_id: str) -> Task | None:
        """Get a task with its steps."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = await cur.fetchone()
            if not row:
                return None

            task = self._row_to_task(dict(row))

            # Load steps
            cur = await db.execute(
                "SELECT * FROM task_steps WHERE task_id = ? ORDER BY step_index",
                (task_id,),
            )
            task.steps = [
                TaskStep(**{k: dict(r)[k] for k in dict(r) if k in TaskStep.__dataclass_fields__})
                for r in await cur.fetchall()
            ]
        return task

    async def get_next_pending(self) -> Task | None:
        """Get the highest-priority pending task that's ready to execute."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """SELECT * FROM tasks WHERE status IN ('pending', 'active')
                   ORDER BY priority ASC, rowid ASC LIMIT 1"""
            )
            row = await cur.fetchone()
            return self._row_to_task(dict(row)) if row else None

    async def get_next_step(self, task_id: str) -> TaskStep | None:
        """Get the next pending step for a task."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """SELECT * FROM task_steps WHERE task_id = ? AND status = 'pending'
                   ORDER BY step_index ASC LIMIT 1""",
                (task_id,),
            )
            row = await cur.fetchone()
            if not row:
                return None
            d = dict(row)
            return TaskStep(**{k: d[k] for k in d if k in TaskStep.__dataclass_fields__})

    async def complete_step(self, task_id: str, step_index: int, result: str) -> None:
        """Mark a step as completed."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """UPDATE task_steps SET status = 'completed', result = ?,
                   completed_at = CURRENT_TIMESTAMP WHERE task_id = ? AND step_index = ?""",
                (result, task_id, step_index),
            )
            await db.execute(
                "UPDATE tasks SET steps_completed = steps_completed + 1 WHERE id = ?",
                (task_id,),
            )
            await db.commit()

    async def fail_step(self, task_id: str, step_index: int, error: str) -> None:
        """Mark a step as failed."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """UPDATE task_steps SET status = 'failed', result = ?
                   WHERE task_id = ? AND step_index = ?""",
                (error, task_id, step_index),
            )
            await db.commit()

    async def complete_task(self, task_id: str) -> None:
        """Mark a task as completed."""
        await self.update_status(task_id, "completed")

    async def update_status(self, task_id: str, status: str) -> None:
        """Update task status."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE tasks SET status = ? WHERE id = ?",
                (status, task_id),
            )
            await db.commit()
            await self._log_event(task_id, "status_change", status, db=db)

    async def list_tasks(self, status: str | None = None, limit: int = 20) -> list[Task]:
        """List tasks, optionally filtered by status."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            if status:
                cur = await db.execute(
                    "SELECT * FROM tasks WHERE status = ? ORDER BY priority ASC, rowid DESC LIMIT ?",
                    (status, limit),
                )
            else:
                cur = await db.execute(
                    "SELECT * FROM tasks ORDER BY priority ASC, rowid DESC LIMIT ?",
                    (limit,),
                )
            rows = await cur.fetchall()
            return [self._row_to_task(dict(r)) for r in rows]

    async def get_stuck_tasks(self, threshold_minutes: int = 30) -> list[Task]:
        """Get tasks that have been in_progress/active for longer than threshold."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            # Look for tasks that have been active for too long
            # Uses task_log to find when task entered active/in_progress state
            cur = await db.execute(
                """SELECT t.* FROM tasks t
                   JOIN task_log tl ON t.id = tl.task_id
                   WHERE t.status IN ('active', 'in_progress')
                     AND tl.event = 'status_change'
                     AND tl.details IN ('active', 'in_progress')
                     AND tl.timestamp <= datetime('now', ? || ' minutes')
                   ORDER BY tl.timestamp ASC""",
                (f"-{threshold_minutes}",),
            )
            rows = await cur.fetchall()
            return [self._row_to_task(dict(r)) for r in rows]

    async def fail_stuck_tasks(self, threshold_minutes: int = 30) -> list[str]:
        """Mark stuck tasks as failed and return their IDs."""
        stuck = await self.get_stuck_tasks(threshold_minutes)
        failed_ids: list[str] = []
        for task in stuck:
            await self.update_status(task.id, "failed")
            logger.warning(f"Marked stuck task {task.id} '{task.title}' as failed")
            failed_ids.append(task.id)
        return failed_ids

    async def _log_event(
        self, task_id: str, event: str, details: str, db: aiosqlite.Connection | None = None
    ) -> None:
        """Write to task_log."""
        async def _do(conn):
            await conn.execute(
                "INSERT INTO task_log (task_id, event, details) VALUES (?, ?, ?)",
                (task_id, event, details),
            )
            await conn.commit()

        try:
            if db:
                await _do(db)
            else:
                async with aiosqlite.connect(self._db_path) as conn:
                    await _do(conn)
        except Exception as e:
            logger.warning(f"Task log failed: {e}")

    async def set_pending_questions(self, task_id: str, questions: str) -> None:
        """Set pending questions and move task to awaiting status."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE tasks SET pending_questions = ?, status = 'awaiting' WHERE id = ?",
                (questions, task_id),
            )
            await db.commit()
            await self._log_event(task_id, "questions_set", questions[:200], db=db)

    async def clear_pending_questions(self, task_id: str) -> None:
        """Clear pending questions and move task back to active."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE tasks SET pending_questions = NULL, status = 'active' WHERE id = ?",
                (task_id,),
            )
            await db.commit()
            await self._log_event(task_id, "questions_cleared", "", db=db)

    async def get_tasks_with_questions(self) -> list[Task]:
        """Get tasks that have pending questions (status = awaiting)."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM tasks WHERE pending_questions IS NOT NULL AND status = 'awaiting'"
            )
            rows = await cur.fetchall()
            return [self._row_to_task(dict(r)) for r in rows]

    async def add_steps_v2(self, task_id: str, steps: list[dict]) -> list[TaskStep]:
        """Add steps with tool_type metadata. Each dict needs 'description', optional 'tool_type'."""
        result = []
        async with aiosqlite.connect(self._db_path) as db:
            for i, step in enumerate(steps):
                desc = step["description"]
                tool_type = step.get("tool_type", "general")
                rec_model = step.get("recommended_model", "")
                await db.execute(
                    """INSERT OR IGNORE INTO task_steps (task_id, step_index, description, tool_type, recommended_model)
                       VALUES (?, ?, ?, ?, ?)""",
                    (task_id, i, desc, tool_type, rec_model),
                )
                result.append(TaskStep(task_id=task_id, step_index=i, description=desc, tool_type=tool_type, recommended_model=rec_model))
            await db.execute(
                "UPDATE tasks SET step_count = ? WHERE id = ?", (len(steps), task_id),
            )
            await db.commit()
        return result

    @staticmethod
    def _row_to_task(row: dict) -> Task:
        return Task(
            id=row.get("id", ""),
            title=row.get("title", row.get("id", "")),
            description=row.get("description", ""),
            status=row.get("status", "pending"),
            priority=row.get("priority", 3),
            session_key=row.get("session_key", ""),
            parent_id=row.get("parent_id"),
            deadline=row.get("deadline"),
            step_count=row.get("step_count", 0),
            steps_completed=row.get("steps_completed", 0),
            pending_questions=row.get("pending_questions"),
        )
