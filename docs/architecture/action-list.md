# Prioritized Action List — 2026-02-21

> **Basis**: Gap analysis + reconciled architecture + recurring failure patterns.
> **Ordering**: Blocking bugs first → foundational infrastructure → trust/safety features → value features.
> **Size**: S = <2h, M = half-day, L = full day, XL = multi-day
>
> **V3 note (2026-02-23):** This action list targets nanobot v1/v2. With the
> Genesis v3 migration to Agent Zero, most items become irrelevant (fresh codebase
> eliminates SqlitePool debt, timezone issues, task system bugs). Retained as
> decision history.

---

## Tier 1: Active Bugs (Break things silently right now)

### 1. Fix `get_next_pending()` — picks active tasks [S]
**File**: `nanobot/copilot/tasks/manager.py`
**Bug**: `status IN ('pending', 'active')` — an active task can be re-picked and re-executed.
**Fix**: Change to `status = 'pending'` only. One-line change.
**Why first**: Can corrupt in-progress task state. Every TaskWorker tick is a potential re-execution.

### 2. SqlitePool adoption — AlertBus + TaskManager + DreamCycle [L]
**Files**: `alerting/bus.py` (2 calls), `tasks/manager.py` (30+), `dream/cycle.py` (20+), `agent/loop.py` (3)
**Bug**: Raw `aiosqlite.connect()` bypasses WAL and retry logic. Background services (heartbeat, dream, health check, monitor) run concurrently and can all hit SQLite simultaneously.
**Fix**: Replace all raw calls with `get_pool(db_path).execute(...)`. SqlitePool already exists — it's just not used.
**Why here**: Silent `SQLITE_BUSY` failures or lost writes are already possible. Gets worse as more background services activate.

### 3. Memory consolidation routing — uses self.model [S]
**File**: `nanobot/agent/loop.py` `_consolidate_memory()`
**Bug**: Uses `self.model` (main conversation model, currently Sonnet) for background memory work.
**Fix**: Route to `self._copilot_config.fast_model` or `resolved_extraction_cloud_model`. One-line change.
**Why here**: Burns Sonnet tokens on a background task that Haiku handles equally well.

---

## Tier 2: Foundation (Everything else depends on this)

### 4. Timezone normalization — create tz.py [M]
**Files**: New `nanobot/copilot/tz.py` + wire into `copilot/__init__.py` + fix P3 sites (monitor.py, health_check.py active hours)
**Problem**: Morning nag, active hours, cost reports, lesson decay all use UTC or naive local time. User is EST. Off by 4–5 hours.
**Priority sites** (fix first):
- `monitor.py` morning nag: `datetime.datetime.now().hour != 7` → `tz.local_now().hour != 7`
- `health_check.py` active hours: same pattern
**Remaining sites** (P2 — fix next):
- `dream/cycle.py` ~15 queries: `datetime('now', '-1 day')` → bind `tz.local_date_str(-1)`
- `cost/alerting.py`, `status/aggregator.py`, `tools/ops_log.py` — similar patterns
**Why here**: Morning nag and active hours are user-visible and currently wrong.

### 5. ~~Situational Awareness Briefing [M]~~ ✅ DONE (2026-02-22)
**File**: `nanobot/copilot/context/extended.py`
**Implemented**: `build_situational_briefing()` static async method with 4 independent SQL queries (active tasks, pending questions, completions, daily spend). Wired into `loop.py`, guarded by `skip_enrichment`. Per-query error isolation.
- Active/awaiting tasks
- Unacknowledged pending questions from tasks
- Completions in last 24h
- Today's spend
Injected as `## Current Situation` block. Empty → omitted entirely.
**Why here**: Every task interaction is degraded without this. Navigator duo escalations get lost. The LLM doesn't know what it's managing.

### 6. task_context table [S]
**Files**: `nanobot/copilot/cost/db.py` (schema) + task system writes
**Problem**: Session notes from task system are piggybacked on `heartbeat_events` (wrong purpose) or lost on compaction. No queryable history of what a task delivered or what it needs.
**Fix**: Create the table (Decision #36 schema already designed), write session notes on task completion/question.
**Why here**: Prerequisite for Situational Awareness Briefing to work at full fidelity.

---

## Tier 3: Task System Safety (Needed before trusting tasks with real work)

### 7. Worker tool restriction — research + files only [M]
**Files**: `tasks/worker.py`, CLI task execution wiring
**Problem**: Workers get full tool suite including shell. V2.1 design explicitly says workers get only web search + file read/write. Shell access is a security concern.
**Fix**: Pass a restricted `tools_whitelist` to worker SubagentManager calls.
**Why here**: Before running tasks on anything sensitive, workers need scoped access.

### 8. Task budget enforcement [M]
**Files**: `tasks/worker.py`, `tasks/manager.py`
**Problem**: `default_task_budget: float = 2.00` exists in config but no enforcement. Tasks can run indefinitely at cost.
**Fix**: Track cumulative cost per task. At $5 (or configurable threshold), pause and ask user. Uses existing AlertBus for the escalation.
**Why here**: Without this, a misbehaving task silently burns money.

### 9. ~~Graceful cancellation + /cancel command [S]~~ ⚠️ PARTIAL (2026-02-22)
**Files**: `tasks/worker.py`, `web/routes/tasks.py`, `task_detail.html`
**Done**: Cancel via WebUI (`POST /tasks/{id}/cancel`). Pause/resume added for graceful control. Worker checks paused status at step boundaries.
**Remaining**: No `/cancel` CLI tool action yet. No two-tier confirmation.

### 10. ~~Park/resume [M]~~ ✅ DONE (2026-02-22)
**Files**: `cost/db.py`, `tasks/manager.py`, `tasks/worker.py`, `web/routes/tasks.py`, `task_detail.html`
**Implemented as pause/resume**: `paused` status with schema migration, `pause_task()`/`resume_task()` on manager, worker skips paused tasks, WebUI pause/resume buttons + paused badge. Supersedes parked status design.

---

## Tier 4: Task UX and Robustness

### 11. Wake event instead of polling [S]
**File**: `tasks/worker.py`
**Problem**: TaskWorker polls on `asyncio.sleep(interval)`. New tasks wait up to N seconds before being picked up.
**Fix**: Replace sleep with `asyncio.Event`. Task creation signals the event. Worker wakes immediately.
**Why deferred**: Low impact until task volume increases. Do after the safety features.

### 12. Two-phase intake interview [M]
**Files**: Identity files (AGENTS.md) + task detection prompt guidance
**Problem**: No structured intake. LLM detects task potential and creates it directly. Orchestrator gets whatever nanobot captured.
**Fix**: Primarily an LLM guidance change — update AGENTS.md with the two-phase protocol. Nanobot confirms task → gathers requirements → creates task record. Orchestrator gets structured handoff. No new code needed if framed correctly as a prompt engineering change.

### 13. Crash recovery for awaiting tasks [S]
**File**: `tasks/worker.py._tick()`
**Problem**: On restart, `awaiting` tasks (waiting for user input) are not resumed. They sit in DB with no worker picking them up.
**Fix**: On startup, scan for `awaiting` tasks and re-inject their `pending_questions` into nanobot's context.

### 14. Cross-model deliverable review [L]
**Files**: New reviewer logic in `tasks/worker.py`, config (`reviewer_model`)
**Problem**: Navigator duo reviews the plan and execution, but not the final deliverable quality before delivery.
**Fix**: Before delivering to user, a different model (reviewer_model, defaults to Haiku/Gemini Flash) scores the output on completeness/accuracy/relevance. Below threshold → orchestrator gets feedback + re-plans. Max 2 auto-iterations.
**Why deferred**: High value but medium complexity. Do after the safety foundations are solid.

### 15. WhatsApp outbound rate limiter [S]
**File**: `nanobot/channels/whatsapp.py`
**Problem**: No guard against message flooding. Task progress heartbeats (every node completion) could overwhelm the chat.
**Fix**: ~20 lines. 1 msg/2s limit, FIFO queue, digest merge at 10 queued.

---

## Tier 5: Infrastructure Completeness

### 16. Free tier status table [M]
**Files**: `nanobot/copilot/cost/db.py` (schema) + orchestrator dispatch logic
**Problem**: Orchestrator can't know which free-tier models have hit daily limits. Sends to exhausted free APIs, gets billed.
**Fix**: Create `free_tier_status` table (Decision #40 schema). After each 0-cost API call, confirm free tier active. Update on billing detection. Orchestrator checks before dispatching.
**Why deferred**: Adds complexity. Do when task execution volume warrants it.

### 17. Context bridging on model switch [S]
**File**: `nanobot/copilot/routing/router.py`
**Problem**: When model changes (via `/use` or escalation), new model has no context about the previous model's participation.
**Fix**: Inject `"Note: You are continuing a conversation previously handled by {model}."` as system note. ~20 tokens. Track `last_model_used` in session metadata.

### 18. Identity file pointer retrieval [S]
**File**: `nanobot/copilot/context/extended.py`
**Problem**: When identity files have `<!-- memory: keyword1, keyword2 -->` tags pointing to evicted content, nothing retrieves that content.
**Fix**: In `_build_identity_context()`, detect pointer tags, run Qdrant search for keywords, append as `## Deep Context`. Reuses existing proactive recall mechanism.

---

## Not Doing (Deferred by Design)

| Item | Reason |
|------|--------|
| Proactive heartbeat WhatsApp delivery | V2.2 scope — need data from heartbeat first |
| Parallel task execution | V2.2 scope — sequential queue sufficient for now |
| Capability profiles per task type | V2.2 scope — needs shell workers to matter |
| Playbook system | V2.2 scope — needs task volume to seed data |
| Web dashboard | Scoped but not yet designed — needs routes + frontend decision |
| Natural language model switching | V2.2 scope — `/use` command sufficient for now |
| OpenCode CLI integration | V2.2 scope — blocked on worker tool safety first |
| Shadow mode / autonomy calibration | V2.5 scope |
| Browser automation | V2.3 scope |

---

## Suggested Sequencing for Next 2–3 Sessions

**Session A** (stabilize what's broken):
1. Fix `get_next_pending()` bug (#1) — 5 min
2. Fix memory consolidation routing (#3) — 5 min
3. Create tz.py + fix monitor.py/health_check.py active hours (#4, P3 sites) — 1–2h

**Session B** (make tasks usable):
4. Create task_context table (#6) — 30 min
5. Situational Awareness Briefing (#5) — 2–3h
6. Cancellation command (#9) — 1h

**Session C** (task safety):
7. Worker tool restriction (#7) — 1–2h
8. Task budget enforcement (#8) — 2–3h
9. SqlitePool adoption — AlertBus + TaskManager (#2, partial) — 2h

**Avoid**: Starting the web dashboard, OpenCode integration, or parallel execution before Tier 1 and Tier 2 are done.
