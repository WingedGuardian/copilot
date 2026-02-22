"""SQLite connection pool with WAL mode and busy timeout."""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiosqlite
from loguru import logger


class SqlitePool:
    """Async SQLite connection pool — singleton per db_path.

    Features:
    - Configurable pool size
    - PRAGMA busy_timeout=5000
    - WAL journal mode
    - Retry on SQLITE_BUSY
    - Periodic WAL checkpoint
    """

    _instances: dict[str, "SqlitePool"] = {}
    _lock = threading.Lock()

    def __new__(cls, db_path: str, pool_size: int = 4) -> "SqlitePool":
        """Singleton per db_path (thread-safe)."""
        key = str(Path(db_path).resolve())
        with cls._lock:
            if key not in cls._instances:
                inst = super().__new__(cls)
                inst._initialized = False
                cls._instances[key] = inst
            return cls._instances[key]

    def __init__(self, db_path: str, pool_size: int = 4):
        if self._initialized:
            return
        self._db_path = str(db_path)
        self._pool_size = pool_size
        self._pool: asyncio.Queue[aiosqlite.Connection] = asyncio.Queue(maxsize=pool_size)
        self._all_conns: list[aiosqlite.Connection] = []
        self._initialized = True
        self._started = False
        self._checkpoint_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Initialize the pool with connections."""
        if self._started:
            return
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        for _ in range(self._pool_size):
            conn = await aiosqlite.connect(self._db_path)
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA busy_timeout=5000")
            self._all_conns.append(conn)
            await self._pool.put(conn)
        self._started = True
        self._checkpoint_task = asyncio.create_task(self._checkpoint_loop())
        logger.info(f"SqlitePool started: {self._db_path} (pool_size={self._pool_size})")

    async def close(self) -> None:
        """Close all connections in the pool."""
        if self._checkpoint_task:
            self._checkpoint_task.cancel()
            try:
                await self._checkpoint_task
            except asyncio.CancelledError:
                pass
        for conn in self._all_conns:
            try:
                await conn.close()
            except Exception:
                pass
        self._all_conns.clear()
        self._started = False
        # Remove from singleton cache
        key = str(Path(self._db_path).resolve())
        self._instances.pop(key, None)
        self._initialized = False
        logger.info(f"SqlitePool closed: {self._db_path}")

    async def acquire(self) -> aiosqlite.Connection:
        """Acquire a connection from the pool."""
        return await self._pool.get()

    async def release(self, conn: aiosqlite.Connection) -> None:
        """Return a connection to the pool."""
        await self._pool.put(conn)

    async def execute(
        self, sql: str, params: tuple = (), *, commit: bool = False, retries: int = 3
    ) -> aiosqlite.Cursor:
        """Execute SQL with automatic retry on SQLITE_BUSY."""
        conn = await self.acquire()
        try:
            for attempt in range(retries):
                try:
                    cur = await conn.execute(sql, params)
                    if commit:
                        await conn.commit()
                    return cur
                except sqlite3.OperationalError as e:
                    if "locked" in str(e).lower() and attempt < retries - 1:
                        logger.warning(f"SQLite locked, retrying ({attempt + 1}/{retries})")
                        await asyncio.sleep(0.1 * (attempt + 1))
                    else:
                        raise
        finally:
            await self.release(conn)

    async def execute_commit(self, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
        """Execute SQL and commit."""
        return await self.execute(sql, params, commit=True)

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        """Hold a pooled connection for a multi-statement transaction.

        Commits on clean exit, rolls back on exception, always releases.
        """
        conn = await self.acquire()
        try:
            yield conn
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
        finally:
            await self.release(conn)

    async def fetchall(self, sql: str, params: tuple = ()) -> list[Any]:
        """Execute and fetch all rows."""
        conn = await self.acquire()
        try:
            cur = await conn.execute(sql, params)
            return await cur.fetchall()
        finally:
            await self.release(conn)

    async def fetchone(self, sql: str, params: tuple = ()) -> Any:
        """Execute and fetch one row."""
        conn = await self.acquire()
        try:
            cur = await conn.execute(sql, params)
            return await cur.fetchone()
        finally:
            await self.release(conn)

    async def _checkpoint_loop(self) -> None:
        """Periodic WAL checkpoint every 5 minutes."""
        while True:
            await asyncio.sleep(300)
            conn = await self.acquire()
            try:
                await conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
                logger.debug(f"WAL checkpoint completed: {self._db_path}")
            except Exception as e:
                logger.warning(f"WAL checkpoint failed: {e}")
            finally:
                await self.release(conn)
