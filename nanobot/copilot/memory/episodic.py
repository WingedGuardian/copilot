"""Qdrant episodic memory store with multi-factor retrieval scoring."""

from __future__ import annotations

import math
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from loguru import logger


@dataclass
class Episode:
    """A single episodic memory entry."""

    id: str
    text: str
    session_key: str = ""
    role: str = ""  # 'user', 'assistant', 'preference', 'fact', 'entity'
    timestamp: float = 0.0
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class EpisodicStore:
    """Qdrant-backed episodic memory with MemU-style multi-factor scoring."""

    COLLECTION = "episodic_memory"

    def __init__(
        self,
        embedder,
        qdrant_url: str = "http://localhost:6333",
        dimensions: int = 768,
    ):
        self._embedder = embedder
        self._qdrant_url = qdrant_url
        self._dimensions = dimensions
        self._client = None

    async def _ensure_client(self):
        if self._client is None:
            from qdrant_client import AsyncQdrantClient
            self._client = AsyncQdrantClient(url=self._qdrant_url)
            await self.ensure_collection()

    async def ensure_collection(self) -> None:
        """Create the episodic_memory collection if it doesn't exist."""
        from qdrant_client.models import Distance, VectorParams
        try:
            collections = await self._client.get_collections()
            names = [c.name for c in collections.collections]
            if self.COLLECTION not in names:
                await self._client.create_collection(
                    collection_name=self.COLLECTION,
                    vectors_config=VectorParams(
                        size=self._dimensions,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info(f"Created Qdrant collection: {self.COLLECTION}")
        except Exception as e:
            logger.warning(f"Qdrant collection check failed: {e}")

    async def store(
        self,
        text: str,
        session_key: str,
        role: str = "exchange",
        metadata: dict[str, Any] | None = None,
        importance: float = 0.5,
    ) -> str:
        """Embed and store a single memory point. Returns point ID."""
        await self._ensure_client()
        from qdrant_client.models import PointStruct

        vector = await self._embedder.embed(text)
        point_id = str(uuid.uuid4())
        payload = {
            "text": text,
            "session_key": session_key,
            "role": role,
            "timestamp": time.time(),
            "access_count": 0,
            "importance": importance,
            **(metadata or {}),
        }

        try:
            await self._client.upsert(
                collection_name=self.COLLECTION,
                points=[PointStruct(id=point_id, vector=vector, payload=payload)],
            )
        except Exception as e:
            logger.warning(f"Qdrant store failed: {e}")
        return point_id

    async def store_extractions(
        self, extractions: dict[str, Any], session_key: str
    ) -> list[str]:
        """Store individual facts/decisions/entities as separate high-importance points."""
        ids = []
        for key in ("facts", "decisions", "constraints", "entities"):
            for item in extractions.get(key, []):
                role = key.rstrip("s")  # 'fact', 'decision', etc.
                pid = await self.store(
                    text=item,
                    session_key=session_key,
                    role=role,
                    importance=0.8,
                )
                ids.append(pid)
        return ids

    async def recall(
        self,
        query: str,
        limit: int = 5,
        session_key: str | None = None,
        min_score: float = 0.35,
    ) -> list[Episode]:
        """Recall memories using multi-factor scoring.

        Factors: semantic similarity (50%), recency (20%), access count (15%), importance (15%).
        """
        await self._ensure_client()
        vector = await self._embedder.embed(query)

        # Fetch 3x candidates for re-ranking
        fetch_limit = limit * 3
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            search_filter = None
            if session_key:
                search_filter = Filter(must=[
                    FieldCondition(key="session_key", match=MatchValue(value=session_key))
                ])

            results = await self._client.search(
                collection_name=self.COLLECTION,
                query_vector=vector,
                limit=fetch_limit,
                score_threshold=min_score * 0.5,  # Lower threshold for pre-filter
                query_filter=search_filter,
            )
        except Exception as e:
            logger.warning(f"Qdrant recall failed: {e}")
            return []

        if not results:
            return []

        # Multi-factor re-ranking
        now = time.time()
        max_access = max((r.payload.get("access_count", 0) for r in results), default=1) or 1
        scored_episodes: list[tuple[float, Episode]] = []

        for r in results:
            payload = r.payload or {}
            semantic_score = r.score
            ts = payload.get("timestamp", now)
            days_old = (now - ts) / 86400
            recency_score = math.exp(-days_old / 30)
            access_count = payload.get("access_count", 0)
            access_score = math.log(1 + access_count) / math.log(1 + max_access) if max_access > 0 else 0
            importance_score = payload.get("importance", 0.5)

            final_score = (
                0.50 * semantic_score
                + 0.20 * recency_score
                + 0.15 * access_score
                + 0.15 * importance_score
            )

            if final_score >= min_score:
                episode = Episode(
                    id=str(r.id),
                    text=payload.get("text", ""),
                    session_key=payload.get("session_key", ""),
                    role=payload.get("role", ""),
                    timestamp=ts,
                    score=final_score,
                    metadata={k: v for k, v in payload.items() if k not in ("text",)},
                )
                scored_episodes.append((final_score, episode))

        # Sort by final score and return top N
        scored_episodes.sort(key=lambda x: x[0], reverse=True)
        top = [ep for _, ep in scored_episodes[:limit]]

        # Increment access_count for returned episodes
        for ep in top:
            try:
                await self._client.set_payload(
                    collection_name=self.COLLECTION,
                    payload={"access_count": ep.metadata.get("access_count", 0) + 1},
                    points=[ep.id],
                )
            except Exception:
                pass

        return top

    async def recall_hybrid(
        self,
        query: str,
        fts_store: "FullTextStore",
        limit: int = 5,
        session_key: str | None = None,
        min_score: float = 0.35,
    ) -> list[Episode]:
        """Hybrid recall: vector search + FTS5, combined via Reciprocal Rank Fusion."""
        from nanobot.copilot.memory.fulltext import reciprocal_rank_fusion

        # Run both searches with expanded candidate set
        vector_results = await self.recall(
            query, limit=limit * 2, session_key=session_key, min_score=min_score
        )
        fts_results = await fts_store.search(
            query, limit=limit * 2, session_key=session_key
        )

        if not vector_results and not fts_results:
            return []

        combined = reciprocal_rank_fusion(vector_results, fts_results)

        # Convert back to Episode objects
        episodes: list[Episode] = []
        for item in combined[:limit]:
            if "episode" in item:
                ep = item["episode"]
                ep.score = item["score"]
                episodes.append(ep)
            else:
                fts_r = item.get("fts_result")
                episodes.append(Episode(
                    id=str(fts_r.id) if fts_r else "fts",
                    text=item["text"],
                    session_key=fts_r.session_key if fts_r else "",
                    timestamp=fts_r.timestamp if fts_r else 0.0,
                    score=item["score"],
                ))
        return episodes

    async def recall_global(
        self, query: str, limit: int = 5, min_score: float = 0.40
    ) -> list[Episode]:
        """Search across all sessions (proactive recall)."""
        return await self.recall(query, limit=limit, session_key=None, min_score=min_score)

    async def count(self) -> int:
        """Total number of episodes stored."""
        try:
            await self._ensure_client()
            info = await self._client.get_collection(self.COLLECTION)
            return info.points_count
        except Exception:
            return 0

    async def delete_by_session(self, session_key: str) -> None:
        """Delete all episodes for a session."""
        try:
            await self._ensure_client()
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            await self._client.delete(
                collection_name=self.COLLECTION,
                points_selector=Filter(must=[
                    FieldCondition(key="session_key", match=MatchValue(value=session_key))
                ]),
            )
        except Exception as e:
            logger.warning(f"Qdrant delete failed: {e}")
