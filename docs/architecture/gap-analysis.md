# Codebase Gap Analysis — 2026-02-21

> **Purpose**: Ground-truth audit of what's planned vs. what's actually in the code.
> **Source**: Direct code reads of routing/, tasks/, dream/, context/, copilot/config.py, agent/loop.py
> **Supersedes**: All prior status docs for accuracy. Old V2/Amendment docs remain as decision history.
> **Status legend**: ✅ DONE | ⚠️ PARTIAL | ❌ NOT STARTED | 🐛 BUG | 🔄 CHANGED (from plan)
>
> **V3 note (2026-02-23):** Most gaps in this document become irrelevant with the
> Genesis v3 migration to Agent Zero. See `genesis-v3-dual-engine-plan.md` §4
> "What This Migration Solves" in the Genesis repo (`WingedGuardian/GENesis`,
> local: `~/genesis/docs/architecture/`). Genesis design docs no longer live
> in this (copilot) repo.

---

## 1. Routing Subsystem

| Item | Planned | Actual | Status |
|------|---------|--------|--------|
| Heuristic `classify()` removal | Delete heuristics.py | File kept — only contains `RouteDecision` dataclass. No classify() function. Zero calls from router. | ✅ DONE |
| Router class rename | `RouterProvider` → `ConversationProvider` | Class is still `RouterProvider`. Deliberately kept — no functional reason to rename. | 🔄 CHANGED |
| Default model + self-escalation | Default cloud model + `[ESCALATE]` retry | Implemented: `force_provider` > `private_mode` > `routing_plan` > `default_conversation_model`. Self-escalation via `[ESCALATE]` marker is live. | ✅ DONE |
| Plan-based routing | LLM-generated routing plan, user-approved | `self._routing_plan` is the primary routing mode. When set, it governs all calls. | ✅ DONE |
| LM Studio alert suppression | `if "lm_studio" not in name:` guard | Present in **both** circuit breaker failure paths in failover.py. | ✅ DONE |
| `big_model` default | Opus → Sonnet | `big_model: str = "anthropic/claude-sonnet-4-6"` in config.py. | ✅ DONE |
| `escalation_model` field | New field replacing big_model | Both `big_model` AND `escalation_model` exist — `escalation_model` defaults to Sonnet, `big_model` also Sonnet. The stale marker was wrong: big_model still exists AND escalation_model was added alongside it. | ⚠️ PARTIAL |
| Native provider preference | Put native provider first in failover chain | Implemented via `find_by_model()` in `_build_chain()`. | ✅ DONE |
| Per-provider alert dedup | `provider_failed:{name}` alert keys | Implemented in failover.py `_fire_alert()` — passes `name` as dedup key. | ✅ DONE |
| `free_tier_status` table | Track free API tier quota | Table **not found** in any schema. | ❌ NOT STARTED |
| Natural language model switching | "Use something cheaper" → LLM resolves | Not implemented. `/use` command still requires provider/model syntax. | ❌ NOT STARTED |
| `switch_model` tool | LLM calls tool with structured params | Not implemented. | ❌ NOT STARTED |
| Model registry (`models.json`) | Living registry of models with metadata | Not found. `models.md` exists as an identity file but no structured JSON registry. | ❌ NOT STARTED |
| WhatsApp outbound rate limiter | 1 msg/2s, FIFO queue, digest at 10 | Not found in channel handler. | ❌ NOT STARTED |
| Context bridging on model switch | Inject "continuing from {model}" note | Not found in router.py switch logic. | ❌ NOT STARTED |
| Memory consolidation mid-tier routing | Route `_consolidate_memory()` explicitly | Still uses `self.model` (main model). Bug #4 from Amendment #2 unresolved. | 🐛 BUG |

---

## 2. Task System

### Phase 0 Infrastructure

| Item | Planned | Actual | Status |
|------|---------|--------|--------|
| P0.1 SqlitePool mandate | All raw `aiosqlite.connect()` → SqlitePool | **30+ violations remain**: AlertBus (2), cycle.py (20+), tasks/manager.py (30+), loop.py routing prefs (3). SqlitePool exists and works but is barely used. | 🐛 BUG |
| P0.2 `process_direct()` race fix | Local variables instead of `self.model` mutation | Fixed with try/finally save/restore. | ✅ DONE |
| P0.3 `get_next_pending()` query fix | `status = 'pending'` only | **Still picks 'pending' AND 'active'** — can re-execute in-progress tasks. | 🐛 BUG |
| P0.4 Tool name→class registry | Map tool names to classes | Status unknown — not verified in this audit. | ❓ UNVERIFIED |
| P0.5 Crash recovery for awaiting tasks | Resume awaiting tasks on restart | Status unknown. `awaiting` status exists. | ❓ UNVERIFIED |
| P0.6 LiteLLM routing verification | Verify native routing works | Status unknown. | ❓ UNVERIFIED |
| P0.7 Router simplification | Decision #30 — remove heuristics, add default+escalation | Done. | ✅ DONE |
| P0.8 session_key passthrough | Pass session_key through task stack | Status unknown. | ❓ UNVERIFIED |
| P0.9 Cancellation infrastructure | `parked` status + single `_current_orchestrator` | Single `_task: asyncio.Task | None` done. **`parked` status NOT added.** Cancellation is just `fail`. | ⚠️ PARTIAL |
| P0.10 Wake-after-resume events | `asyncio.Event` wake instead of 60s poll | Still uses `await asyncio.sleep(interval)` polling. | ❌ NOT STARTED |
| P0.11 `task_context` + `free_tier_status` tables | Two new SQL tables | Neither table exists in schema. | ❌ NOT STARTED |
| P0.12 WhatsApp outbound rate limiter | 1 msg/2s, FIFO queue | Not found. | ❌ NOT STARTED |
| P0.13 WhatsApp media bug fixes | Persistent storage, auto-extraction, etc. | Reported as done in Amendment #2 (2026-02-18). Not re-verified in this audit. | ✅ (ASSUMED) |

### Task Execution (Phase 1–3)

| Item | Planned | Actual | Status |
|------|---------|--------|--------|
| Task statuses | `pending`, `active`, `awaiting`, `parked`, `completed`, `failed` | `pending`, `planning`, `awaiting`, `active`, `completed`, `failed`, `paused` — **`paused` replaces `parked`** | ✅ DONE |
| LLM task decomposition | Frontier model designs DAG | Implemented: `_decompose_fn` → LLM → `parse_decomposition_response()` → steps. Steps have `tool_type` + `recommended_model`. | ✅ DONE |
| Navigator duo | Two-checkpoint peer review (plan + execution) | Fully implemented in navigator.py with metrics, disagreement tracking, escalation. | ✅ DONE |
| Task retrospectives | Per-task post-mortem, embedded in Qdrant | Implemented in `_run_retrospective()`, stored in `task_retrospectives` table + Qdrant. | ✅ DONE |
| Cross-model deliverable review | Different model reviews draft before delivery | Not implemented. No reviewer_model or review loop found. | ❌ NOT STARTED |
| Two-phase intake interview | Nanobot confirms → orchestrator probes further | Not implemented. Single-phase task creation. | ❌ NOT STARTED |
| Park/resume commands | `/park`, `/resume <id>` | Implemented as pause/resume: `pause_task()`/`resume_task()` on manager, `paused` status with schema migration, worker checks at step boundaries, WebUI buttons. | ✅ DONE |
| Cancel with confirmation | Two-tier: graceful then force-close | Cancel exists in WebUI (`POST /tasks/{id}/cancel`). Pause/resume added for graceful control. No two-tier confirmation yet. | ⚠️ PARTIAL |
| Cost tracking per node | Per-step cost + orchestrator overhead | `cost_usd` column exists in `task_steps`... but not confirmed populated. | ❓ UNVERIFIED |
| Task budget enforcement | $2 default, pause at 100%, user approves continuation | Not implemented. `default_task_budget` config field exists but no enforcement loop. | ❌ NOT STARTED |
| Playbook system | Reusable templates from successful tasks | Not implemented. No `task_playbooks` table. | ❌ NOT STARTED |
| `task_context` table | Session notes for nanobot between tasks | Not implemented. `context_json` column in tasks exists but never populated. | ❌ NOT STARTED |
| `task_attachments` table | Files attached to tasks | Not implemented. | ❌ NOT STARTED |
| Situational Awareness Briefing | Active tasks/questions injected into every system prompt | Implemented: `build_situational_briefing()` static async method in ExtendedContextBuilder, wired into loop.py. 4 independent SQL queries (active tasks, pending questions, completions, daily spend). Guarded by `skip_enrichment`. | ✅ DONE |
| Task feasibility check | First orchestrator step before DAG design | Not implemented. | ❌ NOT STARTED |
| Blocker detection + early bailout | "If 3 approaches failed, STOP" | Not implemented (design guidance in prompts only). | ❌ NOT STARTED |
| Capability profiles | Per-task-type tool/network/filesystem scope | Not implemented. Workers have full tool access. | ❌ NOT STARTED |
| Schema-validated worker outputs | Parse failure → retry with correction | Not implemented. | ❌ NOT STARTED |
| Worker tool restriction (V2.1 scope) | Research + files only, no shell | Not implemented. Workers get full tool suite. | ❌ NOT STARTED |

---

## 3. Dream Cycle

| Item | Planned | Actual | Status |
|------|---------|--------|--------|
| All 13 jobs | 13 named jobs | All 13 present: consolidation, cost_report, lesson_review, backup, monitor, reconcile, zero_vectors, routing_prefs, memory_budget, reflection, identity_evolution, observation_cleanup, codebase_index | ✅ DONE |
| Per-job checklist tracking | `JobResult` per job, `DreamReport.jobs` list | Fully implemented via `_run_job()` wrapper. Each job gets status, duration_ms, detail. | ✅ DONE |
| LM Studio filter in alert queries | `AND message NOT LIKE '%lm_studio%'` | Present in `_gather_reflection_context()` and health_check.py unresolved alerts. | ✅ DONE |
| Reflection character limit | 200 → 1000 | Upgraded: 500 (parse fail), 1000 (stored user_summary), 2000 (morning brief context). | ✅ DONE |
| LM Studio filter in Job 5 monitor | Filter `sub.name != "LM Studio"` | Not separately verified — may be in the `_monitor_and_remediate()` method. | ❓ UNVERIFIED |
| Identity evolution (Job 11) | notify/autonomous modes, evolution_log | Implemented. | ✅ DONE |
| Observation cleanup (Job 12) | Expire old unacted observations | Implemented. | ✅ DONE |
| Codebase indexing (Job 13) | Update codebase-map skill | Implemented. | ✅ DONE |
| Timezone in date queries | Use `tz.local_date_str()` instead of `date('now')` | **NOT done.** No tz.py exists. All queries still use `datetime('now', ...)`. | ❌ NOT STARTED |
| Monthly review writes findings.json | `monthly_review_findings.json` for weekly to pick up | Implementation status unknown. | ❓ UNVERIFIED |

---

## 4. Heartbeat

| Item | Planned | Actual | Status |
|------|---------|--------|--------|
| Gating bug fix | Remove `return` when no observations/tasks | Fixed. Code says "running ambient tick" and proceeds to LLM. | ✅ DONE |
| Daily session keys | `heartbeat:{YYYY-MM-DD}` session per day | **Not implemented as per-date keys.** Uses `_last_dream_check` epoch in memory. Session continuity unclear. | ❌ NOT STARTED (or differently implemented) |
| Writes to dream_observations | Structured JSON observations stored | Implemented. | ✅ DONE |
| Writes to heartbeat_events | Events + checklist logs stored | Implemented. | ✅ DONE |
| Skips when dream cycle running | `DreamCycle.is_running` check | Implemented. | ✅ DONE |
| Morning brief injection | First tick post-dream gets reflection context | Implemented via `_last_dream_check` timestamp comparison. | ✅ DONE |
| Proactive WhatsApp delivery / deliver_fn | Heartbeat triggers outbound messages | Not implemented — **explicitly deferred to V2.2 per design**. Heartbeat is DB-only. | 🔄 BY DESIGN |
| Severity-based injection filter | Only `medium`/`high` events injected into nanobot | Not verified — health_check.py filter status unknown. | ❓ UNVERIFIED |
| 20B local + Gemini Flash fallback | Heartbeat model upgrade from 4B | Config: `heartbeat_model` field defaults to `dream_model` (Gemini Flash). No 20B local model separate config for heartbeat. Plan partially folded into general model config. | ⚠️ PARTIAL |

---

## 5. Memory & Context

| Item | Planned | Actual | Status |
|------|---------|--------|--------|
| Qdrant episodic memory | Vector store for long-term recall | Implemented and working. | ✅ DONE |
| Cloud extraction fallback | Haiku fallback when LM Studio down | Implemented. `cloud_extraction_model` config field. | ✅ DONE |
| Four-level JSON parse fallback | `json.loads` → fence strip → regex → trailing comma | Implemented in `_parse_llm_json()` across dream/heartbeat. | ✅ DONE |
| Error response guard in memory pipeline | `not is_error` before extraction | Implemented via `skip_enrichment` and error detection. | ✅ DONE |
| Budget-aware identity files | Per-file token budgets in `budgets.json` | Implemented. Dream cycle Job 9 checks MEMORY.md budget. | ✅ DONE |
| Weekly review trims identity files | LLM trims over-budget files | Implemented in weekly review. | ✅ DONE |
| Monthly review adjusts budgets | Only monthly changes `budgets.json` | Implementation unknown. | ❓ UNVERIFIED |
| Situational Awareness Briefing | Active tasks/questions in every system prompt | Implemented via `build_situational_briefing()` in ExtendedContextBuilder. | ✅ DONE |
| MEMORY.md as lean scratchpad | ~150 tokens, goals/blockers/priorities only | Config has budget, dream warns if exceeded. Enforcement relies on weekly review trim. | ⚠️ PARTIAL |
| `<!-- memory: keyword -->` pointer retrieval | Evicted content flagged for Qdrant retrieval | Not found in ExtendedContextBuilder. | ❌ NOT STARTED |

---

## 6. Infrastructure

| Item | Planned | Actual | Status |
|------|---------|--------|--------|
| Timezone normalization (tz.py) | `nanobot/copilot/tz.py` with `local_now()` etc. | **File does not exist.** All queries use `datetime('now')` UTC. Morning nag uses `datetime.datetime.now()` (local time, but no TZ awareness). | ❌ NOT STARTED |
| SqlitePool adoption | All raw `aiosqlite.connect()` replaced | **Major violations remain**: AlertBus (2), dream/cycle.py (20+), tasks/manager.py (30+), loop.py (3). | 🐛 BUG |
| `process_direct()` race fix | Local variable save/restore for self.model | ✅ Fixed with try/finally. | ✅ DONE |
| `skip_enrichment` isolation | Background services pass `skip_enrichment=True` | ✅ Parameter exists, documented, used to guard all enrichment operations. | ✅ DONE |
| Asyncio timer try/finally re-arm | Prevent silent timer death | Implemented in cron (Lesson 38). | ✅ DONE |
| Agent loop graceful degradation | Final iteration forces text-only completion | Implemented (Lesson 39, commit ac5b533). | ✅ DONE |
| Memory consolidation mid-tier routing | Route `_consolidate_memory()` to fast/mid model | Still uses `self.model`. Bug #4 from Amendment #2 unresolved. | 🐛 BUG |
| `copilot/__init__.py` timezone init | `tz.init(config.timezone)` at startup | Not present (no tz.py to init). | ❌ NOT STARTED |

---

## 7. Recurring Troubleshooting Patterns (from Lessons Learned #29–46)

These are patterns that have bitten us repeatedly — distinct from planned-vs-actual gaps:

| Pattern | Category | Recurrence |
|---------|----------|------------|
| SQLite positional index reads break on ALTER TABLE | Schema | Happened once, rule added |
| LLMs return prose-wrapped JSON, not bare JSON | Parsing | 2x (extraction, dream cycle) |
| Background services contaminate user context | Architecture | Fixed via skip_enrichment |
| Cron reminder framing (bare string → LLM treats as task) | Framing | Happened, rule added |
| Identity files not updated during refactors | Process | 2x (router V2 renames, navigator) |
| Uncommitted work vanishes on branch switch | Process | 1x (entire session lost) |
| Asyncio timer task dies silently without try/finally | Reliability | 1x (10-min cron stopped firing) |
| Naive datetime interpreted as UTC on UTC server | Timezone | 1x (reminder 5h off) — tz.py would fix this class |
| Cross-session message delivery needs breadcrumbs | UX | 1x (reminder reply had no context) |

---

## Summary: Completion Scorecard

| Area | Done | Partial | Not Started | Bugs |
|------|------|---------|-------------|------|
| Routing | 7 | 2 | 5 | 1 |
| Task System Phase 0 | 3 | 1 | 6 | 2 |
| Task System Phase 1–3 | 4 | 1 | 14 | 0 |
| Dream Cycle | 7 | 0 | 1 | 0 |
| Heartbeat | 5 | 1 | 1 | 0 |
| Memory & Context | 5 | 2 | 3 | 0 |
| Infrastructure | 4 | 0 | 2 | 2 |

**The dream cycle is the most complete subsystem.** The task system (Phases 1–3) is the furthest behind — navigator duo is done but most of the session management, budget enforcement, UX, and safety features are not started. SqlitePool adoption and timezone normalization are structural debts affecting everything.
