"""SQLite schema management for copilot tables."""

from pathlib import Path

import aiosqlite
from loguru import logger

# All copilot tables — created idempotently on startup.
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS routing_log (
    id INTEGER PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    input_length INTEGER,
    has_images BOOLEAN DEFAULT 0,
    routed_to TEXT,
    provider TEXT,
    model_used TEXT,
    route_reason TEXT,
    success BOOLEAN DEFAULT 1,
    latency_ms INTEGER,
    failure_reason TEXT,
    cost_usd REAL DEFAULT 0,
    thread_id TEXT
);

CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY,
    trigger_pattern TEXT,
    lesson_text TEXT,
    confidence REAL DEFAULT 0.5,
    reinforcement_count INTEGER DEFAULT 0,
    active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_applied TIMESTAMP
);
"""


async def ensure_tables(db_path: str | Path) -> None:
    """Create copilot tables if they don't exist.

    Existing tables (cost_log, approval_rules, tasks) from Phase 1 are left
    untouched — their schema is compatible.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(str(db_path)) as db:
        await db.executescript(_SCHEMA_SQL)
        # Enable WAL mode for better concurrent read/write
        await db.execute("PRAGMA journal_mode=WAL")
        await db.commit()
    logger.info(f"Copilot tables verified in {db_path}")


async def migrate_phase3(db_path: str | Path) -> None:
    """Phase 3 schema additions: approval, satisfaction, audit, lesson columns.

    Safe to call repeatedly — all operations are idempotent.
    """
    db_path = Path(db_path)
    async with aiosqlite.connect(str(db_path)) as db:
        await db.executescript("""
            -- Pending approvals (crash recovery)
            CREATE TABLE IF NOT EXISTS pending_approvals (
                id TEXT PRIMARY KEY,
                session_key TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                tool_args_json TEXT,
                summary TEXT,
                created_at REAL,
                timeout_seconds REAL DEFAULT 300.0,
                status TEXT DEFAULT 'pending'
            );

            -- Satisfaction log (analytics)
            CREATE TABLE IF NOT EXISTS satisfaction_log (
                id INTEGER PRIMARY KEY,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                session_key TEXT,
                polarity TEXT,
                confidence REAL,
                trigger TEXT,
                lesson_id INTEGER
            );

            -- Tool audit log (forensic trail)
            CREATE TABLE IF NOT EXISTS tool_audit_log (
                id INTEGER PRIMARY KEY,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                session_key TEXT,
                tool_name TEXT NOT NULL,
                tool_args_json TEXT,
                result_summary TEXT,
                cost_usd REAL,
                latency_ms INTEGER,
                approved_by TEXT,
                denied INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_audit_session ON tool_audit_log(session_key, timestamp);
            CREATE INDEX IF NOT EXISTS idx_audit_tool ON tool_audit_log(tool_name, timestamp);
        """)

        # Add columns to existing lessons table (idempotent)
        for col, default in [
            ("source TEXT", "'system'"),
            ("category TEXT", "'general'"),
            ("applied_count INTEGER", "0"),
            ("helpful_count INTEGER", "0"),
        ]:
            try:
                await db.execute(
                    f"ALTER TABLE lessons ADD COLUMN {col} DEFAULT {default}"
                )
            except Exception:
                pass  # Column already exists

        await db.commit()
    logger.info(f"Phase 3 migration complete in {db_path}")


async def migrate_phase4(db_path: str | Path) -> None:
    """Phase 4 schema: memory_items + memory_consolidation_log.

    Safe to call repeatedly.
    """
    db_path = Path(db_path)
    async with aiosqlite.connect(str(db_path)) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS memory_items (
                id INTEGER PRIMARY KEY,
                category TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                confidence REAL DEFAULT 0.5,
                source TEXT,
                session_key TEXT,
                qdrant_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                access_count INTEGER DEFAULT 0,
                UNIQUE(category, key)
            );

            CREATE TABLE IF NOT EXISTS memory_consolidation_log (
                id INTEGER PRIMARY KEY,
                run_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                episodes_processed INTEGER DEFAULT 0,
                items_created INTEGER DEFAULT 0,
                items_updated INTEGER DEFAULT 0,
                items_pruned INTEGER DEFAULT 0,
                duration_ms INTEGER DEFAULT 0
            );
        """)
        await db.commit()
    logger.info(f"Phase 4 migration complete in {db_path}")


async def migrate_phase7(db_path: str | Path) -> None:
    """Phase 7 schema: task_steps + task_log + task table columns.

    Safe to call repeatedly.
    """
    db_path = Path(db_path)
    async with aiosqlite.connect(str(db_path)) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS task_steps (
                id INTEGER PRIMARY KEY,
                task_id TEXT NOT NULL,
                step_index INTEGER NOT NULL,
                description TEXT NOT NULL,
                status TEXT CHECK(status IN ('pending','active','completed','failed','skipped'))
                    DEFAULT 'pending',
                depends_on TEXT,
                result TEXT,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                UNIQUE(task_id, step_index)
            );

            CREATE TABLE IF NOT EXISTS task_log (
                id INTEGER PRIMARY KEY,
                task_id TEXT NOT NULL,
                event TEXT NOT NULL,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Add columns to existing tasks table (idempotent)
        for col, default in [
            ("title TEXT", "''"),
            ("description TEXT", "''"),
            ("parent_id TEXT", "NULL"),
            ("priority INTEGER", "3"),
            ("deadline TEXT", "NULL"),
            ("session_key TEXT", "''"),
            ("step_count INTEGER", "0"),
            ("steps_completed INTEGER", "0"),
        ]:
            try:
                await db.execute(
                    f"ALTER TABLE tasks ADD COLUMN {col} DEFAULT {default}"
                )
            except Exception:
                pass
        await db.commit()
    logger.info(f"Phase 7 migration complete in {db_path}")


async def migrate_phase8(db_path: str | Path) -> None:
    """Phase 8 schema: dream_cycle_log + heartbeat_log.

    Safe to call repeatedly.
    """
    db_path = Path(db_path)
    async with aiosqlite.connect(str(db_path)) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS dream_cycle_log (
                id INTEGER PRIMARY KEY,
                run_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                duration_ms INTEGER DEFAULT 0,
                episodes_consolidated INTEGER DEFAULT 0,
                items_created INTEGER DEFAULT 0,
                items_pruned INTEGER DEFAULT 0,
                lessons_reviewed INTEGER DEFAULT 0,
                alerts_count INTEGER DEFAULT 0,
                remediations_count INTEGER DEFAULT 0,
                errors TEXT
            );

            CREATE TABLE IF NOT EXISTS heartbeat_log (
                id INTEGER PRIMARY KEY,
                run_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                tasks_checked INTEGER DEFAULT 0,
                tasks_with_results INTEGER DEFAULT 0,
                duration_ms INTEGER DEFAULT 0,
                summary TEXT
            );
        """)
        await db.commit()
    logger.info(f"Phase 8 migration complete in {db_path}")


async def migrate_ironclaw(db_path: str | Path) -> None:
    """IronClaw feature adoption: episodic FTS5 full-text search table.

    Safe to call repeatedly.
    """
    db_path = Path(db_path)
    async with aiosqlite.connect(str(db_path)) as db:
        # FTS5 content table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS episodic_fts_content (
                id INTEGER PRIMARY KEY,
                text TEXT NOT NULL,
                session_key TEXT NOT NULL,
                timestamp REAL NOT NULL,
                importance REAL DEFAULT 0.5
            )
        """)
        # FTS5 virtual table
        try:
            await db.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS episodic_fts USING fts5(
                    text,
                    session_key,
                    timestamp UNINDEXED,
                    importance UNINDEXED,
                    content=episodic_fts,
                    content_rowid='rowid'
                )
            """)
        except Exception:
            pass  # Table already exists

        await db.commit()
    logger.info(f"IronClaw migration complete in {db_path}")
