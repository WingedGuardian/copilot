"""Test memory tier/tags migration."""

import aiosqlite
import pytest

from nanobot.copilot.cost.db import ensure_tables, migrate_memory_tiers, migrate_phase4


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.db"


@pytest.mark.asyncio
async def test_migrate_memory_tiers_adds_columns(db_path):
    """Migration adds tier and tags columns to memory_items."""
    await ensure_tables(db_path)
    await migrate_phase4(db_path)
    await migrate_memory_tiers(db_path)
    async with aiosqlite.connect(str(db_path)) as db:
        cur = await db.execute("PRAGMA table_info(memory_items)")
        cols = {r[1] for r in await cur.fetchall()}
        assert "tier" in cols
        assert "tags" in cols


@pytest.mark.asyncio
async def test_migrate_memory_tiers_defaults(db_path):
    """New rows get tier='domain' and tags='[]' by default."""
    await ensure_tables(db_path)
    await migrate_phase4(db_path)
    await migrate_memory_tiers(db_path)
    async with aiosqlite.connect(str(db_path)) as db:
        await db.execute(
            "INSERT INTO memory_items (category, key, value) VALUES ('fact', 'test', 'hello')"
        )
        await db.commit()
        cur = await db.execute("SELECT tier, tags FROM memory_items WHERE key='test'")
        row = await cur.fetchone()
        assert row[0] == "domain"
        assert row[1] == "[]"


@pytest.mark.asyncio
async def test_migrate_memory_tiers_idempotent(db_path):
    """Running migration twice doesn't error."""
    await ensure_tables(db_path)
    await migrate_phase4(db_path)
    await migrate_memory_tiers(db_path)
    await migrate_memory_tiers(db_path)
