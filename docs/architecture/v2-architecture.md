# Executive Co-Pilot V2: Architecture & Roadmap

> **V1**: A reactive assistant with memory, self-maintenance, intelligent routing, and cost-conscious multi-model orchestration.
> **V2**: An autonomous digital executive assistant — takes your to-do list and gets it done.

---

## The Vision (Revised 2026-02-16)

A single interface (WhatsApp) through which everything digital gets handled. You're the CEO; the system is your company. Not just answering questions — **doing the work**: coding features, researching options, handling admin, creating content. Learning from outcomes, reaching out when something matters, staying quiet when it doesn't, and getting better every week.

V1 built the nervous system. V2 adds the hands.

### What Changed from the Original V2 Architecture

The original V2 doc was structured around **features** (proactive scheduler, tiered reviews, deeper lessons, autonomous tools, task persistence, sub-agents, dashboard). Through brainstorming (2026-02-16), we identified that the **task lifecycle engine** — the ability to take a to-do item and actually get it done — is the core product that everything else serves.

The revised architecture adds the task lifecycle as the new centerpiece while preserving the operational intelligence features (memory, lessons, reviews, metacognition) that make the system smarter over time. These are **not mutually exclusive** — the task engine needs the intelligence layer, and the intelligence layer becomes more valuable when there are real tasks producing real outcomes to learn from.

---

## Core Architecture: The Task Lifecycle

Every task flows through this lifecycle:

```
User message → INTAKE → DECOMPOSE → EXECUTE → CHECKPOINT → ITERATE → COMPLETE
                 │          │           │           │            │          │
              Detect if   Frontier    Workers    Report to    Incorporate  Present
              task vs     model       execute    user via     feedback,    deliverable
              chat        breaks      steps      WhatsApp     re-plan
                          into steps
```

**The interaction model is asynchronous and iterative:**
1. User sends a task via WhatsApp (or it's pulled from an external to-do system)
2. System asks clarifying questions upfront
3. System goes away and works
4. System comes back with: "here's what I did, here's what I couldn't, here are new questions"
5. Repeat until done
6. Final review

Tasks execute sequentially (one at a time) in V2.1. The user doesn't babysit — they check in when convenient. *(Revised 2026-02-18: parallel execution deferred. Tasks queue by priority. User can park a task to start a different one.)*

---

## Model Architecture

### Roles for Task Execution

V1 used a 5-tier model table for conversational routing. V2 adds **role-based assignment** for task work: the right model for the job, chosen by the decomposer.

| Role | Responsibility | Model Class | Examples |
|------|---------------|-------------|----------|
| **Thinker** | Task decomposition, re-planning, iteration decisions | Frontier | Opus, GPT-5 Codex, Gemini Pro |
| **Coordinator** | Task management, progress reporting, context resolution, feedback matching | Strong-cheap | Sonnet, Gemini Flash, MiniMax |
| **Worker** | Step execution (research, coding, ops, content) | Varies by step | Any model appropriate to the work |

The model pool (specific models, costs, capabilities, free-tier routing) is designed separately — the architecture doesn't depend on specific models, only on roles.

### 5-Tier Model Architecture (V1, Still Active)

Canonical model tier assignments for conversational routing and background services. Each tier has a name, runtime, and clear responsibility boundary.

| Tier | Name | Runtime | Examples | Cost | Use Cases |
|------|------|---------|----------|------|-----------|
| **0** | **Brainstem SLM** | LM Studio (local) | Llama 4.1 (4B) | Free | Background extraction, simple classification. Fixed schema, shallow reasoning. **Nothing else.** |
| **1** | **Local Cortex** | LM Studio (local) | Qwen 30B MoE, Mistral 24B | Free | Primary conversation, privacy mode, always-available baseline. NOT for metacognition. |
| **2** | **Tactical Hub** | Cloud (fast, cheap) | Haiku 4.5, Gemini 3 Flash | ~$0.001/call | Metacognition, tiered reviews, lesson synthesis, morning brief, cost reports. |
| **3** | **Cognitive Core** | Cloud (strong) | Sonnet 4.5, MiniMax 2.5, Kimi 2.5 | ~$0.01-0.03/call | Complex reasoning, multi-step analysis, creative work, task decomposition. |
| **4** | **Executive Office** | Cloud (frontier + thinking) | Opus 4.6, GPT-5.3 Codex, Gemini 3 Pro | ~$0.05-0.15/call | Weekly comprehensive audits, architecture decisions, direction assessment. |

The Brainstem's role is narrow. Anything involving judgment, nuance, or "should I have said something?" is Tier 2+ work. The Local Cortex is for privacy and availability — not for deep thinking. Tier 4 is reserved for high-stakes decisions where frontier reasoning matters.

### V2 Goal: Natural Language Model Switching ("Grandma Mode")

**Current state (V1)**: `/use minimax MiniMax-M2.5` — user must know provider names, model IDs, and the command syntax. Misconfigured combos silently fail.

**V2 target**: The user says in plain language what they want — "use minimax", "switch to the cheapest model", "I want GPT for this", "go back to normal" — and the current LLM (whatever it is) resolves the intent against a **living model registry** (available providers, their models, capabilities, costs, current health). The LLM:

1. **Resolves ambiguity by asking**, not guessing. "MiniMax has M2.5 and M2.5-highspeed — M2.5 is cheaper, highspeed is 2x faster. Which do you want?" If the user says something nonsensical ("use llama on anthropic"), the LLM explains why it can't work and suggests alternatives.
2. **Validates before switching.** Checks the model exists on the target provider, the API key is configured, and **pings health before confirming the switch**. Never routes to a non-existent or unhealthy model — the user should never discover a broken route the hard way.
3. **Works for users who don't know the terminology.** "Use something cheaper" → checks cost table → suggests the cheapest healthy option. "I need the best model for coding" → checks benchmarks → suggests accordingly.
4. **Implemented as a tool, not a command.** The LLM calls a `switch_model` tool with structured params (provider, model) after resolving intent conversationally. No `/use` command needed — though it can remain as a shortcut.
5. **Model registry is config-driven.** A `models.json` or config section listing available models per provider with metadata (cost, capabilities, speed, health status). The LLM reads this at switch time. Registry updated by dream cycle or manually.

**Design principle**: The router is not a feature — it's an **invisible butler**. The user should never need to understand providers, model IDs, or routing tiers. They just say what they want and it works.

---

## V2 Phases (Revised — Ordered by Foundation → Value)

### V2.1 — Task Lifecycle Engine (First Milestone)

**Goal**: Prove the task lifecycle works end-to-end with a simple use case.

**Proof of life**: User texts a multi-step task that produces a real deliverable — e.g., "Set up a new GitHub repo for project X, scaffold the Python project, and push an initial commit." System works asynchronously, delivers the completed artifact with a summary to WhatsApp. *(Revised 2026-02-18: simple research queries like VPS comparisons are handled by nanobot directly — they don't meet the task threshold of "deliverable + iteration.")*

**Components** (revised — see brain architecture plan):
1. ~~Task detection heuristic~~ → LLM-native detection with **two-phase intake interview**. Nanobot detects task potential → confirms with user → gathers requirements and desired outcomes. Then orchestrator spins up, reviews what nanobot sent, and can ask MORE questions before starting any work. TaskTool excluded when RouterProvider resolves to local provider (LM Studio = Tier <3). Lower-tier identity files include escalation prompt. *(Revised 2026-02-18: added two-phase intake — nanobot is latency-sensitive, orchestrator is thoroughness-optimized.)*
2. Per-task orchestrator (fresh frontier agent) designs workflow DAG. Uses direct `provider.chat()` for its own LLM calls (not `process_direct()`). Worker dispatch inline (no separate dispatcher).
3. Worker dispatch via SubagentManager with per-worker model/tools/prompt. Workers spawned with `silent=True`. LiteLLM native routing for multi-provider dispatch.
4. Silent by default — only notify on: questions needing input, draft delivery for feedback, unrecoverable failure. Orchestrator ALWAYS confirms workflow design before executing (no sunset — user explicitly removes this guard rail when ready). *(Revised 2026-02-18: removed 30-day bootstrap cutoff.)*
5. **Iteration loop**: Orchestrator delivers DRAFT → blocks for feedback → re-plans if needed → delivers again. Waits indefinitely for user response — no auto-complete timeout. *(Revised 2026-02-18: user must explicitly approve.)*
6. ~~Heuristic feedback loop~~ → LLM-native feedback routing via context injection (no feedback.py)
7. Task commands: `/tasks`, `/task <id>`, `/cancel <id>` (cancel actually kills running orchestrator via cancellation token + asyncio task registry)
8. ~~Parallel task execution~~ → **Sequential queue** in V2.1. One task executes at a time. Tasks queue by priority. User can park a running task to start a different one (`/park`, `/resume <id>`). Parallel execution deferred to V2.2+. *(Revised 2026-02-18.)*
9. `asyncio.Event` wake signal — TaskWorker wakes immediately on task creation (no 60s poll delay)
10. Task pipeline resilience — timeout protection on LLM calls (`asyncio.wait_for`), DAG cycle detection, budget atomicity, rate limit coordination, monitoring wired into existing AlertBus/heartbeat_events/deliver_fn, auto-resolution via MonitorService
11. Phase 0 infrastructure wiring — SqlitePool mandate, `process_direct()` race fix, cancellation infrastructure, tier check split, tool registry, testable with current codebase

**Communication Architecture** (V2.1 scope):
- **Direct delivery with self-identification**: All outbound from orchestrator/dream cycle/weekly review goes direct to WhatsApp with prefix identifying source (e.g., `[Task #3 — Orchestrator] ...`). NOT through nanobot's LLM. System outbound messages never loop back as inbound — completely separate code paths.
- **Inbound routing**: All user messages go through nanobot. Nanobot sees session notes + pending questions in context and routes task-related replies via TaskTool.
- **Session notes**: Nanobot receives structured context updates (task ID, summary, status) via `heartbeat_events` after deliveries — no LLM processing, just context for follow-up conversations.
- **Blackboard**: Heartbeat writes observations to SQLite. Nanobot queries on demand (`/dashboard`). Only high-priority items pushed to context.
- **Notification preferences**: Deferred to Phase 5 or later. "Silent by default" + existing alert mute is sufficient for current volume.

**Builds on**: TaskManager, TaskWorker, SubagentManager, ExecTool, message bus (all existing and working).

**See**: `2026-02-16-v2.1-brain-architecture-plan.md` for the current implementation plan.
*(The earlier `task-lifecycle-design.md` and `task-lifecycle-plan.md` are superseded.)*

---

### V2.2 — Coding Agent + Model Pool + Heartbeat Reframe

**Goal**: The system can build software. Heartbeat becomes proactive peripheral vision.

**Components**:
1. OpenCode CLI integration as a coding worker (model-flexible, 75+ models)
2. Model pool design — living registry of available models with capabilities, costs, free tiers
3. Parallel task execution — orchestrators launched as independent `asyncio.create_task()` coroutines *(Revised 2026-02-18: moved BACK to V2.2 — V2.1 uses sequential queue)*
4. Priority/urgency system for task ordering
5. Full heartbeat reframe: rotating roster, blackboard architecture, SLM-powered observation, proactive peripheral vision
6. Orchestrator liveness monitoring: `last_activity` timestamps, task-aware stuck thresholds, orphan detection
7. Identity file consolidation: weekly review job for 1000-token cap enforcement, long-term memory overflow with pointer keywords
8. Notification preferences: `/settings notifications` command, message queue, digest generation

**Note**: V2.1 Phases 0-5 (Infrastructure → Foundation → Core Engine → Wiring → Resilience → Polish) are completion gates before V2.2 begins. See brain architecture plan for full phase breakdown.

---

### V2.3 — Browser Automation + External Integrations

**Goal**: The system can interact with websites and pull tasks from external systems.

**Components**:
1. Browser automation (Playwright or Agent-S) for web research, form filling, testing
2. External to-do system integration (Todoist, Notion, Linear, etc.)
3. Proactive task suggestions from dream cycle analysis

---

### V2.4 — Communication + Content

**Goal**: The system handles email, creates content, and communicates on your behalf.

**Components**:
1. Email (IMAP/SMTP) — read, summarize, draft, send with approval
2. Content pipelines — documents, proposals, blog posts
3. n8n integration hub for 400+ service connections

---

### V2.5 — Self-Improvement + Advanced Intelligence

**Goal**: The system gets better over time without manual tuning.

**Components**:
1. Tiered review system (hourly/nightly/weekly self-assessment)
2. Deeper lessons (semantic matching, categories, composite lessons, meta-lessons)
3. Autonomy calibration via shadow mode
4. Self-evolving extension lifecycle (skills + tools — see "Extension Lifecycle" under Operational Intelligence)

---

### V2.6+ — Future Capabilities

| Feature | Description |
|---|---|
| ~~Sub-agent orchestration~~ | **Implemented in V2.1** — per-task orchestrator with parallel worker dispatch |
| Web dashboard | Visual task board, cost charts, memory browser, lesson manager |
| Ambient awareness | Screen capture, meeting transcription |
| Voice synthesis | TTS responses via WhatsApp voice notes |
| Neo4j semantic graph | Entity relationships across people, projects, decisions |
| Delegation & handoff | Task delegation to other humans with follow-up tracking |
| Telegram multi-channel | Explore separate channels per agent (nanobot, orchestrator, dream cycle, heartbeat oversight). User controls which to follow/mute. Replaces single WhatsApp thread for multi-agent communication. |

---

## Operational Intelligence (Ongoing — Supports All Phases)

These capabilities run continuously and improve all task execution. They are not phases — they're cross-cutting concerns that get better as the system does more real work.

### Heartbeat — Proactive Peripheral Vision

> **⚠️ Note**: The design below describes the V2.2 target heartbeat (outbound messaging, rotating roster, NEVER takes action). Current V1 implementation is `CopilotHeartbeatService` — see the Sentience Plan note at the end of this section and `data/copilot/heartbeat.md` for actual behavior.

**NOT a health check.** The heartbeat is the system's ambient awareness — its proactive peripheral vision. Nanobot is reactive (processes user messages). The heartbeat is what gives the system initiative. Without it, nanobot only thinks when the user texts. With it, nanobot thinks about the user's world continuously.

**Role split**: Heartbeat = immune system (real-time detection). Dream cycle = learning system (reflection + improvement). Same domains, different depth/model.

**Design**:
- Runs on **20B local model** (LM Studio) with Gemini Flash free tier cloud fallback.
- **NEVER takes action.** Only writes observations to the blackboard (SQLite).
- **NEVER talks to the user.** Writes to blackboard. Nanobot decides what to surface.
- **NEVER judges higher-tier work.** Observes, doesn't second-guess. Acts as COURIER for orchestrator retrospectives.
- **Baseline checks** (every tick, programmatic): task status, cost burn rate, undelivered messages.
- **Rotating roster** (SLM analysis, one focus per tick): conversation reflection, temporal awareness, anomaly detection, opportunity spotting.
- Living reference file: `data/copilot/heartbeat.md` (200-300 tokens, improved by dream cycle + weekly review).
- Most ticks should be SILENT (nothing significant to report).

**Blackboard**: Queryable SQLite store, NOT prompt injection. Nanobot queries on demand (`/dashboard`). Only HIGH-priority items pushed as context notes (~20-50 tokens). Dream cycle reviews full 24h.

> **Sentience Plan (2026-02-20)**: Foundation implemented. `CopilotHeartbeatService` subclasses `HeartbeatService` and enriches the heartbeat prompt with: unacted dream observations (LIMIT 10), pending/active tasks, autonomy permissions, and a morning brief (first tick post-dream). LLM response parsed for JSON observations, written to `dream_observations` and `heartbeat_events`. Concurrency safety: checks `DreamCycle.is_running` before executing — skips tick if dream is active. The full proactive outbound messaging ("heartbeat decides to text the user") remains V2.2 scope.

### Identity File Lifecycle
Identity files have per-file token budgets stored in `~/.nanobot/workspace/budgets.json` (SOUL: 250, USER: 250, AGENTS: 600, POLICY: 200, MEMORY: 150). Three-tier enforcement:
- **Dream cycle (daily)**: warns if any file exceeds its budget (heartbeat event, no truncation)
- **Weekly review**: trims over-budget files using LLM judgment about what to cut
- **Monthly review**: adjusts the budgets themselves (the ONLY cycle that changes budget policy)

memory/MEMORY.md is a lean scratchpad (~150 tokens): active goals, blockers, priorities only. Facts go to `memory store` (writes to SQLite + Qdrant + FTS5). Session summaries are stored to all searchable backends on consolidation. HISTORY.md exists only as a non-copilot fallback.

Identity files are a curated working set. Deep context lives in episodic memory (Qdrant) and structured items (SQLite), retrieved on demand via `memory search` or auto-injected as core facts (confidence ≥ 0.8).

**Learning policy**: All learning is user-supervised. Dream observations and identity file changes require approval. No automatic sunset — user explicitly relaxes when ready.

> **Sentience Plan (2026-02-20)**: Identity evolution framework implemented. Dream cycle Job 11 reads `autonomy_permissions.identity_evolution`: `notify` mode surfaces proposals via heartbeat (writes `observation_type='evolution_proposal'` to `dream_observations`); `autonomous` mode applies the top proposal directly, diffs logged to `evolution_log` with rollback tracking. Velocity limit: 1 file/cycle for system-initiated changes. User-directed changes bypass the limit. Safety: 30-minute user-activity check before autonomous writes (dream runs at 7 AM). All changes tracked in `evolution_log` for audit and rollback.

### Task Pipeline Monitoring

The task pipeline wires into existing infrastructure for detection, auto-resolution, and escalation. No new monitoring systems — only integration with what's already built.

- **Detection** (code, zero LLM cost): `asyncio.wait_for` timeout on hung API calls, budget threshold checks, circuit breaker trips, worker inactivity detection, rate limit 429 tracking.
- **Auto-resolution** (code, zero LLM cost): Hung calls cancelled + retried with backoff. Rate limits use exponential backoff with jitter. Unavailable models fail over to next provider. Budget 80% warns user, 100% aborts gracefully.
- **Escalation** (through nanobot, not raw injection): AlertBus high severity → deliver_fn → OutboundMessage → WhatsApp. Nanobot sees heartbeat_events at next turn → conversational delivery. User gets full context: what failed, what the system tried, what it needs from the user.

**Key**: Goes THROUGH nanobot's conversation, not raw bus injection. The old approval system failed by bypassing nanobot. This doesn't.

**Infrastructure used**: AlertBus (`copilot/alerting/bus.py`), heartbeat_events table (`copilot/cost/db.py`), ProcessSupervisor (`copilot/dream/supervisor.py`), deliver_fn pattern (`cli/commands.py`), MonitorService (`copilot/dream/monitor.py`).

### Proactive Scheduler
The heartbeat service + cron system already exist. The heartbeat reframe (above) provides the intelligence layer that decides *what* to surface and *when*.

**Components**:
1. **Morning brief** — Summary of overnight activity, today's priorities, pending tasks, reminders. Generated by **Tactical Hub** (Tier 2). Delivered via WhatsApp at user's preferred wake time.
2. **Missed-opportunity detection** — Heartbeat catches surface-level (SLM). Dream cycle catches subtle (Tier 2/3).
3. **Scheduled outreach** — Deadline reminders, project nudges. Uses cron system + n8n integration for execution.
4. **Context-aware timing** — Respects quiet hours, batches non-urgent items.

### Tiered Review System
The system reviews its own performance at four cadences in a **Worker → Manager → Director** pipeline. Information flows up (daily→weekly→monthly for review); decisions flow down (monthly findings→weekly for implementation).

**Every ~2 hours — Heartbeat** (20B local + Gemini Flash fallback):
- Baseline: task status checks, cost anomalies, health monitoring
- Rotating roster: conversation reflection, temporal awareness, anomaly detection
- Reads CHANGELOG.local for external codebase changes
- Writes observations to blackboard (SQLite)
- Cost: ~$0.00/day (local/free tier)

**Daily 7 AM — Dream Cycle / Worker** (Gemini 3 Flash, free tier):
- 13 jobs total (Jobs 1-10 programmatic, 11-13 autonomous): memory consolidation, lesson decay, backup, zero-vector cleanup, Qdrant reconciliation, routing pref cleanup, file budget warnings, cost report, health monitor, operational self-reflection, identity evolution, observation cleanup, codebase indexing
- Operational self-reflection (LLM): "what broke today, what needs attention tomorrow, data quality issues"
- Does NOT make strategic decisions — that's weekly's job
- Cost: ~$0.01-0.05/night (free tier model)

**Sunday 9 AM — Weekly Review / Manager** (Claude Opus 4.6, Tier 4):
- **Dream oversight**: reviews dream cycle error logs, verifies cleanup decisions
- **Implements monthly findings**: reads `monthly_review_findings.json`, addresses each, clears file
- **Architecture & code quality**: monitors drift, makes changes (suggests to user first for significant changes)
- **Memory health**: trims over-budget identity files (LLM judgment), does NOT adjust budget policy
- **Model pool audit**: routing verification, new model search, free tier optimization
- **Cost trends**: week-over-week comparison + optimization
- **Strategic direction**: sets priorities for coming week
- Cost: ~$0.50-2.00/week (Opus)

**1st of Month 10 AM — Monthly Review / Director** (Kimi K2.5, 2M context):
- **Reviews weekly reports**: assesses whether weekly is making good strategic decisions
- **Budget policy**: the ONLY cycle that adjusts `budgets.json` — sets limits, weekly enforces
- **Architecture audit**: reads workspace files for drift/contradictions, but does NOT fix — writes findings
- **Codebase patterns**: reads CHANGELOG.local for recurring fixes, instability areas
- **Cost structure**: not trends (weekly handles that), but whether spending is on the right tiers
- **Self-reflection**: long-term thinking — is the system serving the user well?
- **Writes findings**: `monthly_review_findings.json` for weekly to pick up and implement
- Cost: ~$0.30-1.00/month (Kimi)

### Learning Hierarchy
```
Monthly (Director)  → audits weekly → adjusts budget policy → writes findings for weekly
Weekly (Manager)    → oversees dream → implements monthly findings → makes code/architecture changes
Dream (Worker)      → executes maintenance → warns on issues → operational reflection only
Heartbeat           → reads reference → writes observations → NEVER judges higher tiers
```
Bigger models judge smaller. Never the reverse. Monthly audits but doesn't implement — weekly implements. Dream executes but doesn't strategize — weekly sets direction.

### Recursive Self-Review

The system's ability to review its own work, catch gaps, and improve is a core architectural capability — not a feature, but a principle that manifests at every tier AND at the system level.

```
RECURSIVE SELF-REVIEW HIERARCHY
────────────────────────────────────────────────────────────────────
Heartbeat (every 2h, 20B local + cloud fallback)
  Reviews: Recent conversations, task statuses, system state
  Against: Dropped threads, unanswered questions, commitments without tasks
  Catches: Surface-level misses, obvious gaps
  Scope: Component-level (conversations, tasks, infrastructure)

Tier 2/3 — Orchestrator Inline Eval (per-worker)
  Reviews: Worker output
  Against: Expected output spec, task requirements
  Catches: Bad results before they cascade through the DAG

Tier 2/3 — Task Retrospective (per-task, task worker — IMPLEMENTED 2026-02-20)
  Reviews: Task execution — what worked, what failed, capability gaps
  Against: Task description, step outcomes
  Catches: Recurring failure patterns, missing capabilities, wrong models
  Implemented: TaskWorker._run_retrospective() — LLM analysis post-task,
    stored in task_retrospectives table, embedded in Qdrant with
    role="retrospective". Future tasks query these for "past wisdom"
    injection into decomposition prompts.
  Threshold: Only on failures (always) or non-trivial completions (>1 step).

Tier 3/4 — Orchestrator Retrospective (per-task, orchestrator model — V2.2 scope)
  Reviews: Its own workflow design + model assignments
  Against: Actual outcomes, worker performance
  Catches: Wrong decompositions, model misassignments
  Note: Written by the orchestrator itself before terminating — uses
    the orchestrator model (user-designated, typically frontier/Tier 4)
  Status: Deferred to V2.2 (requires brain/orchestrator)

Dream Cycle / Worker (daily, Gemini 3 Flash)
  Reviews: Yesterday's errors, service health, data quality
  Against: File budgets, cleanup thresholds, operational baselines
  Catches: Broken services, over-budget files, stale vectors, extraction failures
  13 jobs total (Jobs 1-10 programmatic, 11-13 autonomous): memory consolidation,
    lesson decay, backup, zero-vector cleanup, Qdrant reconciliation, routing pref cleanup,
    file budget warnings, cost report, health monitor, self-reflection,
    identity evolution, observation cleanup, codebase indexing
  LLM reflection: operational only — "what broke, what needs attention
    tomorrow, any data quality issues"
  Scope: Execution and maintenance. Does NOT make strategic decisions,
    surface capability gaps, or propose new features — that's weekly's job.

Weekly Review / Manager (Sunday, Claude Opus 4.6)
  Reviews: Dream cycle quality + architecture drift + monthly findings
  Against: User goals, stated priorities, codebase health
  Catches: Whether dream cycle is making good decisions, architecture drift
  Implements: Monthly review findings, file trimming, code/architecture changes
    (suggests significant changes to user first)
  ALSO reviews: The ENTIRE nanobot+copilot system as a product —
    delivered value, user satisfaction, missed opportunities, strategic
    direction. "Are we building the right thing? Is the user's life
    materially better this week than last?"
  ALSO asks: What does NANOBOT need to BECOME? Not just capabilities
    and features, but the system and the thinking within it. What might
    need to be rearchitected? What should change, be added, or removed
    to deliver the most value?
  ALSO audits: All extensions (tools/skills) created or modified that
    week — still needed? working? security concerns? See "Self-Evolving
    Extension Lifecycle" for full audit criteria.

Monthly Review / Director (1st of month, Kimi K2.5)
  Reviews: Weekly review reports + budget policy + codebase patterns
  Against: Long-term system health, architectural coherence, user value
  Catches: Whether weekly is moving in the right direction, systemic
    patterns that weekly misses from its narrower time horizon
  Does NOT implement — writes findings to monthly_review_findings.json
    for weekly to pick up and implement next cycle
  Adjusts: File token budgets (budgets.json) — the ONLY cycle that
    changes budget policy
  Self-reflects: Is the system serving the user well long-term? Are the
    automated cycles themselves well-designed? What needs rethinking at
    an architectural level?
────────────────────────────────────────────────────────────────────
Principle: Each tier reviews the tier below it. Monthly audits weekly,
weekly oversees dream, dream executes. Information flows up, decisions
flow down. Monthly never implements — weekly implements.
```

### Deeper Lessons
The system learns in a way that's actually useful, not just "user was unhappy."

1. **Semantic matching** — Embeddings for lesson relevance instead of keyword overlap. QDrant already available.
2. **Categorized lessons** — `routing`, `communication_style`, `tool_usage`, `timing`, `content_preference`, `approval_behavior`.
3. **Lesson provenance** — Store full exchange context that created a lesson, not just a trigger string.
4. **Composite lessons** — "User prefers concise responses EXCEPT for technical deep-dives."
5. **Dream-cycle meta-lessons** — Weekly review finds patterns across lessons → higher-order insights.
6. **Proactive suggestions** — "I notice you always approve Docker operations. Want me to auto-approve them?"
7. **Shadow mode** — After onboarding, system asks "Was that the right call?" after autonomous actions.

### Self-Evolving Extension Lifecycle

The system extends its own capabilities through two mechanisms: **skills** (LLM instruction files + scripts, orchestrated via existing tools) and **tools** (Python classes with programmatic access to nanobot internals). Both follow the same lifecycle but with different security thresholds.

**Distinction**:
- **Skill** = `SKILL.md` + optional `scripts/`, `references/`, `assets/`. The LLM follows instructions using existing tools (`read_file`, `write_file`, shell). No access to nanobot internals. Lower risk.
- **Tool** = Python class extending `Tool`, registered at startup, called via function calling. Has access to sessions, DB, config. Higher risk — requires stricter review.

**The lifecycle**:

```
DISCOVERY → PROPOSAL → USER APPROVAL → BUILDING → REVIEW → SANDBOX → DEPLOY → AUDIT
    │           │            │              │          │         │         │        │
  Dream      Summary      User          Frontier   Clean-    Static    Git     Weekly
  cycle      of what      says yes      model      context   analysis  commit  review
  surfaces   + why        before any    builds     frontier  + mock    + restart audits
  opportunity             work begins   it         reviews   run                all
```

**1. Discovery** — Dream cycle and weekly review surface opportunities:
- Dream cycle (daily): "Task X required 5 manual steps that could be a skill." Notes observation, biases toward skills over tools. Does NOT build anything.
- Weekly review (weekly): Reviews dream observations about capability gaps. Prioritizes by frequency x effort saved.

**2. Proposal** — User sees a summary before anything gets built:
- What the extension would do, why it was identified, skill vs tool recommendation.
- No code, no implementation details — just the concept and expected value.
- Delivered via WhatsApp like any other system communication.

**3. User Approval** — Nothing gets built without a yes:
- User approves the proposal -> building begins.
- User rejects -> observation archived with rejection reason. System does not re-propose the same idea unless circumstances change.
- User can also request changes to the proposal (different scope, skill instead of tool, etc.).

**4. Building** — Frontier model (Tier 4) creates the extension:
- Skills: Writes `SKILL.md` + any scripts. Relatively low risk.
- Tools: Writes Python class. Higher stakes — can access internals.
- Builder uses fresh context with: the capability gap description, relevant existing code (read via tools), and the extension framework docs.
- Builder does NOT see conversation history — prevents prompt injection from user messages poisoning the build.

**5. Review** — A different frontier model instance reviews in a **clean subagent context**:
- Reviewer gets ONLY: the extension code, the stated purpose, and review criteria.
- Reviewer does NOT get: conversation history, user messages, or builder rationale. This is the core security property — if a prompt injection compromised the builder's context, it cannot reach the reviewer.
- Review criteria: correctness, security (no command injection, no data exfiltration, no unbounded resource use), adherence to existing patterns, actual necessity, least-privilege execution (skills that only need to run specific executables should use argument-list invocation, not shell command strings).
- For tools: `ast.parse()` static analysis runs automatically before LLM review — detects dangerous calls, network calls to unexpected endpoints, file access outside workspace.
- Reviewer returns: approve/reject + specific concerns. Rejection loops back to builder for fixes (max 2 iterations), then fails to user with explanation.

**6. Sandbox** — Mock run before live deployment:
- Skills: Dry-run the skill instructions against a test scenario. Verify the LLM can follow the SKILL.md and produce the expected output.
- Tools: Import the module in an isolated context. Verify it initializes, responds to a test call, and does not crash. Restricted dependencies — no network, no filesystem outside temp.
- Sandbox failures loop back to builder (max 1 retry), then fail to user with diagnostic.

**7. Deployment** — Automated once review + sandbox pass:
- Extension moves to live location, git commit, gateway restart.
- User gets a brief confirmation: "Deployed [skill/tool name]. Try it out."
- Since the user already approved the proposal (step 3), no second approval gate here. The review and sandbox are the quality assurance.

**8. Audit** — Weekly review examines all extensions:
- Weekly review (Tier 4) audits every tool/skill created or modified that week.
- Checks: still needed? working correctly? any codebase conflicts? security concerns?
- Cross-references with task performance data — is the extension actually helping?
- Can recommend deprecation/removal of underperforming extensions.

**Security properties**:
- User approves before any building begins (no wasted work, no unwanted extensions)
- Builder and reviewer never share conversation context (prevents prompt injection propagation)
- Static analysis catches dangerous patterns before LLM review (defense in depth)
- Weekly audit catches regressions (continuous monitoring)
- Bias toward skills over tools (lower attack surface by default)

---

## What Successful Implementation Looks Like

### The Task Completion Test
**Success**: User texts a multi-step task from their phone. Hours later, they receive a completed deliverable with a summary of what was done. They review it and it's usable.

### The Iteration Test
**Success**: When the system can't complete a step, it doesn't fail silently or hallucinate — it reports what it tried, what went wrong, and asks a specific question. The user's answer unblocks the task.

### The Retrieval Gap (critical for task quality)
**Problem**: Qdrant recall is triggered by the *current message*. If the user asks about topic X and the relevant memory was stored under topic Y's framing, it misses.

**Success looks like**: Semantic matching via embeddings replaces keyword overlap. The system finds relevant context even when the user's phrasing doesn't match the storage framing.

### Bad Memory Correction
**Problem**: No correction mechanism exists. If the extraction pipeline writes a wrong fact to Qdrant, nothing catches it. Bad decisions persist and compound.

**Success looks like**: The nightly dream cycle and weekly audit actively identify and prune incorrect or contradictory memories. The system detects when a stored fact conflicts with new information and flags it for correction.

### Prioritization Framework (critical for proactive features)
**Problem**: Proactive capability without prioritization creates noise. 15 to-do proposals, 3 business opportunities, and 5 infrastructure decisions overwhelm the user.

**Success looks like**: Proactive outreach is batched, prioritized, and respects bandwidth. High-urgency items interrupt; everything else is consolidated into summaries. The system learns which items the user acts on vs. ignores.

### Autonomy Calibration
**Problem**: `shadow_mode: bool = True` exists in config but has no implementation. No mechanism to ask "was that the right call?" and build high-confidence lessons from real feedback.

**Success looks like**: During shadow period, the system explicitly asks for feedback after autonomous actions. Responses become calibration data. Real preferences diverge from stated preferences — shadow mode catches this.

### Memory Budget Enforcement (ongoing)
**Problem**: MEMORY.md has no guardrail against growth. Over time it accumulates project notes and verbose action items that should be in Qdrant.

**Success looks like**: MEMORY.md stays under ~400 tokens permanently. Dream-cycle check measures token count and alerts if exceeded. Overflow automatically migrates to Qdrant.

### Model Tier Matters for Metacognition
**Observation**: Opus can reason about its own architecture and identify real limitations. Haiku searched for its own logs with `ps aux` and said infrastructure "doesn't exist yet." Metacognitive tasks — self-review, lesson synthesis, direction assessment — require Tier 2+ models. This validates reserving cheap models for extraction and expensive models for judgment.

---

## Approach: Enhanced Nanobot (Approach C)

**Decision**: Evolve the existing nanobot infrastructure rather than building a new orchestration layer or adopting an external framework.

**Rationale**: The existing TaskManager, TaskWorker, SubagentManager, and shell tool are solid foundations. The decomposition logic, checkpoint system, and external CLI integration are the missing pieces — not a whole new system.

**Escape hatch**: If nanobot's architecture hits ceilings, bolt on external frameworks:
- **[CrewAI](https://github.com/crewAIInc/crewAI)**: Role-based multi-agent orchestration
- **[OpenCode](https://opencode.ai/)**: Model-flexible coding agent CLI
- **[Agent S](https://github.com/simular-ai/Agent-S)**: Computer-use agent for browser/GUI tasks
- **[MassGen](https://github.com/massgen/MassGen)**: Multi-agent parallel execution

---

## Cost Projections

| Activity | Frequency | Model Role | Est. Cost |
|---|---|---|---|
| Background extraction | Every message (~50/day) | Brainstem (free) or Haiku fallback | $0.00-0.05/day |
| Task decomposition | Per task (~5-10/day) | Thinker (frontier) | $0.25-1.50/day |
| Step execution | Per step (~20-50/day) | Workers (varies) | $0.50-3.00/day |
| Checkpoints + coordination | Per step | Coordinator | $0.05-0.20/day |
| Dream cycle + reviews | 1/day + hourly | Coordinator + Thinker | $0.10-0.30/day |
| User conversations | ~50/day mixed routing | Mix | $0.10-0.50/day |
| **Total estimate** | | | **$30-150/month** |

Higher than V1 ($5-20/month) because the system is doing work, not just chatting. Cost scales with task volume and complexity. Free-tier model routing and local models reduce this.

---

## Timezone Normalization (Infrastructure)

> **Added 2026-02-20.** Cross-cutting fix — affects dream cycle, health checks, cost alerting, ops log, status aggregator, context builder, and monitor.

### Problem

All SQL queries use `datetime('now')` / `date('now')` which return UTC. The user operates in EST/EDT (`America/New_York`). The `timezone` field exists in `CopilotConfig` but is never wired into any query or time comparison. Result: cost reports attribute spend to the wrong day, active-hours checks fire at wrong wall-clock times, morning nag triggers at 7 AM UTC (2 AM EST), and all "last N hours/days" windows are shifted by 4-5 hours.

25+ query sites affected. 15+ `CURRENT_TIMESTAMP` column defaults in `cost/db.py` schema.

### Approach

Create `nanobot/copilot/tz.py` — a thin utility module. No class, just functions.

```python
# nanobot/copilot/tz.py
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

_tz: ZoneInfo | None = None

def init(timezone_str: str) -> None:
    """Called once at startup from copilot init."""
    global _tz
    _tz = ZoneInfo(timezone_str)

def get_tz() -> ZoneInfo:
    return _tz or ZoneInfo("America/New_York")

def local_now() -> datetime:
    return datetime.now(tz=get_tz())

def local_date(offset_days: int = 0) -> date:
    return (local_now() + timedelta(days=offset_days)).date()

def local_datetime_str(offset_days: int = 0, offset_hours: int = 0, offset_minutes: int = 0) -> str:
    """ISO format string for use as SQL parameter."""
    dt = local_now() + timedelta(days=offset_days, hours=offset_hours, minutes=offset_minutes)
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def local_date_str(offset_days: int = 0) -> str:
    """Date-only string (YYYY-MM-DD) for use as SQL parameter."""
    return local_date(offset_days).isoformat()
```

**Design rules:**
- `init()` called once from `copilot/__init__.py` (or wherever copilot config loads). Reads `config.timezone`.
- Handles EDT/EST automatically via `zoneinfo.ZoneInfo` — no manual offset math.
- All helpers return Python objects or strings. SQL queries receive these as **bound parameters** — no string interpolation into SQL.
- Storage (`CURRENT_TIMESTAMP` in DDL) stays UTC. Conversion happens on read/query, not on write.

### Migration Patterns

**Pattern 1: `date('now')` / `date('now', '-1 day')` in SQL**
```sql
-- Before
WHERE date(timestamp) = date('now', '-1 day')
-- After
WHERE date(timestamp) = ?  -- bind: tz.local_date_str(offset_days=-1)
```
Files: `cycle.py` (cost report), `alerting.py` (daily total), `aggregator.py` (today's cost).

**Pattern 2: `datetime('now', '-N hours/days')` in SQL**
```sql
-- Before
WHERE timestamp >= datetime('now', '-7 days')
-- After
WHERE timestamp >= ?  -- bind: tz.local_datetime_str(offset_days=-7)
```
Files: `cycle.py` (~12 queries: lesson review, routing prefs, observation cleanup, weekly/monthly stats, dream errors, capability gaps, failure patterns, weekly review events), `ops_log.py` (7 queries), `health_check.py` (stale alerts, unresolved alerts), `aggregator.py` (weekly cost, session cutoff), `events.py` (recent heartbeat events), `cognitive_heartbeat.py` (autonomy permissions, dream log).

**Pattern 3: `datetime.now()` in Python (no tz)**
```python
# Before
now = datetime.datetime.now()
# After
from nanobot.copilot import tz
now = tz.local_now()
```
Files: `health_check.py` (active hours check — this is the critical one), `monitor.py` (morning nag hour check), `events.py` (relative time display).

**Pattern 4: `CURRENT_TIMESTAMP` in DDL / column defaults**
```sql
-- Leave as-is. Storage stays UTC.
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
```
No changes to `cost/db.py` schema. UTC storage is correct — the conversion happens at query time when filtering or displaying.

**Pattern 5: `CURRENT_TIMESTAMP` in UPDATE/INSERT statements**
```sql
-- Before
UPDATE alerts SET resolved_at = CURRENT_TIMESTAMP WHERE ...
-- Leave as-is. Write timestamps stay UTC.
```
No changes. Consistency: all stored timestamps are UTC. Only query boundaries and display shift.

### Affected Files (Exhaustive)

| File | Query count | Pattern(s) | Priority |
|------|-------------|------------|----------|
| `dream/cycle.py` | ~15 | P1, P2 | High — cost reports, lesson decay, all review stats |
| `cost/alerting.py` | 1 | P1 | High — daily cost check queries wrong day |
| `dream/health_check.py` | 3 + P3 | P2, P3 | High — active hours + alert resolution |
| `dream/monitor.py` | P3 | P3 | High — morning nag fires at wrong hour |
| `tools/ops_log.py` | 7 | P2 | Medium — ops log lookback windows |
| `status/aggregator.py` | 4 | P1, P2 | Medium — /status display |
| `context/events.py` | 1 + P3 | P2, P3 | Low — heartbeat event recency |
| `dream/cognitive_heartbeat.py` | 2 | P2 | Low — autonomy + dream log |
| `cost/db.py` | 15+ | P4 | None — leave as UTC |
| `routing/router.py` | 1 | P5 | None — leave as UTC |
| `metacognition/lessons.py` | 1 | P5 | None — leave as UTC |
| `memory/manager.py` | 1 | P5 | None — leave as UTC |
| `tasks/manager.py` | 2 | P2, P5 | None — task timeouts are relative, not wall-clock |

### Verification

1. **Cost report accuracy**: Run `_generate_cost_report()` for a known date. Confirm "yesterday" means yesterday EST, not yesterday UTC. Compare with raw `SELECT * FROM cost_log WHERE date(timestamp) = '2026-02-19'` to verify the day boundary shifted correctly.
2. **Active hours**: Set `active_hours = (7, 22)`. At 11 PM EST (4 AM UTC next day), confirm health check skips. At 7 AM EST (12 PM UTC), confirm it runs.
3. **Morning nag**: Verify `monitor.py` morning nag fires between 7-9 AM EST. Before fix: fires at 7 AM UTC = 2 AM EST.
4. **Daily cost alert**: Log a cost entry at 11 PM EST. Confirm it counts toward today's total (not tomorrow's, which is what UTC would say).
5. **Lesson decay**: Run lesson review. Confirm `-7 days` means 7 days in local time, not 7 days minus the UTC offset.

### Execution Order

1. Create `nanobot/copilot/tz.py` with helpers
2. Wire `tz.init(config.timezone)` into copilot startup
3. Fix P3 sites first (health_check.py, monitor.py active hours — user-visible bug)
4. Fix P1 sites (cost alerting, cost report — financial accuracy)
5. Fix P2 sites (remaining queries, batch by file)
6. Verify each file after fixing — run the query in isolation, check the date boundary
7. Skip P4/P5 sites (UTC storage is correct)

---

## Architecture Principles (Updated)

1. **Task-first** — every feature serves the task lifecycle
2. **Thin hooks, fat modules** — copilot logic in `nanobot/copilot/`, agent loop changes minimal
3. **Right model for the role** — thinker decomposes, coordinator manages, workers execute
4. **Asynchronous by default** — user doesn't babysit, system reports progress
5. **Iterative delivery** — show progress, ask questions, incorporate feedback
6. **Graceful degradation** — every component has a fallback
7. **Learn from outcomes** — every task completion is a training signal
8. **Executive, not employee** — user decides what, system figures out how
9. **LLM-aware capabilities** — every tool, feature, or capability must be documented in the system prompt context (`capabilities.md`, `agents.md`, `TOOLS.md`). A tool the LLM doesn't know about is a tool that doesn't exist. Let the LLM decide when and how to use capabilities — don't build programmatic interceptors that override its judgment (lesson learned from the approval system failure and the V2.1 task detection redesign).
10. **Recursive self-review** — the system reviews its own work at every tier. Heartbeat catches dropped threads. Orchestrator evaluates worker output inline and reviews its own decisions in retrospective. Dream cycle reviews orchestrator patterns and system-level value delivery. Weekly review audits the review mechanisms themselves. Each tier reviews the tier below it. See "Recursive Self-Review" under Operational Intelligence for the full hierarchy.
11. **LLM-first design** — prefer LLM judgment (soul file guidance, better prompts, identity file updates) over programmatic guardrails for decision-making. Reserve code for structural concerns: timeouts, data validation, event wiring, concurrency. The LLM is always the pilot. This is the same principle that killed the approval system — don't build code that overrides LLM judgment.
