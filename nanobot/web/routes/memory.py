"""Memory browser — structured memory_items + episodic FTS search."""
from __future__ import annotations

import aiohttp_jinja2
import aiosqlite
from aiohttp import web


@aiohttp_jinja2.template("pages/memory.html")
async def index(request: web.Request) -> dict:
    ctx = request.app.get("ctx", {})
    db_path = ctx.get("db_path", "")
    query = request.rel_url.query.get("q", "")
    items: list[dict] = []
    stats: dict = {}

    if db_path:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row

            if query:
                # Full-text search via episodic_fts_content
                # columns: id, text, session_key, timestamp, importance
                try:
                    cur = await db.execute(
                        """SELECT id, text, session_key, timestamp, importance
                           FROM episodic_fts_content
                           WHERE text LIKE ?
                           ORDER BY timestamp DESC LIMIT 50""",
                        (f"%{query}%",),
                    )
                    items = [dict(r) for r in await cur.fetchall()]
                except Exception:
                    items = []
            else:
                # Structured memory items
                # columns: id, category, key, value, confidence, source,
                #          session_key, qdrant_id, created_at, updated_at, access_count
                try:
                    cur = await db.execute(
                        "SELECT * FROM memory_items ORDER BY updated_at DESC LIMIT 100"
                    )
                    items = [dict(r) for r in await cur.fetchall()]
                except Exception:
                    items = []

            # Last consolidation stats
            # columns: id, run_at, episodes_processed, items_created,
            #          items_updated, items_pruned, duration_ms
            try:
                cur = await db.execute(
                    """SELECT * FROM memory_consolidation_log
                       ORDER BY run_at DESC LIMIT 1"""
                )
                row = await cur.fetchone()
                stats = dict(row) if row else {}
            except Exception:
                stats = {}

    return {"active": "memory", "items": items, "stats": stats, "query": query}


def setup(app: web.Application) -> None:
    app.router.add_get("/memory", index)
