# Heartbeat Configuration

Runs every 2 hours during active hours (7 AM - 10 PM).

## Programmatic Checks (no LLM)
- Qdrant health (HTTP GET /collections)
- Redis health (PING)
- Unresolved alerts (query alerts table, last 4 hours)
- Stuck subagents/tasks (idle > 10 min / in_progress > 30 min)

## LLM-Assisted (only when needed)
- Review pending tasks (only if tasks exist in queue)

## Dream Cycle (daily, 7 AM EST via cron `0 12 * * *`)
10 jobs orchestrated:
1. Memory consolidation
2. Cost reporting
3. Lesson review
4. Backup
5. Monitor + remediation
6. Reconcile memory stores
7. Cleanup zero vectors
8. Cleanup routing preferences
9. MEMORY.md token budget check
10. Metacognitive self-reflection

## Event Rules
- Only log events when something needs attention
- No "all clear" messages — silence means healthy
- Only message user for high-severity events
- Events feed into next session's context via heartbeat_events table
