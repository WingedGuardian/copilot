# Executive Co-Pilot: Reconciled Architecture — 2026-02-21

> **This document supersedes all prior plan docs for current state accuracy.**
> Old docs remain as decision history: V2 Architecture, Amendments #2/#3, Brain Architecture Plan, Task Lifecycle docs.
> This is a read from the code, not from the plans.
>
> **V3 note (2026-02-23):** This document reflects nanobot v1/v2 current state.
> For the Genesis v3 architecture replacing this system, see the Genesis repo
> (`WingedGuardian/GENesis`, local: `~/genesis/docs/architecture/`).
> Genesis design docs no longer live in this (copilot) repo.

---

## What the System Is Today

A reactive personal assistant with:
- **LLM-powered conversation** via plan-based routing (RouterProvider, not ConversationProvider — the rename was never done and doesn't matter)
- **Self-escalation** when the default model signals `[ESCALATE]`
- **Memory** (Qdrant episodic, SQLite structured facts, FTS5 search)
- **Background intelligence** (dream cycle, heartbeat, health check, monitor)
- **Task system** in V2.1 state — decomposition, navigator duo, retrospectives, situational awareness briefing, granular event logging, user message injection between steps, pause/resume controls, live WebUI activity stream
- **Cost tracking** and alerting via AlertBus

It is approaching supervised autonomous execution. Situational awareness, live observation, user steering, and pause/resume provide the feedback loop. Remaining gaps: task budget enforcement, worker tool restriction, DAG-based step dependencies.

---

## Model Architecture (Current Reality)

### Config Fields (all in CopilotConfig)

| Field | Default | Role |
|-------|---------|------|
| `local_model` | Qwen 30B (LM Studio) | Primary conversation, privacy mode |
| `routing_model` | Llama 3.2 3B (LM Studio) | Background extraction/parsing SLM |
| `fast_model` | `anthropic/claude-haiku-4-5` | Cloud cheap tier |
| `big_model` | `anthropic/claude-sonnet-4-6` | Cloud powerful tier, escalation target |
| `escalation_model` | `anthropic/claude-sonnet-4-6` | Self-escalation retry (same as big_model currently) |
| `default_conversation_model` | `MiniMax-M2.5` | Routing plan fallback when no plan set |
| `dream_model` | `gemini-3-flash-preview` | Dream cycle + heartbeat + weekly + monthly (all default to this) |
| `decomposition_model` | → `big_model` | Task decomposition LLM |
| `navigator_model` | → `big_model` | Navigator duo peer review |
| `emergency_cloud_model` | `openai/gpt-4o-mini` | Last-resort failover |

**Note**: `weekly_model`, `monthly_model`, `heartbeat_model` all default to `dream_model`. They are separately configurable if needed but currently all run on Gemini Flash free tier.

### Routing (Current Reality)

Decision tree (priority order):
1. **Manual override** — `/use provider` or `force_provider` in session metadata
2. **Private mode** — local model only, no cloud
3. **Routing plan** — LLM-generated plan, user-approved, stored in `self._routing_plan`
4. **Default** — `default_conversation_model` (currently MiniMax-M2.5)

Self-escalation: injected instruction when routing to local/default. If response starts with `[ESCALATE]`, retried with `escalation_model`.

Failover chain: native provider first → other cloud providers → last-known-working safety net → LM Studio → emergency model.

**What's gone**: 11-rule heuristic classifier. `heuristics.py` now only has the `RouteDecision` dataclass (18 lines). Zero routing logic in it.

---

## Periodic Services (Current Reality)

| Service | File | Interval | LLM? | Status |
|---------|------|----------|------|--------|
| CopilotHeartbeatService | `dream/cognitive_heartbeat.py` | 2h | YES | Working (gating bug fixed) |
| HealthCheckService | `dream/health_check.py` | 30min | NO | Working |
| MonitorService | `dream/monitor.py` | 5min | NO | Working |
| DreamCycle | `dream/cycle.py` | Nightly 3 AM | YES (jobs 10-12) | All 13 jobs running |
| Weekly Review | `dream/cycle.py._run_weekly_review()` | Sunday 9 AM | YES (Opus 4.6) | Status unknown |
| Monthly Review | `dream/cycle.py._run_monthly_review()` | 1st of month 10 AM | YES | Status unknown |

### Dream Cycle — All 13 Jobs

1. **consolidation** — LLM reviews recent episodes, extracts patterns
2. **cost_report** — Yesterday's cost query + LLM summary
3. **lesson_review** — Decay stale lessons, deactivate low-confidence
4. **backup** — SQLite → backup dir, prune >7 days
5. **monitor** — Health check + remediation attempt
6. **reconcile** — Qdrant vectors ↔ FTS5 orphan cleanup
7. **zero_vectors** — Delete near-zero Qdrant vectors
8. **routing_prefs** — Remove routing preferences >7 days old
9. **memory_budget** — MEMORY.md token budget check (warn only)
10. **reflection** — LLM metacognitive self-reflection → structured observations
11. **identity_evolution** — Propose or apply identity file changes (notify/autonomous modes)
12. **observation_cleanup** — Expire old unacted observations
13. **codebase_index** — Update codebase-map skill + seed episodic facts

Each job is tracked with `JobResult(status, duration_ms, detail)` in `DreamReport.jobs`. Per-job checklist is delivered to WhatsApp.

---

## Task System (Current Reality)

### What Works
- **Decomposition**: LLM breaks task into 2-8 steps with `tool_type` and `recommended_model` per step
- **Navigator Duo**: Two-checkpoint peer review. Plan review (1 round) after decomposition. Execution review (up to N rounds) after completion/block. Navigator uses provider.chat() directly (no tools). Metrics tracked per task: rounds, disagreements, resolution pattern, cost.
- **Task retrospectives**: Post-task LLM analysis stored in `task_retrospectives` table + Qdrant (embedded as `role="retrospective"`). Provides "past wisdom" to future decomposition prompts.
- **Past wisdom injection**: Decomposition prompt can receive Qdrant-recalled retrospective context to inform planning.
- **Basic status machine**: `pending` → `active` → `awaiting` (needs user) → `active` → `completed`/`failed`

### Task Tables (actual schema)
```sql
tasks (id, status, title, description, priority, session_key, step_count, steps_completed, pending_questions, context_json, ...)
task_steps (id, task_id, step_index, description, status, depends_on, result, tool_type, recommended_model, ...)
task_log (id, task_id, event, details, timestamp)
task_retrospectives (id, task_id, outcome, approach_summary, diagnosis, learnings, capability_gaps, model_used, cost_usd, qdrant_point_id, duo_metrics_json)
```

**Missing from schema** (planned, not built): `task_context`, `task_attachments`, `task_playbooks`, `free_tier_status`

### Known Bugs
- **`get_next_pending()` picks active tasks** — queries `status IN ('pending', 'active')` — can re-execute in-progress tasks
- **Workers have unrestricted tool access** — no capability profiles, shell access included contrary to V2.1 plan

### What Doesn't Exist Yet
- Park/resume (`parked` status, `/park`, `/resume`)
- Cancel command
- Cross-model deliverable review
- Budget enforcement ($2 default, pause at 100%)
- Situational Awareness Briefing in system prompt
- `task_context` table (session notes that survive compaction)
- Two-phase intake interview
- Wake event (still polling every N seconds)
- WhatsApp outbound rate limiter
- Crash recovery / state persistence across restarts for active tasks
- Task feasibility check before decomposition

---

## Context Pipeline (Current Reality)

`ExtendedContextBuilder.build_messages()` injects (in order):
1. Identity files (SOUL.md, USER.md, AGENTS.md, POLICY.md, MEMORY.md) — with 60s cache
2. Heartbeat events from `heartbeat_events` table (recent, unacknowledged)
3. Session extraction facts (from session.metadata["extractions"])
4. Active lessons from `lessons` table (confidence-filtered)
5. Core facts (high-confidence memories auto-injected)
6. Episodic memory (Qdrant recall triggered by current message)

**What's NOT injected** (planned but not built):
- Active tasks / pending questions from SQLite (Situational Awareness Briefing)
- Identity file pointer retrieval (`<!-- memory: keyword -->` tags → Qdrant)

---

## Infrastructure State

### Working
- RouterProvider with plan-based routing + self-escalation + failover
- AlertBus for loud failure reporting
- ProcessSupervisor + HealthCheckService for service monitoring
- `process_direct()` with model save/restore (race fix done)
- `skip_enrichment=True` isolation for background services
- SqlitePool exists with WAL + retry (but barely adopted)
- Asyncio timer re-arm in `try/finally` (cron resilience)
- Agent loop graceful degradation (final iteration forces text-only completion)

### Structural Debt
- **SqlitePool not adopted**: 50+ raw `aiosqlite.connect()` calls remain in AlertBus, dream/cycle.py, tasks/manager.py, loop.py. Risk: SQLite write contention under concurrent background services.
- **Timezone not normalized**: No `tz.py`. All SQL queries use `datetime('now')` UTC. `datetime.datetime.now()` used in monitor.py and health_check.py. Morning nag, active hours, cost reports, lesson decay all potentially off by timezone delta.
- **Memory consolidation uses self.model**: `_consolidate_memory()` routes to the current conversation model instead of a mid-tier model. Costs premium tokens for a background task.

---

## What V2.1 Actually Means Right Now

**V2.1 is ~30% complete.** What exists is the correct architecture for a task-capable system (decomposer, navigator duo, retrospectives) but the infrastructure that makes tasks *safe and trustworthy* is mostly unbuilt:

- Session management (task_context, situational briefing, park/resume) — not started
- Budget enforcement — not started
- Safety restrictions (worker tool scope, capability profiles) — not started
- UX integrity (cancel, confirmation flows, graceful failure) — not started

The navigator duo is the most complete Phase 1–3 feature. It was built before the Phase 0 infrastructure it should rest on.

---

## V2.2 and Beyond (Unchanged from V2 Architecture)

V2.2: OpenCode CLI coding agent, parallel task execution, full heartbeat proactive messaging (deliver_fn)
V2.3: Browser automation, external to-do integration
V2.4: Email, content pipelines, n8n
V2.5: Deeper lessons, shadow mode, self-evolving extension lifecycle
V2.6+: Dashboard, ambient awareness, neo4j graph, telegram multi-channel

**Web dashboard** was scoped in the heartbeat overhaul plan (2026-02-21). Foundation: FastAPI already serves the gateway. Read-only first, SQLite-backed. No auth initially.

---

## Document Hierarchy (updated)

When design docs conflict, trust this order:

1. **This document** (2026-02-21) — current ground truth
2. **Amendment #3** (2026-02-18) — decision record, some decisions not yet implemented
3. **Amendment #2** (2026-02-17) — decision record, some stale markers
4. **Design Review Notes** (2026-02-17)
5. **Brain Architecture Plan** (2026-02-16)
6. **V2 Architecture** (2026-02-16, revised inline)

**Explicitly superseded** (do not use for current design decisions):
- `v2.1-task-lifecycle-design.md`, `v2.1-task-lifecycle-plan.md`
- `approval-redesign-design.md`, `approval-redesign-plan.md`
