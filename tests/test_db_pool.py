"""Phase 3 tests: Data Integrity (SQLite pool + dream repairs)."""

import asyncio
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# 3A. SQLite Connection Pool
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pool_singleton():
    """Same db_path should return the same pool instance."""
    from nanobot.copilot.db import SqlitePool

    with tempfile.TemporaryDirectory() as tmpdir:
        db = Path(tmpdir) / "test.db"
        p1 = SqlitePool(str(db), pool_size=2)
        p2 = SqlitePool(str(db), pool_size=2)
        assert p1 is p2
        # Cleanup singleton
        SqlitePool._instances.clear()


@pytest.mark.asyncio
async def test_pool_start_and_execute():
    """Pool should start, execute SQL, and close."""
    from nanobot.copilot.db import SqlitePool

    with tempfile.TemporaryDirectory() as tmpdir:
        db = Path(tmpdir) / "test.db"
        pool = SqlitePool(str(db), pool_size=2)
        try:
            await pool.start()
            await pool.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)", commit=True)
            await pool.execute("INSERT INTO t VALUES (1, 'hello')", commit=True)
            row = await pool.fetchone("SELECT v FROM t WHERE id = 1")
            assert row[0] == "hello"
        finally:
            await pool.close()


@pytest.mark.asyncio
async def test_pool_wal_mode():
    """Pool connections should use WAL journal mode."""
    from nanobot.copilot.db import SqlitePool

    with tempfile.TemporaryDirectory() as tmpdir:
        db = Path(tmpdir) / "test.db"
        pool = SqlitePool(str(db), pool_size=1)
        try:
            await pool.start()
            row = await pool.fetchone("PRAGMA journal_mode")
            assert row[0] == "wal"
        finally:
            await pool.close()


@pytest.mark.asyncio
async def test_pool_fetchall():
    """fetchall should return all matching rows."""
    from nanobot.copilot.db import SqlitePool

    with tempfile.TemporaryDirectory() as tmpdir:
        db = Path(tmpdir) / "test.db"
        pool = SqlitePool(str(db), pool_size=2)
        try:
            await pool.start()
            await pool.execute("CREATE TABLE items (n INTEGER)", commit=True)
            for i in range(5):
                await pool.execute("INSERT INTO items VALUES (?)", (i,), commit=True)
            rows = await pool.fetchall("SELECT n FROM items ORDER BY n")
            assert len(rows) == 5
            assert rows[0][0] == 0
        finally:
            await pool.close()


@pytest.mark.asyncio
async def test_pool_concurrent_access():
    """Pool should handle concurrent access."""
    from nanobot.copilot.db import SqlitePool

    with tempfile.TemporaryDirectory() as tmpdir:
        db = Path(tmpdir) / "test.db"
        pool = SqlitePool(str(db), pool_size=4)
        try:
            await pool.start()
            await pool.execute("CREATE TABLE c (id INTEGER PRIMARY KEY)", commit=True)

            async def insert(n):
                await pool.execute("INSERT INTO c VALUES (?)", (n,), commit=True)

            await asyncio.gather(*[insert(i) for i in range(20)])
            rows = await pool.fetchall("SELECT COUNT(*) FROM c")
            assert rows[0][0] == 20
        finally:
            await pool.close()


# ---------------------------------------------------------------------------
# 3B. Dream Cycle Data Repairs
# ---------------------------------------------------------------------------

def test_dream_cycle_has_reconcile():
    """DreamCycle should have _reconcile_memory_stores method."""
    from nanobot.copilot.dream.cycle import DreamCycle

    dc = DreamCycle()
    assert hasattr(dc, '_reconcile_memory_stores')
    assert hasattr(dc, '_cleanup_zero_vectors')


@pytest.mark.asyncio
async def test_dream_backup_uses_sqlite_backup():
    """Dream backup should use sqlite3.backup() not shutil.copy2."""
    import inspect

    from nanobot.copilot.dream.cycle import DreamCycle

    source = inspect.getsource(DreamCycle._backup)
    assert "src.backup(dst)" in source
    assert "shutil.copy2" not in source
