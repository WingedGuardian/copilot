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

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    user_id TEXT DEFAULT 'user',
    status TEXT CHECK(status IN ('pending','planning','awaiting','active','completed','failed'))
        DEFAULT 'pending',
    checkpoint_tier TEXT CHECK(checkpoint_tier IN ('trivial','operational','strategic','commitment'))
        DEFAULT 'strategic',
    current_assignee TEXT,
    context_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    title TEXT DEFAULT '',
    description TEXT DEFAULT '',
    parent_id TEXT,
    priority INTEGER DEFAULT 3,
    deadline TEXT,
    session_key TEXT DEFAULT '',
    step_count INTEGER DEFAULT 0,
    steps_completed INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cost_log (
    id INTEGER PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    model TEXT,
    tokens_input INTEGER,
    tokens_output INTEGER,
    cost_usd REAL,
    task_type TEXT,
    thread_id TEXT
);
"""


async def ensure_tables(db_path: str | Path) -> None:
    """Create copilot tables if they don't exist."""
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
            ("pending_questions TEXT", "NULL"),
        ]:
            try:
                await db.execute(
                    f"ALTER TABLE tasks ADD COLUMN {col} DEFAULT {default}"
                )
            except Exception:
                pass

        # V2.1: Add tool_type to task_steps (idempotent)
        try:
            await db.execute(
                "ALTER TABLE task_steps ADD COLUMN tool_type TEXT DEFAULT 'general'"
            )
        except Exception:
            pass

        # V2.2: Add recommended_model to task_steps (idempotent)
        try:
            await db.execute(
                "ALTER TABLE task_steps ADD COLUMN recommended_model TEXT DEFAULT ''"
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


async def migrate_alerts(db_path: str | Path) -> None:
    """Alert bus schema: alerts table for unified notification log.

    Safe to call repeatedly.
    """
    db_path = Path(db_path)
    async with aiosqlite.connect(str(db_path)) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                subsystem TEXT NOT NULL,
                severity TEXT NOT NULL,
                error_key TEXT NOT NULL,
                message TEXT NOT NULL,
                delivered INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_alerts_subsystem ON alerts(subsystem, timestamp);
            CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity, timestamp);
        """)
        await db.commit()
    logger.info(f"Alerts migration complete in {db_path}")


async def migrate_routing_preferences(db_path: str | Path) -> None:
    """Routing preferences: keyword-based provider memory for conversation continuity.

    Safe to call repeatedly.
    """
    db_path = Path(db_path)
    async with aiosqlite.connect(str(db_path)) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS routing_preferences (
                id INTEGER PRIMARY KEY,
                session_key TEXT NOT NULL,
                provider TEXT NOT NULL,
                tier TEXT DEFAULT 'big',
                model TEXT,
                keywords TEXT NOT NULL,
                confidence REAL DEFAULT 0.8,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_matched TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_rp_session ON routing_preferences(session_key);
        """)
        await db.commit()
    logger.info(f"Routing preferences migration complete in {db_path}")


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
                    content=episodic_fts_content,
                    content_rowid='rowid'
                )
            """)
        except Exception:
            pass  # Table already exists

        await db.commit()
    logger.info(f"IronClaw migration complete in {db_path}")


async def migrate_heartbeat_events(db_path: str | Path) -> None:
    """Heartbeat events table: event-driven news feed for session context.

    Safe to call repeatedly.
    """
    db_path = Path(db_path)
    async with aiosqlite.connect(str(db_path)) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS heartbeat_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                event_type TEXT NOT NULL,
                severity TEXT DEFAULT 'info',
                message TEXT NOT NULL,
                source TEXT DEFAULT 'heartbeat',
                acknowledged INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_hb_events_ack
                ON heartbeat_events(acknowledged, created_at);
        """)
        await db.commit()
    logger.info(f"Heartbeat events migration complete in {db_path}")


async def migrate_sentience(db_path: str | Path) -> None:
    """Sentience plan schema: observations, autonomy, retrospectives, evolution.

    Safe to call repeatedly — all operations are idempotent.
    """
    db_path = Path(db_path)
    async with aiosqlite.connect(str(db_path)) as db:
        await db.executescript("""
            -- Structured observations from dream/heartbeat/weekly/task failures
            CREATE TABLE IF NOT EXISTS dream_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                source TEXT NOT NULL DEFAULT 'dream_cycle',
                observation_type TEXT NOT NULL,
                category TEXT DEFAULT 'operational',
                content TEXT NOT NULL,
                priority TEXT DEFAULT 'medium',
                status TEXT NOT NULL DEFAULT 'open',
                expires_at TIMESTAMP,
                resolved_at TIMESTAMP,
                resolved_by TEXT,
                resolution_note TEXT,
                related_task_id TEXT,
                metadata_json TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_dream_obs_status
                ON dream_observations(status, created_at);
            CREATE INDEX IF NOT EXISTS idx_dream_obs_source
                ON dream_observations(source, observation_type);

            -- Per-category autonomy permissions (all start as 'notify')
            CREATE TABLE IF NOT EXISTS autonomy_permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL UNIQUE,
                mode TEXT NOT NULL DEFAULT 'notify',
                granted_at TIMESTAMP,
                granted_by TEXT DEFAULT 'system',
                notes TEXT
            );

            -- Post-task analysis with optional Qdrant embedding
            CREATE TABLE IF NOT EXISTS task_retrospectives (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                outcome TEXT NOT NULL,
                approach_summary TEXT,
                diagnosis TEXT,
                learnings TEXT,
                capability_gaps TEXT,
                model_used TEXT,
                cost_usd REAL,
                qdrant_point_id TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_retro_task
                ON task_retrospectives(task_id);
            CREATE INDEX IF NOT EXISTS idx_retro_outcome
                ON task_retrospectives(outcome, created_at);

            -- Full weekly review storage
            CREATE TABLE IF NOT EXISTS weekly_review_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                duration_ms INTEGER DEFAULT 0,
                full_report TEXT,
                user_summary TEXT,
                capability_gaps_json TEXT,
                proposed_roadmap_json TEXT,
                failure_patterns_json TEXT,
                evolution_proposals_json TEXT
            );

            -- Version tracking for identity file changes
            CREATE TABLE IF NOT EXISTS evolution_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                file_path TEXT NOT NULL,
                change_type TEXT NOT NULL,
                change_description TEXT,
                diff_text TEXT,
                triggered_by TEXT,
                rolled_back INTEGER DEFAULT 0,
                rolled_back_at TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_evo_file
                ON evolution_log(file_path, created_at);
        """)

        # ALTER TABLE dream_cycle_log: add reflection_full column (idempotent)
        try:
            await db.execute(
                "ALTER TABLE dream_cycle_log ADD COLUMN reflection_full TEXT"
            )
        except Exception:
            pass  # Column already exists

        # ALTER TABLE dream_cycle_log: add job_results_json column (idempotent)
        try:
            await db.execute(
                "ALTER TABLE dream_cycle_log ADD COLUMN job_results_json TEXT"
            )
        except Exception:
            pass  # Column already exists

        # Seed autonomy_permissions with defaults (idempotent via INSERT OR IGNORE)
        for category in (
            "task_management",
            "identity_evolution",
            "config_changes",
            "proactive_notifications",
            "memory_management",
            "scheduling",
        ):
            await db.execute(
                """INSERT OR IGNORE INTO autonomy_permissions (category, mode, granted_by)
                   VALUES (?, 'notify', 'system')""",
                (category,),
            )

        await db.commit()
    logger.info(f"Sentience migration complete in {db_path}")


async def migrate_navigator(db_path: str | Path) -> None:
    """Add duo_metrics_json column to task_retrospectives for navigator duo tracking.

    Safe to call repeatedly.
    """
    db_path = Path(db_path)
    async with aiosqlite.connect(str(db_path)) as db:
        cur = await db.execute("PRAGMA table_info(task_retrospectives)")
        cols = {r[1] for r in await cur.fetchall()}
        if "duo_metrics_json" not in cols:
            await db.execute(
                "ALTER TABLE task_retrospectives ADD COLUMN duo_metrics_json TEXT"
            )
            await db.commit()
    logger.info(f"Navigator migration complete in {db_path}")


async def migrate_alert_resolution(db_path: str | Path) -> None:
    """Add resolved_at column to alerts for active/resolved tracking.

    Safe to call repeatedly.
    """
    db_path = Path(db_path)
    async with aiosqlite.connect(str(db_path)) as db:
        # Check if column already exists
        cur = await db.execute("PRAGMA table_info(alerts)")
        columns = {row[1] for row in await cur.fetchall()}
        if "resolved_at" not in columns:
            await db.execute(
                "ALTER TABLE alerts ADD COLUMN resolved_at TIMESTAMP DEFAULT NULL"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_alerts_resolved ON alerts(resolved_at)"
            )
            await db.commit()
    logger.info(f"Alert resolution migration complete in {db_path}")


async def migrate_webui(db_path: str | Path) -> None:
    """Add llm_traces table for Langfuse-style trace view in the web UI."""
    async with aiosqlite.connect(str(db_path)) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS llm_traces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                service TEXT NOT NULL,
                job_name TEXT,
                prompt_text TEXT,
                response_text TEXT,
                tokens_input INTEGER,
                tokens_output INTEGER,
                cost_usd REAL,
                model TEXT,
                latency_ms INTEGER,
                success INTEGER DEFAULT 1,
                metadata_json TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_llm_traces_service
                ON llm_traces(service, created_at);
        """)
        await db.commit()
    logger.info(f"WebUI migration complete in {db_path}")


async def log_llm_trace(
    db_path: str | Path,
    *,
    service: str,
    job_name: str = "",
    prompt_text: str = "",
    response_text: str = "",
    tokens_input: int = 0,
    tokens_output: int = 0,
    cost_usd: float = 0.0,
    model: str = "",
    latency_ms: int = 0,
    success: bool = True,
    metadata: dict | None = None,
) -> None:
    """Log an LLM trace for the web UI trace view. Best-effort -- swallows all errors."""
    import json as _json
    try:
        async with aiosqlite.connect(str(db_path)) as db:
            await db.execute(
                """INSERT INTO llm_traces
                   (service, job_name, prompt_text, response_text,
                    tokens_input, tokens_output, cost_usd, model,
                    latency_ms, success, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (service, job_name, prompt_text, response_text,
                 tokens_input, tokens_output, cost_usd, model,
                 latency_ms, int(success),
                 _json.dumps(metadata) if metadata else None),
            )
            await db.commit()
    except Exception:
        pass  # Tracing is best-effort; never interrupt the calling service
