"""Task worker: background executor for persistent task queue."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

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
        db_path: str = "",
        memory_manager: Any = None,
        retrospective_fn: Callable[[str], Awaitable[str]] | None = None,
    ):
        self._manager = task_manager
        self._execute_fn = execute_fn
        self._decompose_fn = decompose_fn
        self._notify_fn = notify_fn
        self._interval = interval_s
        self._running = False
        self._task: asyncio.Task | None = None
        self._db_path = db_path
        self._memory = memory_manager
        self._retrospective_fn = retrospective_fn

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
            # Phase 3B: Inject past wisdom from retrospectives
            past_wisdom = await self._get_past_wisdom(task.description or task.title)
            raw_response = await self._decompose_fn(
                task.description or task.title,
                past_wisdom=past_wisdom,
            )
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
            await self._manager.update_status(task.id, "failed")
            logger.error(f"Task step failed: {task.id}/{step.step_index}: {e}")
            await self._maybe_retrospective(
                task, "failed",
                error_context=f"Step {step.step_index} ({step.description[:100]}): {e}",
            )
            return  # Don't continue to next step after failure

        # Check if all steps are done
        next_step = await self._manager.get_next_step(task.id)
        if next_step is None:
            await self._manager.complete_task(task.id)
            await self._notify_completion(task)
            await self._maybe_retrospective(task, "completed")
        else:
            # Send progress notification
            completed = await self._get_completed_steps(task.id)
            await self._notify(build_progress_message(
                task.id, task.title, completed, current_step={"description": next_step.description},
            ))

    async def _execute_whole_task(self, task) -> None:
        """Execute a task that has no steps as a single unit."""
        try:
            await self._execute_fn(
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
            await self._maybe_retrospective(task, "failed", error_context=str(e))

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

    # ------------------------------------------------------------------
    # Past wisdom (Phase 3B)
    # ------------------------------------------------------------------

    async def _get_past_wisdom(self, description: str) -> str | None:
        """Query Qdrant for similar past retrospectives to inform decomposition."""
        if not self._memory:
            return None
        try:
            episodes = await self._memory._episodic.recall(
                query=description,
                limit=3,
                role_filter="retrospective",
                min_score=0.35,
            )
            if not episodes:
                return None
            lines = []
            for ep in episodes:
                lines.append(f"- {ep.text[:500]}")
            return "\n".join(lines)
        except Exception as e:
            logger.debug(f"Past wisdom query failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Retrospective (Phase 3A)
    # ------------------------------------------------------------------

    async def _maybe_retrospective(
        self, task, outcome: str, error_context: str = ""
    ) -> None:
        """Run retrospective if task is non-trivial (FM5 threshold)."""
        # FM5: Skip trivial successful tasks (single-step quick completions)
        if outcome == "completed" and task.step_count <= 1:
            return
        # Always retrospect on failures
        try:
            await self._run_retrospective(task, outcome, error_context)
        except Exception as e:
            logger.warning(f"Retrospective failed for {task.id}: {e}")

    async def _run_retrospective(
        self, task, outcome: str, error_context: str = ""
    ) -> None:
        """Run LLM retrospective on a completed/failed task, store results."""
        if not self._retrospective_fn or not self._db_path:
            return

        # Gather step summaries
        full_task = await self._manager.get_task(task.id)
        step_summaries = ""
        if full_task and full_task.steps:
            lines = []
            for s in full_task.steps:
                status = s.status
                result = (s.result or "")[:200]
                lines.append(f"  Step {s.step_index}: {s.description} [{status}] {result}")
            step_summaries = "\n".join(lines)

        # Build retrospective prompt
        if outcome == "failed":
            prompt = (
                f'Task failed: "{task.title}"\n'
                f"Description: {task.description or 'N/A'}\n"
                f"Error: {error_context}\n"
                f"Steps:\n{step_summaries or '(no steps)'}\n\n"
                "DIAGNOSE:\n"
                "1. ROOT CAUSE: What specifically failed and why?\n"
                "2. WHAT I TRIED: What approaches were attempted?\n"
                "3. PROPOSED FIX: What would fix this?\n"
                "4. CAPABILITY GAP: What tool, skill, or access was missing?\n\n"
                'Output JSON: {"diagnosis": "...", "approach_summary": "...", '
                '"learnings": "...", "capability_gaps": []}'
            )
        else:
            prompt = (
                f'Task completed: "{task.title}"\n'
                f"Description: {task.description or 'N/A'}\n"
                f"Steps:\n{step_summaries or '(no steps)'}\n\n"
                "RETROSPECTIVE:\n"
                "What went well? What could be improved? Any capability gaps?\n\n"
                'Output JSON: {"approach_summary": "...", "learnings": "...", '
                '"capability_gaps": []}'
            )

        response = await self._retrospective_fn(prompt)

        # Parse structured response
        from nanobot.copilot.dream.cycle import DreamCycle
        parsed = DreamCycle._parse_llm_json(response)
        if not isinstance(parsed, dict):
            parsed = {"approach_summary": response[:500]}

        # Store in task_retrospectives
        import aiosqlite
        try:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    """INSERT INTO task_retrospectives
                       (task_id, outcome, approach_summary, diagnosis, learnings, capability_gaps)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        task.id,
                        outcome,
                        parsed.get("approach_summary", ""),
                        parsed.get("diagnosis", ""),
                        parsed.get("learnings", ""),
                        ", ".join(parsed.get("capability_gaps", [])),
                    ),
                )
                await db.commit()
        except Exception as e:
            logger.warning(f"Retrospective DB write failed: {e}")
            return

        # On failure, write dream_observations for visibility
        if outcome == "failed":
            try:
                async with aiosqlite.connect(self._db_path) as db:
                    diagnosis = parsed.get("diagnosis", error_context[:300])
                    await db.execute(
                        """INSERT INTO dream_observations
                           (source, observation_type, content, priority, related_task_id)
                           VALUES (?, ?, ?, ?, ?)""",
                        (
                            "task_retrospective",
                            "failure_diagnosis",
                            f"Task '{task.title}' failed: {diagnosis}",
                            "high",
                            task.id,
                        ),
                    )
                    await db.commit()
            except Exception as e:
                logger.warning(f"Retrospective observation write failed: {e}")

        # Embed in Qdrant for future task wisdom (FM6: graceful on failure)
        if self._memory:
            retro_text = (
                f"Task: {task.title}\nOutcome: {outcome}\n"
                f"Approach: {parsed.get('approach_summary', '')}\n"
                f"Learnings: {parsed.get('learnings', '')}\n"
                f"Gaps: {', '.join(parsed.get('capability_gaps', []))}"
            )
            try:
                await self._memory._episodic.store(
                    text=retro_text,
                    session_key=f"retro:{task.id}",
                    role="retrospective",
                    importance=0.9 if outcome == "failed" else 0.7,
                )
            except Exception as e:
                logger.debug(f"Retrospective embed failed (will retry in dream): {e}")
