"""One-time cleanup script: remove error responses and zero-vector points from memory stores.

Usage:
    python scripts/cleanup_memory.py [--dry-run]

This script:
1. Scans Qdrant `episodic_memory` for points matching error prefixes
2. Scans for zero-vector points (norm == 0.0, from embedder outages)
3. Removes matching rows from SQLite `episodic_fts` and `memory_items`
4. Logs all candidates before deleting for manual review
"""

import argparse
import asyncio
import sqlite3
from pathlib import Path

# Same error prefixes as nanobot/agent/loop.py
ERROR_PREFIXES = (
    "I'm having trouble connecting",
    "I'm sorry, the response timed out",
)

DB_PATH = Path.home() / ".nanobot" / "data" / "sqlite" / "copilot.db"
# Fallback: try relative path used in config
DB_PATH_ALT = Path("data/sqlite/copilot.db")
QDRANT_URL = "http://localhost:6333"
COLLECTION = "episodic_memory"


async def scan_qdrant(dry_run: bool) -> tuple[list, list]:
    """Scan Qdrant for error-text and zero-vector points."""
    try:
        from qdrant_client import AsyncQdrantClient
    except ImportError:
        print("ERROR: qdrant-client not installed. pip install qdrant-client")
        return [], []

    client = AsyncQdrantClient(url=QDRANT_URL)

    # Scroll all points
    error_ids = []
    zero_ids = []
    offset = None
    total_scanned = 0

    while True:
        result = await client.scroll(
            collection_name=COLLECTION,
            limit=100,
            offset=offset,
            with_vectors=True,
            with_payload=True,
        )
        points, next_offset = result
        if not points:
            break

        for p in points:
            total_scanned += 1
            text = (p.payload or {}).get("text", "")

            # Check error prefixes
            if any(text.startswith(prefix) for prefix in ERROR_PREFIXES):
                error_ids.append(p.id)
                print(f"  [ERROR TEXT] id={p.id} text={text[:100]}...")

            # Check zero vectors
            if p.vector and isinstance(p.vector, list):
                magnitude = sum(v * v for v in p.vector) ** 0.5
                if magnitude < 0.01:
                    zero_ids.append(p.id)
                    session = (p.payload or {}).get("session_key", "?")
                    print(f"  [ZERO VECTOR] id={p.id} session={session} text={text[:80]}...")

        offset = next_offset
        if offset is None:
            break

    print(f"\nQdrant scan complete: {total_scanned} points scanned")
    print(f"  Error text matches: {len(error_ids)}")
    print(f"  Zero vector matches: {len(zero_ids)}")

    if not dry_run:
        all_ids = list(set(error_ids + zero_ids))
        if all_ids:
            await client.delete(
                collection_name=COLLECTION,
                points_selector=all_ids,
            )
            print(f"  Deleted {len(all_ids)} points from Qdrant")

    await client.close()
    return error_ids, zero_ids


def clean_sqlite(error_ids: list, zero_ids: list, dry_run: bool, db_path: Path):
    """Remove matching rows from SQLite tables."""
    if not db_path.exists():
        print(f"SQLite DB not found at {db_path}")
        return

    all_ids = list(set(error_ids + zero_ids))
    if not all_ids:
        print("No IDs to clean from SQLite")
        return

    conn = sqlite3.connect(str(db_path))

    # Check episodic_fts
    try:
        placeholders = ",".join("?" * len(all_ids))
        cur = conn.execute(
            f"SELECT rowid, * FROM episodic_fts WHERE rowid IN ({placeholders})",
            all_ids,
        )
        fts_rows = cur.fetchall()
        print(f"\nSQLite episodic_fts matches: {len(fts_rows)}")
        for row in fts_rows[:10]:
            print(f"  rowid={row[0]}")

        if not dry_run and fts_rows:
            conn.execute(
                f"DELETE FROM episodic_fts WHERE rowid IN ({placeholders})",
                all_ids,
            )
            print(f"  Deleted {len(fts_rows)} from episodic_fts")
    except Exception as e:
        print(f"  episodic_fts: {e}")

    # Check memory_items for error text
    try:
        deleted = 0
        for prefix in ERROR_PREFIXES:
            cur = conn.execute(
                "SELECT id, value FROM memory_items WHERE value LIKE ?",
                (f"{prefix}%",),
            )
            rows = cur.fetchall()
            if rows:
                print(f"\nmemory_items matching '{prefix[:30]}...': {len(rows)}")
                for row in rows[:5]:
                    print(f"  id={row[0]} val={row[1][:80]}...")
                if not dry_run:
                    conn.execute(
                        "DELETE FROM memory_items WHERE value LIKE ?",
                        (f"{prefix}%",),
                    )
                    deleted += len(rows)
        if deleted:
            print(f"  Deleted {deleted} from memory_items")
    except Exception as e:
        print(f"  memory_items: {e}")

    if not dry_run:
        conn.commit()
    conn.close()


async def main():
    parser = argparse.ArgumentParser(description="Clean error responses from memory stores")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without deleting")
    args = parser.parse_args()

    print(f"Memory cleanup {'(DRY RUN)' if args.dry_run else '(LIVE)'}")
    print(f"Qdrant: {QDRANT_URL}/{COLLECTION}")

    db_path = DB_PATH if DB_PATH.exists() else DB_PATH_ALT
    print(f"SQLite: {db_path}")
    print()

    error_ids, zero_ids = await scan_qdrant(args.dry_run)
    clean_sqlite(error_ids, zero_ids, args.dry_run, db_path)

    if args.dry_run:
        print("\n--- DRY RUN COMPLETE --- Re-run without --dry-run to delete")
    else:
        print("\n--- CLEANUP COMPLETE ---")


if __name__ == "__main__":
    asyncio.run(main())
