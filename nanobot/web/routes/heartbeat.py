"""Heartbeat traces page — Langfuse-style LLM I/O trace view."""
from __future__ import annotations

import html as _html

import aiohttp_jinja2
import aiosqlite
from aiohttp import web


@aiohttp_jinja2.template("pages/heartbeat.html")
async def index(request: web.Request) -> dict:
    ctx = request.app.get("ctx", {})
    db_path = ctx.get("db_path", "")
    traces: list[dict] = []
    events: list[dict] = []

    if db_path:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row

            # llm_traces columns: id, created_at, service, job_name,
            #   prompt_text, response_text, tokens_input, tokens_output,
            #   cost_usd, model, latency_ms, success, metadata_json
            cur = await db.execute(
                """SELECT id, created_at, service, job_name, model,
                          latency_ms, success,
                          length(prompt_text) as prompt_len,
                          length(response_text) as response_len
                   FROM llm_traces
                   WHERE service = 'heartbeat'
                   ORDER BY created_at DESC
                   LIMIT 50"""
            )
            traces = [dict(r) for r in await cur.fetchall()]

            # heartbeat_events columns: id, created_at, event_type, severity,
            #   message, source, acknowledged
            cur = await db.execute(
                """SELECT id, created_at, event_type, severity, message, source, acknowledged
                   FROM heartbeat_events
                   ORDER BY created_at DESC
                   LIMIT 20"""
            )
            events = [dict(r) for r in await cur.fetchall()]

    return {"active": "heartbeat", "traces": traces, "events": events}


async def trace_detail(request: web.Request) -> web.Response:
    """HTMX partial: expand a single trace to show full prompt/response."""
    trace_id = request.match_info["id"]
    ctx = request.app.get("ctx", {})
    db_path = ctx.get("db_path", "")

    if not db_path:
        return web.Response(
            text="<p class='text-nb-muted p-3'>No database configured.</p>",
            content_type="text/html",
        )

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM llm_traces WHERE id = ?", (trace_id,)
        )
        row = await cur.fetchone()

    if not row:
        return web.Response(
            text="<p class='text-nb-muted p-3'>Trace not found.</p>",
            content_type="text/html",
        )

    trace = dict(row)
    prompt = _html.escape(trace.get("prompt_text") or "(not captured)")
    response = _html.escape(trace.get("response_text") or "(not captured)")

    html_content = f"""
<div class="p-4 border-t border-nb-border bg-nb-bg space-y-4 text-xs">
  <div>
    <div class="text-nb-muted uppercase mb-1 tracking-widest text-[10px]">Prompt</div>
    <pre class="p-3 bg-nb-surface rounded overflow-x-auto whitespace-pre-wrap text-nb-text max-h-64 overflow-y-auto">{prompt}</pre>
  </div>
  <div>
    <div class="text-nb-muted uppercase mb-1 tracking-widest text-[10px]">Response</div>
    <pre class="p-3 bg-nb-surface rounded overflow-x-auto whitespace-pre-wrap text-nb-text max-h-64 overflow-y-auto">{response}</pre>
  </div>
</div>"""

    return web.Response(text=html_content, content_type="text/html")


def setup(app: web.Application) -> None:
    app.router.add_get("/heartbeat", index)
    app.router.add_get("/heartbeat/trace/{id}", trace_detail)
