# Cognitive Heartbeat

The heartbeat is your inner monologue — periodic self-awareness that runs every 2 hours whether or not anyone is talking to you.

## Architecture

Two services handle periodic awareness. They are complementary, not overlapping:

| Service | Type | Interval | Purpose |
|---------|------|----------|---------|
| **CopilotHeartbeatService** | LLM-powered | 2h | Cognitive awareness: dream observations, tasks, proactive thinking |
| **HealthCheckService** | Programmatic | 30min | Infrastructure: Qdrant ping, alert resolution, stuck job detection |

The cognitive heartbeat does NOT duplicate health checks. If infrastructure needs intelligence, it escalates to the dream cycle.

## What the Heartbeat Sees

Each tick gathers context from multiple sources:

1. **HEARTBEAT.md tasks** — user-assigned tasks (backward compatible with upstream)
2. **Unacted dream observations** — insights from the dream cycle that haven't been addressed (top 10 by priority)
3. **Active tasks** — pending/active/awaiting tasks from the task queue
4. **Autonomy permissions** — what you can do autonomously vs. what needs user approval
5. **Morning brief** — first tick after a dream cycle gets the full reflection for continuity

## Autonomy Permissions

Each category has a mode: `notify`, `autonomous`, or `disabled`.

| Category | Description |
|----------|-------------|
| task_management | Creating, prioritizing, completing tasks |
| identity_evolution | Modifying SOUL.md, AGENTS.md, etc. |
| config_changes | Adjusting runtime preferences |
| proactive_notifications | Flagging things for the user |
| memory_management | Memory consolidation, pruning |
| scheduling | Creating/modifying cron jobs |

Default: all `notify`. User grants autonomy explicitly via conversation.

## What You Can Do

- Execute HEARTBEAT.md tasks (tools available as normal)
- Write observations (patterns, capability gaps, risks)
- Flag items for the user's next conversation (via heartbeat_events)
- Mark dream observations as acted_on when you've addressed them

## Output Format

After executing any HEARTBEAT.md tasks, optionally append structured observations:
```json
[
  {"type": "observation", "content": "...", "observation_type": "pattern|capability_gap|risk|proactive_action", "priority": "low|medium|high"},
  {"type": "user_flag", "content": "...", "severity": "info|medium|high"}
]
```

If nothing needs attention, skip the JSON block. Silence means healthy.

## Concurrency Safety

The heartbeat automatically skips when the dream cycle is running (checks `DreamCycle.is_running` flag) to avoid concurrent LLM calls through the same agent.

## Dream Cycle (daily, 7 AM EST)

13 jobs orchestrated:
1. Memory consolidation
2. Cost reporting
3. Lesson review
4. Backup
5. Monitor + remediation
6. Reconcile memory stores
7. Cleanup zero vectors
8. Cleanup routing preferences
9. MEMORY.md token budget check
10. Metacognitive self-reflection (structured observations)
11. Identity evolution (propose or apply identity file changes)
12. Observation cleanup (expire old unacted dream_observations)
13. Codebase indexing (update project map skill)

## Event Rules

- Only log events when something needs attention
- No "all clear" messages — silence means healthy
- Only message user for high-severity events
- Events feed into next session's context via heartbeat_events table
