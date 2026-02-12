"""Task worker: background executor for persistent task queue."""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Awaitable

from loguru import logger

from nanobot.copilot.tasks.manager import TaskManager


class TaskWorker:
    """Background worker that picks up and executes pending tasks."""

    def __init__(
        self,
        task_manager: TaskManager,
        execute_fn: Callable[[str, str, str], Awaitable[str]],
        decompose_fn: Callable[[str], Awaitable[list[str]]] | None = None,
        interval_s: int = 60,
    ):
        self._manager = task_manager
        self._execute_fn = execute_fn
        self._decompose_fn = decompose_fn
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

    async def _tick(self) -> None:
        """Process one pending task."""
        task = await self._manager.get_next_pending()
        if not task:
            return

        logger.info(f"Task worker picked up: {task.id} - {task.title}")
        await self._manager.update_status(task.id, "active")

        # If no steps, try decomposition
        if task.step_count == 0:
            if self._decompose_fn:
                try:
                    step_descs = await self._decompose_fn(task.description or task.title)
                    if step_descs:
                        await self._manager.add_steps(task.id, step_descs)
                        task.step_count = len(step_descs)
                except Exception as e:
                    logger.warning(f"Task decomposition failed: {e}")

        # Execute next step (or whole task if no steps)
        if task.step_count > 0:
            step = await self._manager.get_next_step(task.id)
            if step:
                try:
                    result = await self._execute_fn(
                        step.description,
                        task.session_key or f"task:{task.id}",
                        "cli",
                    )
                    await self._manager.complete_step(task.id, step.step_index, result[:1000])
                except Exception as e:
                    await self._manager.fail_step(task.id, step.step_index, str(e))
                    logger.error(f"Task step failed: {task.id}/{step.step_index}: {e}")

            # Check if all steps are done
            next_step = await self._manager.get_next_step(task.id)
            if next_step is None:
                await self._manager.complete_task(task.id)
                logger.info(f"Task completed: {task.id}")
        else:
            # No steps — execute the whole task directly
            try:
                result = await self._execute_fn(
                    task.description or task.title,
                    task.session_key or f"task:{task.id}",
                    "cli",
                )
                await self._manager.complete_task(task.id)
                logger.info(f"Task completed: {task.id}")
            except Exception as e:
                await self._manager.update_status(task.id, "failed")
                logger.error(f"Task execution failed: {task.id}: {e}")
