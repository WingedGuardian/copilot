"""Task worker: background executor for persistent task queue."""

from __future__ import annotations

import asyncio
from typing import Callable, Awaitable

from loguru import logger

from nanobot.copilot.tasks.decomposer import parse_decomposition_response
from nanobot.copilot.tasks.manager import TaskManager
from nanobot.copilot.tasks.prompts import build_progress_message


class TaskWorker:
    """Background worker that picks up and executes pending tasks."""

    def __init__(
        self,
        task_manager: TaskManager,
        execute_fn: Callable[[str, str, str, str, str], Awaitable[str]],
        decompose_fn: Callable[[str], Awaitable[str]] | None = None,
        notify_fn: Callable[[str], Awaitable[None]] | None = None,
        interval_s: int = 60,
    ):
        self._manager = task_manager
        self._execute_fn = execute_fn
        self._decompose_fn = decompose_fn
        self._notify_fn = notify_fn
        self._interval = interval_s
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the background worker loop."""
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(f"Task worker started (interval={self._interval}s)")

    def stop(self) -> None:
        """Stop the worker."""
        self._running = False
        if self._task:
            self._task.cancel()

    async def _loop(self) -> None:
        """Main worker loop."""
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Task worker tick failed: {e}")
            await asyncio.sleep(self._interval)

    async def _notify(self, message: str) -> None:
        """Send a notification if notify_fn is configured."""
        if self._notify_fn:
            try:
                await self._notify_fn(message)
            except Exception as e:
                logger.warning(f"Task notification failed: {e}")

    async def _tick(self) -> None:
        """Process one pending task."""
        task = await self._manager.get_next_pending()
        if not task:
            return

        logger.info(f"Task worker picked up: {task.id} - {task.title}")
        await self._manager.update_status(task.id, "active")

        # If no steps, try decomposition
        if task.step_count == 0:
            await self._decompose_task(task)
            # Re-fetch task to get updated step_count
            task = await self._manager.get_task(task.id)
            if not task or task.status == "awaiting":
                return  # Waiting for user to answer questions

        # Execute next step (or whole task if no steps)
        if task.step_count > 0:
            await self._execute_next_step(task)
        else:
            await self._execute_whole_task(task)

    async def _decompose_task(self, task) -> None:
        """Decompose a task into steps using the frontier model."""
        if not self._decompose_fn:
            return

        try:
            raw_response = await self._decompose_fn(task.description or task.title)
            result = parse_decomposition_response(raw_response)

            if result.error:
                logger.warning(f"Decomposition parse error for {task.id}: {result.error}")
                return

            if result.clarifying_questions:
                questions_text = "\n".join(result.clarifying_questions)
                await self._manager.set_pending_questions(task.id, questions_text)
                await self._notify(build_progress_message(
                    task.id, task.title, [], questions=result.clarifying_questions,
                ))
                logger.info(f"Task {task.id} awaiting answers to {len(result.clarifying_questions)} questions")
                return

            if result.steps:
                await self._manager.add_steps_v2(task.id, result.steps)
                logger.info(f"Task {task.id} decomposed into {len(result.steps)} steps")

        except Exception as e:
            logger.warning(f"Task decomposition failed for {task.id}: {e}")

    async def _execute_next_step(self, task) -> None:
        """Execute the next pending step of a task."""
        step = await self._manager.get_next_step(task.id)
        if not step:
            # All steps done
            await self._manager.complete_task(task.id)
            await self._notify_completion(task)
            return

        try:
            result = await self._execute_fn(
                step.description,
                task.session_key or f"task:{task.id}",
                "cli",
                step.tool_type,
                step.recommended_model,
            )
            await self._manager.complete_step(task.id, step.step_index, result[:1000])
        except Exception as e:
            await self._manager.fail_step(task.id, step.step_index, str(e))
            logger.error(f"Task step failed: {task.id}/{step.step_index}: {e}")

        # Check if all steps are done
        next_step = await self._manager.get_next_step(task.id)
        if next_step is None:
            await self._manager.complete_task(task.id)
            await self._notify_completion(task)
        else:
            # Send progress notification
            completed = await self._get_completed_steps(task.id)
            await self._notify(build_progress_message(
                task.id, task.title, completed, current_step={"description": next_step.description},
            ))

    async def _execute_whole_task(self, task) -> None:
        """Execute a task that has no steps as a single unit."""
        try:
            result = await self._execute_fn(
                task.description or task.title,
                task.session_key or f"task:{task.id}",
                "cli",
                "general",
            )
            await self._manager.complete_task(task.id)
            await self._notify(f"Task #{task.id} completed: {task.title}")
            logger.info(f"Task completed: {task.id}")
        except Exception as e:
            await self._manager.update_status(task.id, "failed")
            await self._notify(f"Task #{task.id} failed: {task.title}\n{e}")
            logger.error(f"Task execution failed: {task.id}: {e}")

    async def _notify_completion(self, task) -> None:
        """Send a completion notification with aggregated results."""
        completed = await self._get_completed_steps(task.id)
        await self._notify(build_progress_message(task.id, task.title, completed))
        logger.info(f"Task completed: {task.id}")

    async def _get_completed_steps(self, task_id: str) -> list[dict]:
        """Get list of completed step descriptions for notifications."""
        full_task = await self._manager.get_task(task_id)
        if not full_task:
            return []
        return [
            {"description": s.description}
            for s in full_task.steps
            if s.status == "completed"
        ]
