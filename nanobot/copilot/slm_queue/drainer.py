"""Background worker that drains the SLM queue when local SLM is available."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from nanobot.copilot.extraction.background import BackgroundExtractor
    from nanobot.copilot.memory.manager import MemoryManager
    from nanobot.copilot.slm_queue.manager import SlmWorkQueue, WorkItem


class SlmQueueDrainer:
    """Processes deferred SLM work when the local model comes back online."""

    def __init__(
        self,
        queue: SlmWorkQueue,
        extractor: BackgroundExtractor,
        memory_manager: MemoryManager,
        lm_studio_url: str = "http://192.168.50.100:1234",
        rate_per_minute: int = 30,
        batch_size: int = 5,
        probe_interval: int = 60,
    ):
        self._queue = queue
        self._extractor = extractor
        self._memory = memory_manager
        self._lm_studio_url = lm_studio_url
        self._rate_per_min = rate_per_minute
        self._batch_size = batch_size
        self._probe_interval = probe_interval
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("SlmQueueDrainer started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    # ── Main loop ────────────────────────────────────────────────────

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._queue.reset_stuck()
                await self._queue.prune_completed()

                if not await self._slm_is_online():
                    await asyncio.sleep(self._probe_interval)
                    continue

                size = await self._queue.size()
                if size == 0:
                    await asyncio.sleep(self._probe_interval)
                    continue

                logger.info(f"SLM online — draining queue ({size} pending)")
                processed = await self._drain_batch()
                if processed > 0:
                    await self._queue.update_drain_ts()
                    # Rate limit: spread work over time
                    await asyncio.sleep((60.0 / self._rate_per_min) * processed)
                else:
                    await asyncio.sleep(self._probe_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"SlmQueueDrainer error: {e}")
                await asyncio.sleep(30)

    # ── Health probe ─────────────────────────────────────────────────

    async def _slm_is_online(self) -> bool:
        """Lightweight HTTP probe to LM Studio /v1/models."""
        import httpx
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self._lm_studio_url}/v1/models")
                return r.status_code == 200
        except Exception:
            return False

    # ── Batch processing ─────────────────────────────────────────────

    async def _drain_batch(self) -> int:
        items = await self._queue.dequeue_batch(self._batch_size)
        if not items:
            return 0

        processed = 0
        for item in items:
            try:
                if item.work_type == "extraction":
                    await self._process_extraction(item)
                elif item.work_type == "embedding":
                    await self._process_embedding(item)
                await self._queue.mark_completed(item.id)
                processed += 1
            except Exception as e:
                logger.warning(f"Queue item #{item.id} ({item.work_type}) failed: {e}")
                await self._queue.mark_failed(item.id, str(e))
        return processed

    async def _process_extraction(self, item: WorkItem) -> None:
        """Run local-only extraction, store directly to memory (skip on_result chain)."""
        payload = item.payload
        result = await self._extractor.extract_local_only(
            payload["user_message"], payload["assistant_response"],
        )
        # Store SLM-quality extraction to Qdrant + FTS5 + SQLite items
        # (session metadata + satisfaction detector already ran with the
        # immediate heuristic/Haiku result — no need to re-run)
        data = result.model_dump()
        await self._memory.remember_extractions(
            data, item.session_key, conversation_ts=item.conversation_ts,
        )
        logger.debug(
            f"Drained extraction #{item.id}: "
            f"{len(result.facts)}F {len(result.decisions)}D"
        )

    async def _process_embedding(self, item: WorkItem) -> None:
        """Re-embed text with local model, store to Qdrant."""
        payload = item.payload
        await self._memory._episodic.store(
            text=payload["text"],
            session_key=item.session_key,
            role=payload.get("role", "exchange"),
            metadata=payload.get("metadata"),
            importance=payload.get("importance", 0.5),
            conversation_ts=item.conversation_ts,
        )
        logger.debug(f"Drained embedding #{item.id}")
