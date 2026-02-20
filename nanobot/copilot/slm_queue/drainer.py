"""Background worker that drains the SLM queue.

Embedding items: only enqueued on double failure (local AND cloud both down).
The drainer retries via embed() which tries local→cloud→zero again.
Deterministic point IDs ensure upserts overwrite zero-vectors in place.

Extraction items: tries local SLM first. After CLOUD_STALENESS_HOURS, falls
back to cloud LLM extraction.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from nanobot.copilot.extraction.background import BackgroundExtractor
    from nanobot.copilot.memory.manager import MemoryManager
    from nanobot.copilot.slm_queue.manager import SlmWorkQueue, WorkItem

CLOUD_STALENESS_HOURS = 4


class SlmQueueDrainer:
    """Processes deferred SLM work: local when online, cloud after staleness."""

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

                size = await self._queue.size()
                if size == 0:
                    await asyncio.sleep(self._probe_interval)
                    continue

                local_online = await self._slm_is_online()

                # Embedding items: drain immediately — embed() handles
                # local→cloud fallback internally, no staleness wait needed.
                embedding_pending = (await self._queue.breakdown()).get("embedding", 0)
                if embedding_pending > 0:
                    logger.info(f"Draining {embedding_pending} embedding items")
                    processed = await self._drain_batch(
                        use_cloud=not local_online, work_type="embedding",
                    )
                # Extraction items: need local SLM or cloud LLM with staleness gate.
                elif local_online:
                    logger.info(f"SLM online — draining queue ({size} pending)")
                    processed = await self._drain_batch(use_cloud=False)
                elif await self._oldest_age_hours() >= CLOUD_STALENESS_HOURS:
                    logger.info(
                        f"SLM offline >{CLOUD_STALENESS_HOURS}h — "
                        f"cloud draining queue ({size} pending)"
                    )
                    processed = await self._drain_batch(use_cloud=True)
                else:
                    await asyncio.sleep(self._probe_interval)
                    continue

                if processed > 0:
                    await self._queue.update_drain_ts()
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

    async def _oldest_age_hours(self) -> float:
        """How old is the oldest pending item in the queue?"""
        row = await self._queue._pool.fetchone(
            "SELECT MIN(queued_at) FROM slm_work_queue "
            "WHERE status IN ('pending', 'failed') AND attempts < max_attempts"
        )
        if not row or row[0] is None:
            return 0.0
        return (time.time() - row[0]) / 3600.0

    # ── Batch processing ─────────────────────────────────────────────

    async def _drain_batch(
        self, use_cloud: bool = False, work_type: str | None = None,
    ) -> int:
        items = await self._queue.dequeue_batch(self._batch_size, work_type=work_type)
        if not items:
            return 0

        processed = 0
        for item in items:
            try:
                if item.work_type == "extraction":
                    await self._process_extraction(item, use_cloud)
                elif item.work_type == "embedding":
                    await self._process_embedding(item, use_cloud)
                await self._queue.mark_completed(item.id)
                processed += 1
            except Exception as e:
                logger.warning(f"Queue item #{item.id} ({item.work_type}) failed: {e}")
                await self._queue.mark_failed(item.id, str(e))
        return processed

    async def _process_extraction(self, item: WorkItem, use_cloud: bool) -> None:
        """Run extraction via local or cloud, store to memory."""
        payload = item.payload
        if use_cloud:
            result = await self._extractor.extract_cloud(
                payload["user_message"], payload["assistant_response"],
            )
            logger.debug(f"Cloud-drained extraction #{item.id}")
        else:
            result = await self._extractor.extract_local_only(
                payload["user_message"], payload["assistant_response"],
            )
            logger.debug(
                f"Drained extraction #{item.id}: "
                f"{len(result.facts)}F {len(result.decisions)}D"
            )
        data = result.model_dump()
        await self._memory.remember_extractions(
            data, item.session_key, conversation_ts=item.conversation_ts,
        )

    async def _process_embedding(self, item: WorkItem, use_cloud: bool) -> None:
        """Re-embed text and upsert to Qdrant (overwrites zero-vector via deterministic ID).

        embed() handles local→cloud fallback internally. Deterministic point IDs
        ensure the upsert overwrites the original zero-vector point.
        """
        payload = item.payload
        await self._memory._episodic.store(
            text=payload["text"],
            session_key=item.session_key,
            role=payload.get("role", "exchange"),
            metadata=payload.get("metadata"),
            importance=payload.get("importance", 0.5),
            conversation_ts=item.conversation_ts,
        )
        logger.debug(f"Re-embedded #{item.id} (deterministic upsert)")
