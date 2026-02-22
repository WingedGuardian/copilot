"""Agent-accessible task tool for creating and managing tasks."""

from __future__ import annotations

from typing import Any

from nanobot.agent.tools.base import Tool
from nanobot.copilot.tasks.manager import TaskManager


class TaskTool(Tool):
    """Tool for creating, listing, and managing persistent tasks."""

    def __init__(self, task_manager: TaskManager):
        self._manager = task_manager

    @property
    def name(self) -> str:
        return "task"

    @property
    def description(self) -> str:
        return (
            "Create, list, and manage persistent tasks. "
            "Actions: 'create' (new task), 'list' (show tasks), 'get' (task details), "
            "'complete' (mark done), 'fail' (mark failed), 'add_steps' (decompose task), "
            "'resume' (clear pending questions and resume task), "
            "'status_summary' (one-line summary of all active tasks)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "list", "get", "complete", "fail", "add_steps", "resume", "status_summary"],
                    "description": "Action to perform",
                },
                "title": {
                    "type": "string",
                    "description": "Task title (for 'create')",
                },
                "description": {
                    "type": "string",
                    "description": "Task description (for 'create')",
                },
                "task_id": {
                    "type": "string",
                    "description": "Task ID (for 'get', 'complete', 'fail', 'add_steps')",
                },
                "priority": {
                    "type": "integer",
                    "description": "Priority 1-5, lower is higher priority (default 3)",
                },
                "steps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Step descriptions (for 'add_steps')",
                },
                "status": {
                    "type": "string",
                    "description": "Filter by status (for 'list')",
                },
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "list")

        if action == "create":
            title = kwargs.get("title", "")
            if not title:
                return "Error: 'title' is required."
            task = await self._manager.create_task(
                title=title,
                description=kwargs.get("description", ""),
                priority=kwargs.get("priority", 3),
            )
            return f"Created task [{task.id}]: {task.title} (P{task.priority})"

        elif action == "list":
            status = kwargs.get("status")
            tasks = await self._manager.list_tasks(status=status)
            if not tasks:
                return "No tasks found."
            lines = [f"Tasks ({len(tasks)}):"]
            for t in tasks:
                progress = f"{t.steps_completed}/{t.step_count}" if t.step_count else "no steps"
                suffix = " [HAS QUESTIONS]" if t.pending_questions else ""
                lines.append(f"  [{t.id}] {t.title} ({t.status}, {progress}, P{t.priority}){suffix}")
            return "\n".join(lines)

        elif action == "get":
            task_id = kwargs.get("task_id", "")
            if not task_id:
                return "Error: 'task_id' is required."
            task = await self._manager.get_task(task_id)
            if not task:
                return f"Task {task_id} not found."
            lines = [
                f"Task: {task.title}",
                f"Status: {task.status} | Priority: {task.priority}",
                f"Description: {task.description or '(none)'}",
            ]
            if task.pending_questions:
                lines.append(f"Pending questions:\n{task.pending_questions}")
            if task.steps:
                lines.append(f"Steps ({task.steps_completed}/{task.step_count}):")
                for s in task.steps:
                    icon = {"completed": "done", "failed": "FAIL", "active": ">>", "pending": "  "}.get(s.status, "  ")
                    lines.append(f"  {icon} {s.step_index}. {s.description}")
            return "\n".join(lines)

        elif action == "complete":
            task_id = kwargs.get("task_id", "")
            await self._manager.complete_task(task_id)
            return f"Task {task_id} marked as completed."

        elif action == "fail":
            task_id = kwargs.get("task_id", "")
            await self._manager.update_status(task_id, "failed")
            return f"Task {task_id} marked as failed."

        elif action == "add_steps":
            task_id = kwargs.get("task_id", "")
            steps = kwargs.get("steps", [])
            if not task_id or not steps:
                return "Error: 'task_id' and 'steps' are required."
            created = await self._manager.add_steps(task_id, steps)
            return f"Added {len(created)} steps to task {task_id}."

        elif action == "resume":
            task_id = kwargs.get("task_id", "")
            if not task_id:
                return "Error: 'task_id' is required."
            task = await self._manager.get_task(task_id)
            if not task:
                return f"Task {task_id} not found."
            if not task.pending_questions:
                return f"Task {task_id} has no pending questions."
            await self._manager.clear_pending_questions(task_id)
            return f"Task {task_id} resumed. Questions cleared, status set to active."

        elif action == "status_summary":
            tasks = await self._manager.list_tasks()
            active = [t for t in tasks if t.status in ("pending", "active", "awaiting")]
            if not active:
                return "No active tasks."
            parts = []
            for t in active:
                if t.status == "awaiting":
                    parts.append(f"[{t.id}] {t.title} (awaiting answers)")
                elif t.step_count:
                    parts.append(f"[{t.id}] {t.title} ({t.steps_completed}/{t.step_count})")
                else:
                    parts.append(f"[{t.id}] {t.title} ({t.status})")
            return f"{len(active)} active: " + "; ".join(parts)

        return f"Unknown action: {action}"
