# Heartbeat Configuration

Runs every 2 hours during active hours (7 AM - 10 PM).

## Programmatic Checks (no LLM)
- Qdrant health (HTTP GET /collections)
- Unresolved alerts (query alerts table, last 4 hours)
- Stuck subagents/tasks (idle > 10 min / in_progress > 30 min)

## LLM-Assisted (only when needed)
- Review pending tasks (only if tasks exist in queue)

## Dream Cycle (daily, 7 AM EST via cron `0 12 * * *`)
13 jobs orchestrated, each tracked via `JobResult` (ok/skipped/error + timing):
1. Memory consolidation
2. Cost reporting
3. Lesson review
4. Backup
5. Monitor + remediation
6. Reconcile memory stores (Qdrant vs FTS5)
7. Cleanup zero vectors
8. Cleanup routing preferences
9. MEMORY.md token budget check
10. Metacognitive self-reflection
11. Identity evolution
12. Observation cleanup
13. Codebase indexing

Per-job results are: (a) included in the delivered summary (`[+]/[~]/[!]` checklist), (b) persisted to `dream_cycle_log.job_results_json` for weekly review inspection.

## Heartbeat Checklist
After each cognitive heartbeat tick, a `heartbeat_checklist` event is logged to `heartbeat_events` recording what inputs were gathered (HEARTBEAT.md, observations, tasks, permissions, lessons, morning brief) and whether LLM execution succeeded. Visible via `/status`.

## Weekly/Monthly Review Checklists
Both `run_weekly()` and `run_monthly()` build a data-gathering checklist that is prepended to the delivered summary. This confirms which data sources were loaded, whether the LLM call succeeded, and whether the report was persisted.

## Context Isolation (`skip_enrichment=True`)

Background services (heartbeat, dream, weekly/monthly reviews, cron, task retrospectives) call `process_direct()` with `skip_enrichment=True`. This means they do **NOT** receive:
- Proactive episodic recall from user conversations
- Lesson injection (or the `mark_applied` side effect)
- Heartbeat event injection (or the destructive acknowledgment side effect)
- Post-response extraction or `remember_exchange()` (prevents reverse contamination)

They **DO** still receive:
- Identity files (SOUL.md, USER.md, AGENTS.md, POLICY.md) via base ContextBuilder
- Memory scratchpad (MEMORY.md) via base ContextBuilder
- Core facts (~200 tokens, high-confidence items about the user)
- Their own session history (via session_key isolation)

The **cognitive heartbeat** additionally queries active lessons directly (read-only, no `mark_applied` side effect) and injects them into its prompt via `_build_cognitive_prompt`. This gives the heartbeat awareness of hard-won rules when making decisions, without corrupting lesson metadata.

**Rule**: Any new enrichment added to `_process_message()` must be guarded by the `skip_enrichment` flag.

## Event Rules
- Only log events when something needs attention
- No "all clear" messages — silence means healthy
- Only message user for high-severity events
- Events feed into next session's context via heartbeat_events table
