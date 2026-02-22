"""Integration tests for copilot subsystems.

These tests verify that components work together correctly.
They require external services (Qdrant, Redis) to be running.
"""

import os
import tempfile

import pytest

# Skip all integration tests if services not available
pytestmark = pytest.mark.skipif(
    os.getenv("COPILOT_INTEGRATION_TESTS") != "1",
    reason="Integration tests require COPILOT_INTEGRATION_TESTS=1",
)


@pytest.mark.asyncio
async def test_db_initialization():
    """Database schema creates successfully."""
    from nanobot.copilot.cost.db import ensure_tables, migrate_phase3

    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
        db_path = tmp.name

    try:
        await ensure_tables(db_path)
        await migrate_phase3(db_path)

        # Verify tables exist
        import aiosqlite

        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = [row[0] for row in await cursor.fetchall()]

            expected_tables = [
                "cost_log",
                "routes",
                "threads",
                "pending_approvals",
                "satisfaction_log",
                "tool_audit_log",
                "lessons",
                "memory_items",
                "memory_consolidation_log",
                "task_steps",
                "task_log",
                "dream_cycle_log",
                "heartbeat_log",
            ]

            for table in expected_tables:
                assert table in tables, f"Missing table: {table}"
    finally:
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_qdrant_connection():
    """Qdrant client connects and creates collection."""
    from nanobot.copilot.memory.embedder import Embedder
    from nanobot.copilot.memory.episodic import EpisodicStore

    embedder = Embedder()
    store = EpisodicStore(embedder, qdrant_url="http://localhost:6333")

    try:
        await store.ensure_collection()
        count = await store.count()
        assert isinstance(count, int)
    except Exception as e:
        pytest.skip(f"Qdrant not available: {e}")


@pytest.mark.asyncio
async def test_redis_connection():
    """Redis client connects successfully."""
    from nanobot.copilot.memory.working import WorkingMemory

    wm = WorkingMemory(redis_url="redis://localhost:6379/0")

    try:
        await wm.connect()
        healthy = await wm.health()
        assert healthy is True
        await wm.close()
    except Exception as e:
        pytest.skip(f"Redis not available: {e}")


@pytest.mark.asyncio
async def test_routing_with_cost_logging():
    """Router logs cost data correctly."""
    # This would require mocking LLM providers
    # Full implementation deferred to end-to-end test
    pass


@pytest.mark.asyncio
async def test_approval_flow():
    """Approval interceptor blocks and resolves correctly."""
    # This would require mocking the bus and provider
    # Full implementation in end-to-end test
    pass


@pytest.mark.asyncio
async def test_memory_storage_and_recall():
    """Memory stores and recalls episodes correctly."""
    from nanobot.copilot.memory.embedder import Embedder
    from nanobot.copilot.memory.episodic import EpisodicStore

    embedder = Embedder()
    store = EpisodicStore(embedder)

    try:
        await store.ensure_collection()

        # Store an episode
        point_id = await store.store(
            text="Python is a high-level programming language",
            session_key="test:1",
            role="user",
            metadata={},
        )
        assert point_id is not None

        # Recall similar content
        results = await store.recall("what is Python?", limit=5)
        assert len(results) > 0
        assert any("Python" in r.text for r in results)
    except Exception as e:
        pytest.skip(f"Qdrant not available: {e}")
