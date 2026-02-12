"""Redis working memory cache for fast access to current conversation state."""

from __future__ import annotations

import json
from typing import Any

from loguru import logger


class WorkingMemory:
    """Redis-backed cache for conversation topics, entities, and recall results."""

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self._redis_url = redis_url
        self._redis = None

    async def connect(self) -> None:
        """Establish Redis connection."""
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
            await self._redis.ping()
            logger.info("Redis working memory connected")
        except Exception as e:
            logger.warning(f"Redis connection failed (degraded mode): {e}")
            self._redis = None

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None

    async def set_topic(self, session_key: str, topic: str, ttl: int = 3600) -> None:
        """Set the current conversation topic."""
        if not self._redis:
            return
        try:
            await self._redis.set(f"topic:{session_key}", topic, ex=ttl)
        except Exception as e:
            logger.warning(f"Redis set_topic failed: {e}")

    async def get_topic(self, session_key: str) -> str | None:
        """Get the current conversation topic."""
        if not self._redis:
            return None
        try:
            return await self._redis.get(f"topic:{session_key}")
        except Exception:
            return None

    async def cache_recall(
        self, session_key: str, episodes: list[dict], ttl: int = 300
    ) -> None:
        """Cache proactive recall results."""
        if not self._redis:
            return
        try:
            await self._redis.set(
                f"recall:{session_key}", json.dumps(episodes), ex=ttl
            )
        except Exception as e:
            logger.warning(f"Redis cache_recall failed: {e}")

    async def get_cached_recall(self, session_key: str) -> list[dict] | None:
        """Get cached recall results."""
        if not self._redis:
            return None
        try:
            data = await self._redis.get(f"recall:{session_key}")
            return json.loads(data) if data else None
        except Exception:
            return None

    async def set_entities(
        self, session_key: str, entities: list[str], ttl: int = 1800
    ) -> None:
        """Store active entities for current session."""
        if not self._redis:
            return
        try:
            await self._redis.set(
                f"entities:{session_key}", json.dumps(entities), ex=ttl
            )
        except Exception as e:
            logger.warning(f"Redis set_entities failed: {e}")

    async def get_entities(self, session_key: str) -> list[str]:
        """Get active entities for current session."""
        if not self._redis:
            return []
        try:
            data = await self._redis.get(f"entities:{session_key}")
            return json.loads(data) if data else []
        except Exception:
            return []

    async def health(self) -> bool:
        """Check if Redis is reachable."""
        if not self._redis:
            return False
        try:
            return await self._redis.ping()
        except Exception:
            return False
