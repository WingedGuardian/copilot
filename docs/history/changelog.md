# Changelog

All notable changes to the Executive Co-Pilot project.

---

## 2026-02-22 — Phase 0: SqlitePool `transaction()` + Full UTC→Local Timezone Normalization (`feat/phase0`)

### Problem
1. **SqlitePool lacked atomic multi-statement writes.** TaskManager had 17 direct `aiosqlite.connect()` call sites; multi-statement writes (INSERT + log, UPDATE + log) were non-atomic. A crash between commits left the DB in a partially-written state.

2. **`_log_event()` double-commit bug.** When `db=` was passed to share a connection, `_log_event` still called `conn.commit()` — committing the shared connection mid-operation and breaking the caller's intended transaction boundary.

3. **33+ SQL queries used SQLite's `datetime('now', ...)` / `date('now')`.** On a UTC server, all time windows (daily cost totals, lesson decay, alert lookbacks, reflection context, weekly stats, monthly stats) cut off at UTC midnight instead of EST midnight. Night-time activity (midnight–5am EST) was attributed to the wrong day.

4. **4 additional UTC sites in `context/` and `cognitive_heartbeat.py`** not in the original plan scope but found during final sweep.

### Fix

**Session 0A — SqlitePool infrastructure:**
- Added `transaction()` async context manager to `SqlitePool`: acquires pooled connection, commits on clean exit, rolls back on exception, always releases.
- Added `offset_minutes` parameter to `tz.local_datetime_str()` for 30-minute window queries.
- Migrated all 17 `aiosqlite.connect()` sites in `TaskManager` to `SqlitePool`. Multi-statement writes use `pool.transaction()` for atomicity. Reads use `pool.transaction()` for consistent connection access.
- Fixed `_log_event()` to only `INSERT` (no commit) when `db=` is provided — caller's `transaction()` handles the single commit.
- Fixed `get_stuck_tasks()` timezone: `datetime('now', ? || ' minutes')` → `local_datetime_str(offset_minutes=)`.

**Session 0B — SQL timezone normalization (37 total sites across 9 files):**
- `cost/alerting.py` (1): daily cost gate → `local_date_str()`
- `status/aggregator.py` (5): today cost, 7-day window, top models, extractions today, 24h alerts → `local_date_str()` / `local_datetime_str()`
- `tools/ops_log.py` (7): all `datetime('now', ? || ' hours')` sites → `local_datetime_str(offset_hours=-hours)`
- `dream/cycle.py` (20): yesterday cost, lesson decay, identity safety check, today's observations, 24h alerts/retros/duo-metrics, routing cleanup, weekly capability gaps/failures/duo-stats/stats/errors, monthly stats/comparison windows, monthly review weekly summaries
- `dream/health_check.py` (2): stale alert auto-resolve, recent alert check
- `context/events.py` (1): 4h heartbeat event lookback
- `context/extended.py` (2): 24h task completions, today's spend
- `dream/cognitive_heartbeat.py` (1): 4h dream cycle reflection check

### Files (9 modified + 2 new in previous PR)
- `nanobot/copilot/db.py` — `transaction()` method, `asynccontextmanager`/`AsyncGenerator` imports
- `nanobot/copilot/tz.py` — `offset_minutes` param in `local_datetime_str()`
- `nanobot/copilot/tasks/manager.py` — SqlitePool migration, `_log_event()` fix
- `nanobot/copilot/cost/alerting.py` — 1 timezone site
- `nanobot/copilot/status/aggregator.py` — 5 timezone sites
- `nanobot/copilot/tools/ops_log.py` — 7 timezone sites
- `nanobot/copilot/dream/cycle.py` — 20 timezone sites
- `nanobot/copilot/dream/health_check.py` — 2 timezone sites
- `nanobot/copilot/context/events.py` — 1 timezone site
- `nanobot/copilot/context/extended.py` — 2 timezone sites
- `nanobot/copilot/dream/cognitive_heartbeat.py` — 1 timezone site

### Verification
All 386 tests pass after every commit. Zero UTC `datetime('now', ...)` patterns remain in `nanobot/copilot/`.

---

## 2026-02-21 — Status Display Accuracy (`fix/status-display-accuracy`)

### Problem
Two status display bugs:
1. **Embedding showed "local" when LM Studio was DOWN** — `_get_extraction_stats()` read `embedder._local_available` (in-memory flag that only flips on a failed embedding call). If LM Studio went down between calls, status reported stale "local" indefinitely.
2. **Heartbeat/health-check "last run" reset to "not yet" on gateway restart** — both used in-memory `last_tick_at` fields that reset to None on restart, despite both services already persisting run data to SQLite.

### Fix
- **Embedding status**: `to_text()` now cross-references `self.subsystems` (LM Studio health, already computed via `_check_lm_studio()`) before reporting "local". If LM Studio is DOWN, reports "cloud" (if cloud key exists) or "down". Zero extra network calls — uses data already in the status report.
- **Heartbeat persistence**: `_get_ops_summary()` falls back to `heartbeat_events` table (`event_type = 'heartbeat_checklist'`, written by `_log_checklist()` every tick) when `last_tick_at` is None.
- **Health check persistence**: Same pattern — falls back to `heartbeat_log` table (`run_at` column, written by `_log()` every tick) when `last_tick_at` is None.

### Files (1)
- `nanobot/copilot/status/aggregator.py` — embedding cross-check (line ~187), heartbeat DB fallback (line ~648), health check DB fallback (line ~641)

---

## 2026-02-21 — Cron Timer Resilience + Agent Loop Graceful Degradation (`fix/resilience` on `feat/navigator-duo-heartbeat-fix`)

### Problem
- Cron timer could die on an unhandled exception in `_on_timer()`, with no re-arm and no alert. All cron jobs would silently stop.
- Agent loop on max iterations returned a terse error with no alert, and kept sending tool definitions on the final iteration (wasting the LLM's last chance to produce a coherent response).
- No daily session reset — user sessions accumulated stale context indefinitely.

### Fix
- **Cron timer**: `_on_timer()` wrapped in try/finally — timer re-arms regardless of errors. Exceptions alert via AlertBus.
- **Health check cron monitoring**: New `_check_cron()` detects dead timer tasks and re-arms automatically with a high-severity alert.
- **Agent loop graceful degradation**: Final iteration sends empty `tools=[]` so the LLM produces a natural-language summary instead of attempting another tool call. Iteration exhaustion fires a medium alert.
- **Removed "Reflect" injection**: Interleaved CoT "Reflect on results" nudge removed (only "Summarize" nudge in final 3 iterations kept).
- **Daily session reset**: `_check_daily_reset()` in HealthCheckService consolidates and clears the user session once daily after an idle period.
- **`reset_session()` method**: Extracted from `/new` handler in AgentLoop for reuse by daily reset.

### Files (4)
- `nanobot/cron/service.py` — try/finally re-arm, alert on failure
- `nanobot/copilot/dream/health_check.py` — `_check_cron()`, `_check_daily_reset()`, new constructor params
- `nanobot/agent/loop.py` — empty tools on final iteration, iteration exhaustion alert, `reset_session()`

---

## 2026-02-21 — Navigator Duo + Heartbeat Fix (`feat/navigator-duo-heartbeat-fix`)

### Background Agent Context Hygiene (Phase 0)
- **Fixed dead heartbeat**: Removed early return in `CopilotHeartbeatService._tick()` that prevented the LLM from ever firing when no explicit tasks or observations existed. The guard was correct pre-sentience but wrong post-sentience — now logs "ambient tick" and proceeds to LLM call.
- **Daily heartbeat sessions**: Session key changed from static `"heartbeat"` to `f"heartbeat:{date.today().isoformat()}"` for within-day continuity with natural nightly reset.
- **Fixed shared session key contamination**: Decomposition (`task:decompose:{uuid}`) and retrospective (`task:retro:{uuid}`) now use per-call unique keys instead of shared static keys, preventing cross-task context leakage.

### Navigator Duo — Opt-in Peer Reviewer (Phases 1-7)
- **Config**: `navigator_enabled` (default: False), `navigator_model` (default: big_model), `max_duo_rounds` (3), `max_review_cycles` (3)
- **Core module** (`navigator.py`): `NavigatorVerdict` + `DuoMetrics` dataclasses, `review_plan()` (single-round), `review_execution()` (multi-round with revision loop), `parse_navigator_response()` with robust JSON parsing
- **Worker integration**: Plan review after decomposition (before execution), execution review after all steps complete, `_navigator_execution_review()` with meta-loop protection. Parse failure = escalate to user (fail safe).
- **CLI wiring**: Uses `provider.chat()` directly — no tools, no agent loop. Cost logging handled automatically by CostAwareRouter.
- **Dream cycle self-learning**: `_gather_reflection_context()` queries duo stats (7-day approval rate, avg rounds, themes). Sycophancy detection when approval rate >90% with >=3 tasks. Weekly review includes Navigator Duo Performance section.
- **Identity document** (`data/copilot/navigator.md`): Critic role, anti-sycophancy rules, review standards, JSON response format.
- **Schema migration**: `migrate_navigator()` adds `duo_metrics_json TEXT` column to `task_retrospectives`.

### Tests
- 13 navigator unit tests (parsing, serialization, plan review, execution review, metrics accumulation)
- 5 worker integration tests (plan approval/escalation, execution review, meta-loop protection, retrospective persistence)
- 247 total tests pass, 6 skipped, 0 failures

### Files (12)
- `nanobot/copilot/dream/cognitive_heartbeat.py` — gating bug fix + response logging
- `nanobot/cli/commands.py` — daily sessions, unique keys, navigator wiring, migration
- `nanobot/copilot/config.py` — navigator config fields + `resolved_navigator_model`
- `nanobot/copilot/cost/db.py` — `migrate_navigator()`
- `nanobot/copilot/tasks/navigator.py` — NEW, core navigator module
- `nanobot/copilot/tasks/worker.py` — navigator integration, meta-loop, duo_metrics
- `nanobot/copilot/tasks/prompts.py` — `build_navigator_escalation_message()`
- `nanobot/copilot/dream/cycle.py` — duo stats, sycophancy detection, weekly navigator section
- `data/copilot/navigator.md` — NEW, navigator identity
- `tests/copilot/tasks/test_navigator.py` — NEW, 13 unit tests
- `tests/copilot/tasks/test_worker.py` — 5 new integration tests
- `.gitignore` — `.claude/.session-locks/`

---

## 2026-02-21 — Routing Visibility & Bug Fixes (`fix/routing-visibility`)

### Testing & Code Quality (Commit 2)
- **Tests now version-controlled**: Removed `tests/` from `.gitignore` — test changes are reviewable in PRs and tracked in git history
- **Shared routing test fixtures**: Created `tests/copilot/routing/helpers.py` with provider-agnostic utilities: `make_router()` (configurable cloud_names), `all_cloud_fail()` (fails all providers regardless of count), `patch_native()` (mocks `find_by_model()` for controlling native provider preference)
- **Refactored routing tests**: All 3 test files import from shared helpers. Removed hardcoded provider counts (`== 4` → `== len(router._cloud)`), removed dict-order assumptions (explicit `patch_native("minimax")` instead of relying on registry), removed per-provider `cloud_succeed` dicts for "all fail" tests
- **Fixed ruff violations**: Resolved ~50 pre-existing linting errors across all test files (import sorting, unused imports/variables, N806 naming)
- **368 tests pass**, 6 skipped, ruff clean

### Changed
- **Router native provider preference**: `_build_chain()` now puts the native provider first for both default and escalation paths using `registry.find_by_model()`. MiniMax-M2.5 now routes to `minimax` directly instead of going through Venice gateway.
- **Per-provider circuit breaker alerts**: Alert dedup keys are now `provider_failed:{name}` instead of shared `provider_failed`. Each provider gets its own alert lifecycle.
- **Auto-resolve on recovery**: When a circuit breaker closes after recovery, the provider's alert is automatically resolved via new `AlertBus.resolve()` method.
- **Guard against re-alerting**: Circuit breaker only fires alert on first opening, not when re-entering open from half-open probe failure with threshold already met.
- **Provider alerts hidden from LLMs**: Health check's `_check_unresolved_alerts()` now excludes `provider_failed%` alerts from heartbeat_events. Provider outages are infrastructure, not LLM concerns.
- **Extraction JSON parser hardened**: `_parse_json()` now finds JSON object boundaries (`{...}`) to handle preamble text that Haiku sometimes adds before JSON.
- **Cloud extraction source tracking**: `extract_cloud()` now sets `_last_source = "cloud"` for accurate /status display.
- **Extraction status terminology**: Renamed "heuristic" to "fallback" for clarity.
- **/status winning provider**: Auto mode now shows `_last_winning_provider` (stripped of plan:/safety: prefixes) instead of first cloud dict key.

### Files Modified (6)
- `nanobot/copilot/routing/router.py` — native provider preference in `_build_chain()`
- `nanobot/copilot/routing/failover.py` — per-provider alerts, auto-resolve, re-alert guard
- `nanobot/copilot/alerting/bus.py` — `resolve()` method
- `nanobot/copilot/dream/health_check.py` — exclude provider_failed from LLM view
- `nanobot/copilot/extraction/background.py` — JSON parser, cloud source, fallback rename
- `nanobot/copilot/status/aggregator.py` — winning provider display

---

## 2026-02-20 — Background Service Job Checklists (feat/background-service-checklists)

### Problem
Background services produced opaque output — the dream cycle ran 13 jobs but the report only showed aggregate counters. Jobs 8-13 produced zero signal on success. "Quiet night. All systems healthy." fired when all counters were zero, which was ambiguous (everything ran fine vs everything was silently skipped). The heartbeat, weekly review, and monthly review had similar gaps — no confirmation that all context-gathering steps and LLM calls actually executed.

### Fix
**Dream cycle**: Added `JobResult` dataclass tracking per-job name, status (`ok`/`skipped`/`error`), duration, and detail. Added `_run_job()` helper that wraps all 13 jobs with timing and exception capture. Guard clauses in job methods now return `{"_skipped": True, "reason": "..."}` sentinel instead of silently returning zero. `to_summary()` renders a `[+]/[~]/[!]` checklist. Results persisted to `dream_cycle_log.job_results_json`.

**Cognitive heartbeat**: After each tick, logs a `heartbeat_checklist` event to `heartbeat_events` recording inputs gathered (observations, tasks, permissions, lessons, morning brief) and LLM execution status.

**Weekly/monthly reviews**: Both build a data-gathering checklist that is prepended to the delivered summary, confirming which data sources were loaded, LLM call status, and report persistence.

### Files
- `nanobot/copilot/dream/cycle.py` — `JobResult`, `_run_job()`, refactored `run()`, updated guard clauses, weekly/monthly checklists
- `nanobot/copilot/dream/cognitive_heartbeat.py` — `_log_checklist()`, checklist tracking in `_tick()`
- `nanobot/copilot/cost/db.py` — Migration: `job_results_json` column on `dream_cycle_log`

---

## 2026-02-20 — Background Context Isolation (fix/background-context-isolation)

### Problem
All background services (heartbeat, dream cycle, weekly/monthly reviews, cron, task retrospectives) used the same `process_direct()` → `_process_message()` pipeline as interactive user chat. This caused: (1) proactive episodic recall injecting user conversation memories into background prompts (heartbeat continued a philosophical discussion instead of doing its job), (2) `get_unacknowledged_events()` consuming events before users saw them, (3) `mark_applied()` on lessons corrupting metacognition data, (4) `remember_exchange()` storing background conversations as episodic memories that could surface in future user recalls (reverse contamination).

### Fix
Added `skip_enrichment: bool = False` parameter to `process_direct()` and `_process_message()`. When True, skips: lesson retrieval/marking, proactive episodic recall, event injection/acknowledgment, post-response extraction, post-response memory storage, and satisfaction detection. **Core facts and identity files still load** — background services keep their identity grounding.

Six call sites updated to `skip_enrichment=True`: heartbeat, dream, weekly review, monthly review, cron, task retrospective. Two callers deliberately kept on full enrichment: task `_execute_step` and `_decompose_task` (user-facing task execution benefits from context).

Additionally, `CopilotHeartbeatService` now queries active lessons directly via `_get_active_lessons()` (read-only, no `mark_applied` side effect) and injects them into its cognitive prompt. This gives the heartbeat deliberate, targeted access to hard-won rules without the contamination of the generic injection pipeline.

### Files
- `nanobot/agent/loop.py` — `skip_enrichment` param + 6 guard points
- `nanobot/cli/commands.py` — 6 background service call sites
- `nanobot/copilot/dream/cognitive_heartbeat.py` — `_get_active_lessons()` + prompt injection

---

## 2026-02-20 — Sentience Plan (feat/sentience-phase-1)

### Closed Feedback Loops
Four open feedback loops closed: dream cycle produces structured observations (not just prose), heartbeat becomes cognitive inner monologue, task failures produce diagnoses, identity files can evolve based on learnings.

### Dream Cycle — Structured Observations
- **`_self_reflect()` rewritten**: JSON output with `capability_gaps`, `patterns_noticed`, `failure_diagnoses`, `evolution_suggestions`. Parsed → `dream_observations` table. `reflection_full` stored in `dream_cycle_log`.
- **SQL bug fixes (3)**: `episodes_content` → `episodic_fts_content` in 3 queries. `unixepoch()` → parameterized `time.time() - 86400`.
- **Job 11 — Identity Evolution**: Reads `autonomy_permissions.identity_evolution`. `notify` → surfaces proposals via heartbeat. `autonomous` → applies top proposal, logs diff to `evolution_log`. Velocity limit: 1 file/cycle, 30-min user-activity check.
- **Job 12 — Observation Cleanup**: Expires unacted observations >14 days (`acted_on=-1`), deletes acted observations >90 days.
- **`is_running` flag**: Set True at `run()` start, False at end — checked by cognitive heartbeat to skip concurrent ticks.
- **`run_weekly()` expanded**: Capability gap synthesis, failure pattern analysis, roadmap proposals, evolution proposals. Full report in `weekly_review_log`. Brief summary to WhatsApp.
- Files: `nanobot/copilot/dream/cycle.py`

### Cognitive Heartbeat (Phase 2)
- **`CopilotHeartbeatService`** (NEW): Subclass of upstream `HeartbeatService`. Overrides `_tick()` to inject dream observations, pending tasks, autonomy permissions, morning brief. Upstream untouched (FM2: survives merges).
- **Context**: Queries `dream_observations WHERE acted_on=0 LIMIT 10`, `task_manager.list_pending()`, `autonomy_permissions`, first-post-dream morning brief from `dream_cycle_log.reflection_full`.
- **Output**: Parses JSON from LLM response → writes to `dream_observations` and `heartbeat_events`. Alerts on failure.
- **Backward compat**: Empty HEARTBEAT.md + no observations → silent tick. HEARTBEAT.md tasks still execute (additive only).
- Files: `nanobot/copilot/dream/cognitive_heartbeat.py` (NEW), `nanobot/cli/commands.py`, `data/copilot/heartbeat.md`

### Task Retrospectives (Phase 3)
- **`TaskWorker` retrospective**: Post-task LLM analysis on failures (always) and non-trivial completions (>1 step). JSON diagnosis stored in `task_retrospectives`, embedded in Qdrant with `role="retrospective"`.
- **Past wisdom injection**: Before task decomposition, queries Qdrant for similar retrospectives (`role_filter="retrospective"`). Injects "Execution Wisdom" section into decomposition prompt.
- **`recall()` role_filter param**: New `role_filter` parameter in `EpisodicStore.recall()` for Qdrant payload filtering.
- **Diagnostic pattern in identity files**: SOUL.md principle #8 ("Diagnose, don't complain"), AGENTS.md Failure Diagnostic Pattern (4-step: root cause → what I tried → proposed fix → capability gap).
- Files: `nanobot/copilot/tasks/worker.py`, `nanobot/copilot/tasks/prompts.py`, `nanobot/copilot/memory/episodic.py`, `workspace/SOUL.md`, `workspace/AGENTS.md`

### Infrastructure (Phase 1)
- **`migrate_sentience()`**: 5 new tables (`dream_observations`, `autonomy_permissions`, `task_retrospectives`, `weekly_review_log`, `evolution_log`) + ALTER TABLE `dream_cycle_log` ADD COLUMN `reflection_full`. Idempotent migration.
- **`SetPreferenceTool` autonomy handling**: `autonomy:` prefix routes to `autonomy_permissions` table update.
- **`TaskManager.list_pending()`**: New method returning string summaries of pending/active/awaiting tasks.
- **`_parse_llm_json()`**: Shared helper with 4-level fallback (direct → markdown fence → regex → trailing comma cleanup). Parse failures stored as `observation_type='parse_failure'`, AlertBus notified.
- Files: `nanobot/copilot/cost/db.py`, `nanobot/copilot/tools/preferences.py`, `nanobot/copilot/tasks/manager.py`

### Slash Commands (Phase 4)
- **`/dream`**: Triggers dream cycle via `asyncio.create_task` (fire-and-forget). Returns immediate acknowledgment.
- **`/review`**: Triggers weekly review via `asyncio.create_task` (fire-and-forget).
- **`_dream_cycle` attribute**: Added to `AgentLoop` for command wiring.
- Files: `nanobot/agent/loop.py`

### New Tables (5 + 1 ALTER)
`dream_observations`, `autonomy_permissions`, `task_retrospectives`, `weekly_review_log`, `evolution_log`, `dream_cycle_log.reflection_full`

---

## 2026-02-20 — Router V2 Overhaul

### Router
- **Plan-based routing**: Heuristic 11-rule `classify()` deleted. Routing now follows LLM-generated, user-approved plans via `PlanRoutingTool`
- **Mandatory safety net**: Every chain gets last-known-working + LM Studio + emergency fallback
- **PlanRoutingTool**: New tool for propose/validate/activate routing plans with API pre-flight probes
- **`router.md`**: New routing planner ground truth file (provider table, free tier info, constraints)
- **Self-escalation**: Now uses dedicated `escalation_model` instead of `big_model`
- **Recovery probing**: Background loop probes failed providers every 30s when in failover mode
- **Config cleared**: `agents.defaults.model` cleared (was phi-4-mini-reasoning causing 27-provider cascades)
- **maxTokens**: Response limit bumped 2048 → 8192

### Memory
- **Pollution guard**: `schedule_extraction()` and `remember_exchange()` now guarded by `not is_error`
- **Cleanup script**: `scripts/cleanup_memory.py` for one-time Qdrant/SQLite error cleanup

### Health & Monitoring
- **HealthMonitorService → HealthCheckService**: Renamed, moved to `health_check.py`, LLM call removed
- **Config**: `heartbeat_interval` → `health_check_interval`
- **Prompts**: WhatsApp constraints removed from dream reflection, weekly, monthly prompts
- **HEARTBEAT.md interval**: Fixed "30 minutes" → "2 hours" in docs
- **SLM queue**: `alert_abandoned()` method for items stuck at max_attempts

### Cost & Context
- **Gemini Flash**: Added `gemini-3-flash-preview` to pricing ($0.00) and context window (1M)
- **Model aliases**: Expanded in `use_model.py` (claude, o1, o3, minimax, m25, kimi, llama, glm)

---

## [Memory Architecture Redesign] — 2026-02-19

### Removed — Redis
- Deleted `working.py` (154 lines), removed from manager.py, config.py, commands.py, aggregator.py, heartbeat.py, pyproject.toml
- Redis provided near-zero value: 3/5 methods had zero callers, recall cache had correctness bug (keyed to session not query)
- System already gracefully degraded when Redis was down

### Fixed — `memory store` → `memory search` Disconnection (Critical Bug)
- `memory store` only wrote to SQLite `memory_items`; `memory search` queried Qdrant+FTS5. Stored items were unsearchable.
- New `store_fact()` method writes to ALL THREE backends (SQLite + Qdrant + FTS5)

### Fixed — Qdrant Collection Name Mismatch (Bug)
- `_reconcile_memory_stores` and `_cleanup_zero_vectors` used hardcoded `"episodes"` but `EpisodicStore.COLLECTION = "episodic_memory"`
- Both dream jobs silently no-oped every night. Now uses `EpisodicStore.COLLECTION` constant.

### Added — Core Facts Injection
- `get_core_facts_block()` auto-injects high-confidence (≥0.8) items from SQLite into system prompt
- Runs concurrently with proactive recall via `asyncio.gather`
- Extended context builder accepts new `core_facts` parameter

### Changed — HISTORY.md → FTS5+Qdrant (Copilot Mode)
- Consolidation now stores summaries via `store_fact()` (all backends) instead of flat file append
- Non-copilot fallback preserved (still writes to HISTORY.md)
- Removed `_prune_history` dream job (no longer needed in copilot mode)

### Changed — SKILL.md Memory
- Dropped `always: true` → `always: false` (~155 tokens/prompt saved)
- Rewritten as reference doc for tool syntax, not operational instructions

### Changed — MEMORY.md Budget
- Lowered default from 400 → 150 tokens. MEMORY.md is a lean scratchpad only.

### Changed — Onboarding Prompt
- Step 4: clarified MEMORY.md is lean scratchpad (~150 tokens), not fact store
- Step 5: changed from "append to HISTORY.md" → "store via memory tool"

### Updated — Documentation
- AGENTS.md: updated memory section, removed Redis from infra
- heartbeat.md: removed Redis health check, updated dream job list
- capabilities.md: marked deprecated
- context.py: updated identity section (removed HISTORY.md reference)

---

## [Dream Cycle & Routing Fixes] — 2026-02-19

### Fixed — Routing Cost Escalation (big_model defaulted to Opus)
- **Root cause**: `CopilotConfig.big_model` defaulted to `anthropic/claude-opus-4.6`. Every routing "big" decision (images, code blocks, complexity patterns) and every failover cascade hit Opus at $5/$25 per MTok.
- **Fix**: Default changed to `anthropic/claude-sonnet-4-6`. Opus available via explicit `weekly_model` config or `/use`.
- **File**: `nanobot/copilot/config.py:71`

### Fixed — LM Studio Noise in Recurring Cycles
- **Root cause**: LM Studio (optional local GPU) generated alerts via 4 separate paths: failover circuit breaker → AlertBus, dream cycle Job 5 (health check), dream cycle Job 11 (reflection DB query), health monitor (unresolved alerts query). MonitorService already silenced it, but dream/heartbeat/failover did not.
- **Fix**: Suppressed `_fire_alert` for lm_studio in failover chain. Filtered "LM Studio" from dream cycle subsystem alerts. Added `NOT LIKE '%lm_studio%'` to reflection context and health monitor DB queries.
- **Files**: `failover.py`, `cycle.py`, `heartbeat.py`

### Fixed — Dream Reflection Truncated at 200 Characters
- **Fix**: Increased truncation limit from 200 to 1000 characters. WhatsApp supports ~4096.
- **File**: `nanobot/copilot/dream/cycle.py`

### Fixed — CopilotHeartbeatService → HealthMonitorService Rename
- **Root cause**: Class was renamed in commands.py import but not in the class definition (heartbeat.py). Would cause ImportError at gateway startup.
- **Fix**: Renamed class + updated docstring and log messages to match.
- **File**: `nanobot/copilot/dream/heartbeat.py`

---

## [Routing & Identity Bug Fixes] — 2026-02-19

### Fixed — Model Identity Confusion (bot says wrong model name)
- **Root cause**: `session.metadata["last_model_used"]` recorded `self.model` (always the static local model default) instead of the actual model used by the router. Every LLM turn was tagged as local regardless of routing.
- **Fix**: Now uses `response.model_used` from the LLM response (set by the failover chain to the winning provider's model).
- **File**: `nanobot/agent/loop.py:859`

### Added — Model Identity Injection into System Prompt
- **Root cause**: The system prompt never told the LLM what model powers it. When asked "what LLM are you?", every model hallucinated an answer (e.g., "Llama 3.3 70B" regardless of actual model).
- **Fix**: `ExtendedContextBuilder.build_messages()` now injects a `## Current Model` section with the last model used from session metadata, plus instruction to report it accurately.
- **File**: `nanobot/copilot/context/extended.py`
- **Note**: First message of a new session won't have this (no prior model recorded). Subsequent messages will be accurate.

### Fixed — Stale EMERGENCY FALLBACK Status Display
- **Root cause**: `/status` shows EMERGENCY FALLBACK based on `_last_winning_provider` from the most recent LLM call. If that call went through emergency but providers later recovered (and no new LLM calls came in), status showed emergency indefinitely. `/status` is programmatic (no LLM call), so it couldn't update the routing state.
- **Fix**: `_build_routing_state()` now checks if emergency state is stale by examining circuit breaker states. If any primary cloud provider's circuit is no longer open (closed or half-open after cooldown), the emergency state is downgraded to "auto (recovered from emergency fallback)".
- **File**: `nanobot/copilot/status/aggregator.py`

### Fixed — Race Condition in `process_direct()` (model contamination)
- **Root cause**: `process_direct()` temporarily mutated `self.model` on the shared `AgentLoop` instance. When concurrent callers (heartbeat, dream cycle, user message) overlapped, the `finally` block could restore the wrong value, leaving `self.model` permanently set to a wrong model (e.g., `microsoft/phi-4-mini-reasoning`). All subsequent user messages then went through the `model_override` path with this wrong model, causing cascading failures.
- **Fix**: Replaced shared mutable state with `contextvars.ContextVar` (`_model_override`, `_reasoning_override`). Each coroutine now has its own override that cannot contaminate other concurrent calls.
- **File**: `nanobot/agent/loop.py`

### Fixed — Routing Preference Logger Crash
- **Root cause**: `logger.info(f"Routing preference matched: {best['provider']}")` at `router.py:575` ran outside the `if best:` block. When no preference matched (`best=None`), it crashed with `TypeError: 'NoneType' object is not subscriptable`. The exception was caught but generated noisy warning logs.
- **Fix**: Moved the `logger.info` inside the `if best:` block.
- **File**: `nanobot/copilot/routing/router.py:575`

---

## [Review Cycle Jurisdiction Redesign] — 2026-02-19

### Redesigned — Worker → Manager → Director Pipeline
- **Dream cycle (Worker)**: Self-reflection narrowed to operational scope only (what broke, what needs attention, data quality). Removed strategic questions. Added memory health data to reflection context.
- **Weekly review (Manager)**: Now oversees dream cycle health, reads monthly findings, owns architecture/code changes (suggests to user first), trims over-budget files, sets strategic direction. No longer adjusts budget policy.
- **Monthly review (Director)**: Now reviews weekly reports, is the ONLY cycle that adjusts budgets.json, audits architecture (writes findings for weekly, doesn't fix), includes self-reflection, uses 30-day cost stats.
- Monthly writes `monthly_review_findings.json` → weekly reads, implements, clears.

### Added — New Data Helpers
- `_get_dream_errors()`: Summarizes dream cycle health for weekly oversight (7-day error log)
- `_get_monthly_stats()`: 30-day cost stats with week-by-week breakdown (replaces reuse of 7-day `_get_weekly_stats`)

### Changed — Model Tier Assignments
- Weekly review: `anthropic/claude-opus-4-6` (quality priority, cost=lowest concern)
- Monthly review: `moonshotai/kimi-k2.5` (strong + 2M context for broad audit scope)
- Dream cycle: unchanged (`gemini-3-flash-preview`, free tier)

### Changed — Monthly cron to 10 AM EST
- `monthly_review_cron_expr` default: `"0 14 1 * *"` → `"0 15 1 * *"` (10 AM EST)

### Merged — CAPABILITIES.md → AGENTS.md
- Eliminated redundant file; all identity content now in 4 bootstrap files (SOUL, USER, AGENTS, POLICY)
- Updated `ContextBuilder.BOOTSTRAP_FILES` to remove CAPABILITIES.md
- AGENTS.md cycle table updated with Worker/Manager/Director roles

### Fixed — 10 stale test failures
- Budget test: updated default window expectation (8192→128000)
- Policy loading tests: rewrote for BOOTSTRAP_FILES (removed references to deleted `_load_identity_docs`)
- Alert bus tests: aligned with actual contract (only HIGH delivers)
- Message UX tests: removed tests for unimplemented `peek_inbound`

Files: `nanobot/copilot/dream/cycle.py`, `nanobot/copilot/config.py`, `nanobot/agent/context.py`, `nanobot/cli/commands.py`, `~/.nanobot/config.json`, `~/.nanobot/workspace/AGENTS.md`, `~/.nanobot/workspace/budgets.json`, tests

---

## [Service Untangling & Status Display Fixes] — 2026-02-19

### Refactored — Heartbeat / Health Monitor Separation
- Renamed `CopilotHeartbeatService` → `HealthMonitorService` — eliminates confusion with the real LLM HeartbeatService
- Removed `execute_fn` from HealthMonitorService — it is now purely programmatic (Qdrant, Redis, alerts, stuck detection)
- Wired `task_manager` and `subagent_manager` to HealthMonitorService — stuck subagent cancel and stuck task fail now actually fire
- Moved LLM task review from HealthMonitorService → HeartbeatService, using `list_tasks(status="pending")` (fixed from nonexistent `list_pending()`)
- Both services write startup events to DB for `/status` visibility
- Files: `nanobot/copilot/dream/heartbeat.py`, `nanobot/heartbeat/service.py`, `nanobot/cli/commands.py`

### Added — Per-Service Model Config
- Added `weekly_model`, `monthly_model` config fields (default to `dream_model`)
- Updated `resolved_heartbeat_model` to default to `dream_model` instead of empty (router heuristics)
- Added `weekly_execute_fn`, `monthly_execute_fn` to DreamCycle — weekly/monthly reviews use their own models
- HeartbeatService now passes explicit `model=resolved_heartbeat_model`
- Only nanobot user chat should go through the router heuristics; all background services use explicit models
- Files: `nanobot/copilot/config.py`, `nanobot/copilot/dream/cycle.py`, `nanobot/cli/commands.py`, `nanobot/copilot/tools/preferences.py`

### Fixed — Status Display Bugs
- **Routing tier mismatch**: `routing_log` now stores actual tier (from winning model) not heuristic intent. DB read path also applies tier correction.
- **Cost today $0.00**: Cost queries now apply timezone offset — "today" means local day, not UTC day
- **Cron display wrong times**: Cron expressions (UTC) now correctly converted to local time for display
- **Extraction labels opaque**: Shows method (local/cloud/down) + failure count instead of "none"
- **Heartbeat status**: Shows separate lines for LLM Heartbeat (2h) and Health Monitor (30m) with alive/dead state
- Files: `nanobot/copilot/routing/router.py`, `nanobot/copilot/status/aggregator.py`

### Added — V2 Plan: Orchestrator Monitoring (Pre-2.2 Task J / 5.14)
- Recovery after kills, per-subagent cost tracking, loop detection, task cancellation semantics, kill notifications
- File: `2026-02-16-v2.1-brain-architecture-plan.md`

---

## [Routing & Status Fixes] — 2026-02-19

### Fixed — Opus Cost Bleed on Dream Cycle
- `RouterProvider.chat()` now honors the `model` parameter instead of silently ignoring it
- New `_build_chain_for_override()` method: tries provider-matched first (e.g. gemini for gemini models), degrades to fast (cheap), never touches Opus
- Dream model changed from invalid `google/gemini-3-thinking` to `gemini-3-flash-preview` (Gemini 3 Flash with thinking, free on Google AI Studio)
- Files: `nanobot/copilot/routing/router.py`, `nanobot/copilot/config.py`

### Fixed — Gemini Thinking Not Enabled
- Added `include_reasoning: true` model_override for `gemini-3-flash` in both gemini and openrouter ProviderSpecs
- Uses existing `_apply_model_overrides()` mechanism — no interface changes
- File: `nanobot/providers/registry.py`

### Fixed — 4096-char Overflow Routing Rule
- Removed the `len(message_text) > 4096 → big` heuristic rule — conflated "long input" with "hard problem"
- All cloud models have 128k+ context; failover handles actual overflow
- Files: `nanobot/copilot/routing/heuristics.py`, `tests/copilot/routing/test_heuristics.py`

### Added — Model Registry
- New `data/copilot/model_registry.json`: machine-readable registry of validated model IDs, tier assignments, costs, and free tier info
- Companion to `models.md` (LLM-readable). Weekly review maintains both.

### Added — Timezone Configuration
- New `timezone` field in `CopilotConfig` (default: `America/New_York`)
- `_format_ago()` in aggregator now compares against UTC correctly
- File: `nanobot/copilot/config.py`, `nanobot/copilot/status/aggregator.py`

### Fixed — CostAlerter Was Dead Code
- `CostAlerter` (already constructed) now wired: per-call alerts via router, daily threshold via CopilotHeartbeatService tick
- Fires HIGH alerts when `per_call_cost_alert` ($0.50) or `daily_cost_alert` ($50) exceeded
- Files: `nanobot/copilot/routing/router.py`, `nanobot/copilot/dream/heartbeat.py`, `nanobot/cli/commands.py`

### Fixed — Status Display Issues
- **Extraction count**: now queries `slm_work_queue` (actual data) instead of counting haiku calls in cost_log
- **Heartbeat persistence**: ticks written to `heartbeat_events` table (survives restarts)
- **Cron schedules**: dream cycle, weekly review, heartbeat interval shown with timezone
- **Routing display**: shows actual winning model/tier, not heuristic intent
- **Alert 24h count**: excludes resolved alerts, shows resolved count for context
- **Embedding health**: cross-references with LM Studio health check
- Files: `nanobot/copilot/status/aggregator.py`, `nanobot/heartbeat/service.py`, `nanobot/cli/commands.py`

### Fixed — Structured Items Still 0 Despite Extractions
- **Root cause 1**: `get_high_confidence_items()` threshold was 0.6 but items start at 0.5. Items need duplicate key match (same `category+key[:100]`) to boost to 0.6 — rarely happens with 19 extraction items.
- **Root cause 2**: All 5 queued cloud extractions failed with "unparseable JSON" — LLM wraps response in preamble text before the JSON.
- **Fix 1**: Lowered `min_confidence` from 0.6 to 0.4 — shows items on first appearance (36 items now visible)
- **Fix 2**: `_parse_json()` now falls back to finding first `{` to last `}` in response text when full-text parse fails
- Files: `nanobot/copilot/memory/manager.py`, `nanobot/copilot/extraction/background.py`

---

## [Post-V1 Enhancements] — 2026-02-17

### Added — Operational Self-Awareness (ops_log tool + /status ops + heartbeat injection)
The bot identified itself as "blind to its own background processes." Three changes fix this:

1. **`ops_log` LLM tool** — The bot can now query its own operational history on demand. Supports 4 categories: `dream` (cycle runs, errors), `heartbeat` (runs, events), `alerts` (deduplicated by error_key), `cost` (by model, by day). Configurable lookback window (default 24h, max 168h).
   - File: `nanobot/copilot/tools/ops_log.py` (NEW)
   - Registered in `nanobot/cli/commands.py`

2. **Enhanced `/status` — "Last Operations" section** — Shows last dream cycle timestamp + error count, last heartbeat timestamp, and alert counts (high/medium) for the last 24h. Always visible in `/status` output.
   - File: `nanobot/copilot/status/aggregator.py` — added `ops_summary` field to `DashboardReport`, `_get_ops_summary()` method, `_format_ago()` helper

3. **Always-on heartbeat context injection** — Every message now includes a ~20-token heartbeat summary in the system prompt: "Last heartbeat: 45m ago, all healthy" or "Last heartbeat: 2h ago — [high] Redis unreachable". Separate from the fire-and-forget detailed event injection.
   - File: `nanobot/copilot/context/events.py` — added `get_heartbeat_summary()`, `_format_ago_short()`
   - File: `nanobot/agent/loop.py` — wired into event injection block (~line 670)

### Fixed — Embedder Crash on Dual Failure
- `Embedder.embed()` and `embed_batch()` now return zero-vectors instead of raising `RuntimeError` when both local and cloud embedding fail
- Previously crashed the entire memorization chain; now stores zero-vectors that get re-embedded when LM Studio comes back
- File: `nanobot/copilot/memory/embedder.py`

### Fixed — Embedding Failures Not Queued
- `MemoryManager` now enqueues embedding work into the SLM queue when local embedding is unavailable
- Both `remember_exchange()` and `remember_extractions()` queue items for re-embedding
- Previously, embedding failures silently lost data
- Files: `nanobot/copilot/memory/manager.py`, `nanobot/cli/commands.py`

### Fixed — /use Override Circular Re-Activation
- Override expiry was storing a routing preference, which immediately got matched by the routing preference check, re-activating the override in an infinite cycle
- Removed `_store_routing_preference()` call from expiry handler, added `_clear_routing_preferences()` to clean stale DB entries
- File: `nanobot/agent/loop.py`

### Added — /help Command
- Adaptive `/help` with topic drill-down and dynamic tips
- Topics loaded from `data/copilot/help.md`
- Shows current routing mode and available capabilities
- File: `nanobot/agent/loop.py` — `_build_help_response()`, `_load_help_section()`, `_list_help_topics()`, `_generate_tips()`
- File: `data/copilot/help.md` (NEW)

---

## [Post-V1 Enhancements] — 2026-02-16

### Fixed — Memory Leak Fixes (Critical)
Three unbounded data structure growth patterns eliminated:

1. **SessionManager cache eviction**: `_cache` now uses `OrderedDict` with LRU eviction at `_max_cache_size=256`. Eviction happens in both `get_or_create()` and `save()` to prevent unbounded growth with many unique sessions. Previously, the dict grew indefinitely with one entry per unique session ID.
   - File: `nanobot/session/manager.py`

2. **Extractions list cap**: Session metadata extractions list now capped at last 1000 entries via `session.metadata["extractions"] = extractions[-1000:]` in message processing loop. Prevents long-lived sessions from accumulating one entry per message indefinitely.
   - File: `nanobot/cli/commands.py:544`

3. **AlertBus deduplication pruning**: Every 100 alerts, `_last_sent` dict prunes expired dedup keys (entries older than cooldown window). Prevents unbounded growth from unique `(subsystem, error_key)` pairs over long runtimes.
   - File: `nanobot/copilot/alerting/bus.py`

### Changed — CoT Reflection Decay
- Last 3 reflection iterations now use "Summarize" prompt instead of "Reflect" to prevent infinite tool loops
- Prevents recursive self-analysis when reflection tools trigger additional reflections
- File: `nanobot/agent/loop.py`

### Changed — Graceful Shutdown
- `AgentLoop.stop()` now async, awaits cancellation of tracked background tasks
- Ensures clean shutdown without orphaned tasks or partial writes
- File: `nanobot/agent/loop.py`

### Changed — WhatsApp Reconnection Backoff
- Exponential backoff with jitter: `5 * 2^n` seconds, capped at 120s
- Prevents aggressive reconnection storms when bridge or network is unstable
- File: `bridge/src/whatsapp.ts`

### Changed — MEMORY.md Slim-Down (Token Budget Enforcement)
- Trimmed MEMORY.md from ~1200 tokens to ~311 tokens — behavioral core only
- Moved goals, action plan, life situation, and development principles to Qdrant episodic memory (4 entries, `session_key="system:core_memory"`, `role="preference"`)
- Added "Deep Context" reference line telling the LLM to use `recall_messages` for detailed context
- Added dream cycle Job 9: `_check_memory_budget()` — reads MEMORY.md, estimates tokens, logs `heartbeat_events` warning if over 400 token budget
- Saves ~800-900 tokens per message across all conversations
- Files changed: `~/.nanobot/workspace/memory/MEMORY.md`, `nanobot/copilot/dream/cycle.py`

### Added — V2 Success Criteria
- Added "What Successful Implementation Looks Like" section to V2 Architecture doc
- 6 concrete success criteria: retrieval gap (V2.3), bad memory correction (V2.2+V2.3), prioritization framework (V2.1), autonomy calibration (V2.3), memory budget enforcement (ongoing), model tier metacognition observation

---

## [Post-V1 Enhancements] — 2026-02-15

### Fixed — /use Override Never Reverting (Bug)
- `touch_activity()` was called before the timeout check, resetting elapsed time to ~0 every message
- Moved timeout check before `touch_activity()` for both `/use` and private mode
- Changed default timeout from 30min to 60min
- Conversation continuity already works: when override expires, routing preferences auto-restore the provider for same-topic follow-ups

### Fixed — Context Continuity Bugs
- Proactive recall: wrapped in `asyncio.wait_for(timeout=2.0)` to prevent hangs when Qdrant/embedder is slow
- Orientation hint: changed `len(real_history) < 6` to `0 < len(real_history) < 6` — no longer fires on brand-new conversations
- Proactive recall budget: reduced from 800 to 200 tokens — appropriate for a nudge, tool handles detailed retrieval

### Fixed — Cost Tracking Accuracy
- Added missing model aliases to `_PRICING` dict (claude-haiku-4.5, claude-opus-4.6, claude-sonnet-4.5, qwen2.5-14b-instruct)
- Added litellm `cost_per_token()` fallback for models not in local pricing table
- Backfilled 126 historical zero-cost rows ($11.34 total was invisible)

### Added — Error Visibility in /status
- `/status` now shows "Alerts (24h)" section with timestamped errors/warnings, deduplicated by error_key with occurrence counts
- Shows "No errors or warnings" when clean
- Wired 5 agent loop error sites to AlertBus: message processing errors, background task failures, turn timeouts, LLM timeouts
- Wired 2 channel manager crash sites to AlertBus: channel crashes, max restart exceeded

### Added — Session & Token Context in /status
- Shows current session token usage as percentage of context window (e.g., "12,450 / 200,000 tokens (6%)")
- Shows active sessions (last 1h) and total session count
- SLM Queue: shows "Not connected" when not wired, "Empty (local SLM handling extractions directly)" when connected but idle
- Uses existing `TokenBudget` class for on-demand computation (cheap, cached tiktoken)

### Changed — Extraction: Local SLM Only (No Haiku Fallback)
- Removed Haiku cloud fallback from background extraction — extraction is non-urgent background work
- Flow is now: local SLM → queue for deferred processing → heuristic regex (immediate low-quality results)
- SLM queue drainer processes deferred items when LM Studio comes back online
- Saves ~$0.001/extraction (84 Haiku calls were visible in cost_log from background extraction alone)

---

## [Post-V1 Enhancements] — 2026-02-14

### Added — `/use` Overhaul + Runtime Preferences
- `/model` command (alias for `/use`) with tier and explicit model support
  - `/use openrouter fast` → routes to fast_model via OpenRouter
  - `/use venice gpt-4o` → routes to specific model via Venice
  - `/use auto` → return to automatic routing
- 30-minute auto-expiry for `/use` overrides (configurable via `use_override_timeout`)
- Routing preferences: keyword-based conversation continuity after `/use` timeout
  - Stores top 10 keywords from recent messages, auto-restores override when resuming topic
  - Max 20 preferences per session, 7-day expiry, SQLite-backed
- `SetPreferenceTool` — natural language config changes via LLM
  - "set my fast model to gpt-4o-mini" → immediate effect + persistence
  - "run the dream cycle at 5am" → reschedules cron on the fly
  - Supports: model tiers, dream cron, heartbeat interval, cost alerts, context budget, lesson params

### Added — Secrets Separation
- Split `~/.nanobot/config.json` into config.json (preferences) + secrets.json (API keys)
- `secrets.json` created with mode 0o600 (owner read/write only)
- Auto-migration on first load: extracts API keys from legacy config.json
- Deep merge on load: secrets override empty config values
- Cloud models and tools can no longer read API keys from config file

### Added — Dream Cycle Always Delivers
- Dream cycle now ALWAYS sends a message to user after completion
- "Quiet night" message when nothing notable to report
- New self-reflection job: LLM reviews 24h activity and suggests improvements
- Reflection summary included in dream report

### Fixed — Catch-22 Patterns
- Negative satisfaction now penalizes active lessons (was creating lessons but never penalizing)
- `lesson_injection_count` and `lesson_min_confidence` config fields now consumed (were hardcoded)
- Startup warnings when `monitor_chat_id` or `approval_chat_id` are empty (alerts were failing silently)

### Changed
- `nanobot/config/loader.py` — secrets split (~60 lines)
- `nanobot/session/manager.py` — +use override helpers (~20 lines)
- `nanobot/copilot/routing/router.py` — +timeout, +tier routing, +set_model, +routing preference check (~70 lines)
- `nanobot/agent/loop.py` — /use+/model handler, timeout, preferences, config passthrough (~75 lines)
- `nanobot/copilot/config.py` — +use_override_timeout field (~2 lines)
- `nanobot/copilot/tools/preferences.py` — NEW: SetPreferenceTool (~130 lines)
- `nanobot/cli/commands.py` — tool registration, migration, reschedule wiring, warnings (~40 lines)
- `nanobot/copilot/metacognition/detector.py` — +negative penalization (~5 lines)
- `nanobot/copilot/cost/db.py` — +routing_preferences table (~20 lines)
- `nanobot/copilot/dream/cycle.py` — +always deliver, +self-reflect, +preference cleanup (~50 lines)

**Total: ~470 lines changed/added across 10 files (1 new)**

---

## [V1 Complete] — 2026-02-14

### Fixed — V1 Completion (Memory, Dream Cycle, Supervisor)
- Declared missing runtime dependencies (`qdrant-client`, `redis`, `openai`, `aiosqlite`) in `pyproject.toml` — these were causing silent memory degradation via ImportError → graceful fallback → no memory
- Fixed ProcessSupervisor false crash detection: fire-and-forget `start()` methods returned immediately, supervisor interpreted this as a crash and restarted 5 times before giving up. Added `get_task_fn` parameter to await internal long-running tasks.
- Eliminated double-start of supervised services (explicit `await start()` + supervisor `_run_service()` both calling `start()`)
- Added dream cycle scheduler via `croniter` consuming `dream_cron_expr` config (default `"0 3 * * *"`)
- Added memory initialization retry (3 attempts, 2s delay) for transient QDrant/Redis startup delays
- ~50 lines changed across 3 files. No new files. No new features — just making existing code run.

### Added — Onboarding Interview System
- `/onboard` command triggers structured getting-to-know-you interview
- `/profile` command shows current user profile
- Interview conducted by nanobot's own LLM via prompt injection (~500 tokens)
- Token-conscious storage: lean USER.md (~10 lines) + detailed MEMORY.md
- Updated `/help` text with new commands

### Added — Multi-Cloud Failover
- Venice AI provider support (privacy-focused, uncensored models)
- Nvidia NIM provider support (GPU-optimized inference)
- FailoverChain: each routing tier tries multiple providers before escalating
- `/use <provider>` command for manual provider override

### Fixed — WhatsApp Bridge
- jidDecode polyfill for newer Baileys versions (messages were failing silently)
- Auto-start bridge process from gateway
- Improved connection state logging

### Changed — Provider Registry
- Extended from ~15 to 30+ supported providers
- Auto-prefixing for cross-provider model name translation

---

## [0.1.3.post7] — 2026-02-13

### Added — Security Hardening
- MRO chain sandbox escape blocked (`agent/safety/sanitizer.py`)
- Private mode activation wired into routing

### Added — MCP Integration
- Model Context Protocol client for external tool servers
- MCP bridge for tool discovery and routing
- Optional dependency: `mcp>=1.0.0`

---

## [Phase 3] — 2026-02-12

### Added — Approval System
- `ApprovalInterceptor` orchestrates full approval flow
- `NLApprovalParser` — regex + SLM for natural language approval parsing
- `RulesEngine` — default patterns + dynamic user-created rules
- `ApprovalQueue` — asyncio.Event-based blocking with crash recovery
- Only `exec` and `message` tools require approval by default
- Quick cancel: "skip", "nevermind" → immediate abort

### Added — Metacognition
- `SatisfactionDetector` — regex positive/negative signal detection
- `LessonManager` — CRUD with confidence scoring, reinforcement, decay
- Lessons injected into system prompts (top 3 by relevance)
- Automatic deactivation of unhelpful lessons

### Added — Cost Alerting
- `CostAlerter` — per-call and daily threshold alerts via WhatsApp
- `CostLogger` — per-call cost calculation and routing decision logging

---

## [Phase 2] — 2026-02-11

### Added — Copilot Core
- `RouterProvider` — drop-in LLMProvider with heuristic routing
- `ExtendedContextBuilder` — tiered context assembly (3 tiers)
- `TokenBudget` — context budget management and continuation detection
- `BackgroundExtractor` — async fact/decision/constraint extraction
- `ThreadTracker` — topic-based conversation thread detection
- `VoiceTranscriber` — faster-whisper + API fallback
- Self-escalation: local model can trigger retry with bigger model
- Private mode: local-only routing with 30-min auto-timeout

### Added — Memory, Dream Cycle & Infrastructure Modules
- `copilot/memory/` — QDrant episodic (multi-factor scoring, hybrid search), Redis working (auto-reconnect), full-text search (FTS5 + BM25)
- `copilot/dream/` — nightly cycle (7 jobs orchestrated), heartbeat (proactive tasks, active hours guard), monitor (state-transition alerting, morning nag), supervisor (auto-restart, exponential backoff)
- `copilot/tasks/` — task manager, worker, tool interface
- `copilot/tools/` — git, browser, documents, AWS, n8n (V2 — not yet registered as agent tools)
- `copilot/status/` — health dashboard aggregation

---

## [Phase 1] — 2026-02-10

### Added — Foundation
- nanobot cloned and configured
- LM Studio connected (Windows 5070ti, 192.168.50.100:1234)
- WhatsApp channel via Baileys bridge (Node.js)
- QDrant (localhost:6333) and Redis (localhost:6379) infrastructure
- SQLite database for structured data
- `~/.nanobot/config.json` with provider configuration
- Skill stubs: sentry-router, memory-manager, status
- End-to-end WhatsApp message flow verified
