"""Dream cycle timeline page."""
from __future__ import annotations

import json

import aiohttp_jinja2
import aiosqlite
from aiohttp import web


@aiohttp_jinja2.template("pages/dream.html")
async def index(request: web.Request) -> dict:
    ctx = request.app.get("ctx", {})
    db_path = ctx.get("db_path", "")
    timeline: list[dict] = []
    observations: list[dict] = []
    evolution_log: list[dict] = []

    if db_path:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row

            # dream_cycle_log columns: id, run_at, duration_ms,
            #   episodes_consolidated, items_created, items_pruned,
            #   lessons_reviewed, alerts_count, remediations_count,
            #   errors, reflection_full, job_results_json
            cur = await db.execute(
                """SELECT id, run_at, duration_ms, episodes_consolidated,
                          items_created, items_pruned, lessons_reviewed,
                          alerts_count, remediations_count, errors, job_results_json,
                          'nightly' as type
                   FROM dream_cycle_log
                   ORDER BY run_at DESC
                   LIMIT 30"""
            )
            for row in await cur.fetchall():
                entry = dict(row)
                if entry.get("job_results_json"):
                    try:
                        entry["job_results"] = json.loads(entry["job_results_json"])
                    except Exception:
                        entry["job_results"] = []
                else:
                    entry["job_results"] = []
                timeline.append(entry)

            # weekly_review_log columns: id, run_at, duration_ms, full_report,
            #   user_summary, capability_gaps_json, proposed_roadmap_json,
            #   failure_patterns_json, evolution_proposals_json
            cur = await db.execute(
                """SELECT id, run_at, duration_ms, user_summary, full_report,
                          'weekly' as type
                   FROM weekly_review_log
                   ORDER BY run_at DESC
                   LIMIT 10"""
            )
            for row in await cur.fetchall():
                timeline.append(dict(row))

            # Sort combined timeline by run_at descending
            timeline.sort(key=lambda x: x.get("run_at") or "", reverse=True)

            # dream_observations columns: id, created_at, source,
            #   observation_type, content, priority, actionable, acted_on,
            #   acted_on_at, expires_at, related_task_id, metadata_json
            cur = await db.execute(
                """SELECT id, created_at, source, observation_type, content,
                          priority, actionable, acted_on
                   FROM dream_observations
                   ORDER BY created_at DESC
                   LIMIT 30"""
            )
            observations = [dict(r) for r in await cur.fetchall()]

            # evolution_log columns: id, created_at, file_path, change_type,
            #   change_description, diff_text, triggered_by, rolled_back, rolled_back_at
            cur = await db.execute(
                """SELECT id, created_at, file_path, change_type,
                          change_description, triggered_by, rolled_back
                   FROM evolution_log
                   ORDER BY created_at DESC
                   LIMIT 20"""
            )
            evolution_log = [dict(r) for r in await cur.fetchall()]

    return {
        "active": "dream",
        "timeline": timeline,
        "observations": observations,
        "evolution_log": evolution_log,
    }


def setup(app: web.Application) -> None:
    app.router.add_get("/dream", index)
