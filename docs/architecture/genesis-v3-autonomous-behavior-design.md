# Genesis v3: Autonomous Behavior Architecture — Design Document

## Context

The current nanobot system runs 6+ independent timer-based services (heartbeat, dream cycle, health check, monitor, weekly/monthly reviews, recon cron jobs) that are fragmented, uncoordinated, and calendar-rigid. This document defines the replacement architecture for Genesis on Agent Zero: a unified, adaptive system informed by neuroscience and grounded in practical constraints.

**This is a design document, not an implementation plan.** It captures architectural decisions for the Genesis repo. Implementation planning happens when the Agent Zero container is ready.

**Design inputs:**
- Current nanobot periodic services and their limitations
- Genesis v3 dual-engine plan (Agent Zero + Claude SDK + OpenCode)
- User's prior AGI Prototype specification (drive primitives, world model, constitutional checks, procedural memory, phased capability)
- Neuroscience functional mapping (used as thinking tool, not deployment blueprint)
- Brainstorming session on proactive outreach, anticipatory intelligence, and feedback loops

**Companion document:** `genesis-v3-dual-engine-plan.md` covers framework decision
(why Agent Zero), three-engine architecture, memory system MCP wrapping, CLAUDE.md
handshake protocol, migration plan, container architecture, and risk assessment.
This document covers the cognitive/autonomous behavior layer that runs on top of
that foundation.

**Core design principle:** The brain has separate modules because evolution couldn't refactor the brainstem. We don't have that constraint. Keep the cognitive FUNCTIONS from neuroscience, simplify the DEPLOYMENT. If something doesn't need its own process, state, and lifecycle, it's a prompt pattern or internal instrument — not a server.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      AGENT ZERO CORE                         │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  AWARENESS LOOP (Extension)                5min tick   │  │
│  │  Programmatic. No LLM. Monitors signals, applies       │  │
│  │  calendar floors/ceilings, triggers Reflection Engine.  │  │
│  └───────────────────────┬────────────────────────────────┘  │
│                          │ triggers                           │
│  ┌───────────────────────▼────────────────────────────────┐  │
│  │  REFLECTION ENGINE (Extension)         Adaptive depth  │  │
│  │  LLM-driven. Micro → Light → Deep → Strategic.         │  │
│  │                                                         │  │
│  │  Inline capabilities (prompt patterns):                 │  │
│  │  • Salience evaluation                                  │  │
│  │  • User model synthesis                                 │  │
│  │  • Social simulation ("imagine user reaction")          │  │
│  │  • Governance check (permissions, budget, reversibility)│  │
│  │  • Drive weighting (curiosity/competence/cooperation/   │  │
│  │    preservation)                                        │  │
│  └───────────────────────┬────────────────────────────────┘  │
│                          │ learns from                        │
│  ┌───────────────────────▼────────────────────────────────┐  │
│  │  SELF-LEARNING LOOP (Extension)    After interactions  │  │
│  │  The "Dopaminergic System": task retrospectives,        │  │
│  │  engagement tracking, drive weight adjustment,          │  │
│  │  procedural memory extraction, prediction error logging │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│                      4 MCP SERVERS                            │
│                                                              │
│  memory-mcp              recon-mcp                           │
│  ├ Episodic memory       ├ Email reconnaissance              │
│  ├ Semantic memory       ├ Web source monitoring             │
│  ├ Procedural memory     ├ GitHub / model landscape          │
│  ├ Observations          ├ Source discovery                   │
│  └ User model cache      └ Self-scheduling                   │
│                                                              │
│  health-mcp              outreach-mcp                        │
│  ├ Software error rates  ├ Channel registry (WhatsApp, web)  │
│  ├ Provider/API status   ├ Delivery queue + timing           │
│  ├ Process health        ├ Engagement tracking               │
│  └ Storage limits        └ Digest generation                 │
└──────────────────────────────────────────────────────────────┘
```

---

## Layer 1: Awareness Loop

**Replaces:** MonitorService + HealthCheckService polling logic
**Type:** Agent Zero extension, 5-minute tick
**Cost:** Zero LLM calls — purely programmatic signal collection

The Awareness Loop is pure perception — it collects signals and decides which depth of reflection to trigger. It does NOT reason about signals or take actions. All reasoning, even the lightest kind, belongs to the Reflection Engine (starting at Micro depth).

### Responsibilities

- Collect signals from MCP servers (pending notifications, error counts, engagement data, recon findings)
- Track event counters since last reflection (conversations, errors, memories stored, findings)
- Run lightweight programmatic health checks (process alive? API responding? storage within bounds?)
- Check time-since-last-reflection at each depth level
- Apply calendar floor/ceiling schedule (see below)
- When thresholds crossed → trigger Reflection Engine at appropriate depth
- Process escalation flags from previous Reflection Engine runs (see Depth Escalation Protocol below)

### Depth Escalation Protocol

The Awareness Loop is the SOLE authority that invokes the Reflection Engine. But Reflection Engine runs can flag that a deeper pass is warranted (e.g., Micro discovers a pattern that needs Light-depth analysis). The protocol:

1. Reflection Engine sets an **escalation flag** with target depth and reason (stored in extension state, not MCP)
2. Awareness Loop checks escalation flags on its NEXT tick (max 5-minute delay)
3. If flag is set and target depth isn't on cooldown → trigger that depth
4. **Critical escalation override:** If the Reflection Engine flags `critical=true` (e.g., cascading failure pattern), the Awareness Loop runs an immediate out-of-cycle tick. This is the ONLY case where the 5-minute interval is bypassed.

**Why this matters:** Without this protocol, either the Awareness Loop is the single coordinator (but can't respond to escalations faster than 5 minutes) or the Reflection Engine can self-trigger (but then you have two scheduling authorities). This gives clean ownership with a safety valve.

### Hybrid Scheduling: Event-Driven + Calendar Guardrails

Events set the tempo, calendar sets the minimum BPM.

| Depth | Event-driven trigger | Calendar floor | Calendar ceiling |
|-------|---------------------|----------------|-----------------|
| **Micro** | Software anomaly, new user interaction pattern, quick improvement idea | Every 30min | Max 2/hour |
| **Light** | Notable activity (5+ conversations, budget warning, recon finding flagged) | Every 6h | Max 1/hour |
| **Deep** | Backlog / salience spike (200+ unprocessed memories, budget alert, multiple recon findings) | Every 48-72h | Max 1/day |
| **Strategic** | Major signal (user goal change, paradigm shift in recon, quarterly boundary) | Every 7-14 days | Max 1/week |

**Adaptive floors:** Quiet periods tighten floors (more likely something was missed). If the system has been consistently event-triggering Deep reflections every 18h, the 72h floor is irrelevant. But if there's a quiet stretch, the floor tightens to 48h — because silence is MORE likely to need a "did I miss something?" check, not less.

**Why calendar floors matter:** Purely event-driven misses drift. If nothing crosses a salience threshold for 3 weeks, the system never asks "why has nothing been important? Have my models gone stale? Has the user's life changed?"

---

## Layer 2: Reflection Engine

**Replaces:** HeartbeatService, CopilotHeartbeatService, DreamCycle (13 jobs), weekly review, monthly review
**Type:** Agent Zero extension, triggered by Awareness Loop
**Cost:** Variable per depth (Micro = near-zero via local 20-30B or Gemini Flash free tier, Light = low, Deep = medium, Strategic = high)

### Depth Levels

**Micro** (quick sanity pass):
- Cheap LLM call: local 20-30B model or free cloud tier (Gemini Flash)
- NOT a health monitor. The question Micro answers is: "Anything worth paying attention to right now?"
- Biased toward: user value opportunities ("user asked about X yesterday, I found related info"), self-improvement ideas ("that task failed because of Y, I should note the pattern"), software anomaly detection ("API error rate spiked", "gateway returned malformed JSON", "config value looks wrong")
- Hardware health is NOT Micro's focus — the Awareness Loop catches the rare hardware issue (storage limits) programmatically. Micro thinks about software reliability, user needs, and system improvement.
- Output: brief observations, optional flag for Light reflection if something warrants deeper thought

**Light** (replaces heartbeat):
- Brief LLM reflection on recent activity
- Queries memory-mcp for recent events, recon-mcp for new findings, health-mcp for status
- Runs inline salience evaluation: "Of these signals, which are worth acting on?"
- Runs inline user model synthesis: "Given recent interactions, update user profile"
- May trigger outreach for high-salience items
- Output: observations written to memory, possible outreach queued

**Deep** (replaces nightly dream cycle):
- Comprehensive review, **but only runs jobs that have pending work**
- Memory consolidation → only if unprocessed backlog exists
- Cost reconciliation → only if spend changed since last check
- Lessons extraction → only if new retrospectives exist
- Identity reflection → only if observations warrant SOUL.md consideration
- Recon triage → only if new findings exist
- Observation cleanup → only if stale observations accumulate
- Output: consolidated memories, updated observations, drive weight adjustments

**Strategic** (replaces weekly + monthly reviews):
- MANAGER role (weekly cadence): architecture review, memory quality, recon triage, cost analysis
- DIRECTOR role (monthly cadence): audits weekly findings, adjusts budgets, strategic assessment
- **Can modify system parameters:** adjust Awareness Loop thresholds, Reflection Engine drive weights, outreach preferences
- **Capability gap review:** Reviews accumulated capability gaps since last Strategic. For each: (1) How many times was this gap hit? (2) What would it take to close it (new tool, MCP integration, skill)? (3) Is the investment justified by frequency and user impact? Proposes capability acquisitions for user approval (L5+ autonomy).
- Output: strategic adjustments, configuration changes, high-level observations, capability acquisition proposals

Strategic reflections track an internal counter. Every Strategic reflection runs MANAGER-scope work. Every 4th Strategic reflection (or when >28 days since last DIRECTOR pass) also runs DIRECTOR-scope work. This gives roughly weekly MANAGER and monthly DIRECTOR cadence while keeping them in a single depth level.

### Inline Capabilities (Prompt Patterns)

These are NOT separate servers. They're sections of the Reflection Engine's prompt that are activated at appropriate depths:

**Salience Evaluation:**
> "Given these signals, the current user model, and recent engagement data (last 10 outreach events: 7 engaged, 3 ignored — topics ignored were...), score each signal on relevance (0-1), urgency (0-1), and actionability (0-1). Which cross the threshold for outreach?"

**User Model Synthesis:**
> "Query memory for recent interactions. Synthesize into structured profile: current interests, active skills, behavioral patterns, stated goals, communication preferences, inferred blind spots. Compare against cached profile — what changed?"

**Social Simulation (World Model):**
> "Before sending this outreach message, simulate the user's reaction. Given their profile [user model], if they received: '[draft message]' — would they find it (a) valuable and act on it, (b) interesting but not actionable, (c) irrelevant/annoying? Adjust or suppress based on simulation."

**Governance Check (Constitutional):**
> "This action was proposed by [source]. Check: (1) Does it align with user's autonomy permissions for this category? (2) Is it reversible? (3) Is it within budget? (4) Has the user previously rejected similar actions? If any answer fails, hold for user approval."

**Drive Weighting:**
Four drives shape what the Reflection Engine focuses on:
- **Curiosity:** Explore new information, investigate unknowns
- **Competence:** Improve at things done often, optimize procedures
- **Cooperation:** Help the user proactively, surface opportunities
- **Preservation:** Maintain system health, manage resources

Weights are initial-configured but adjusted by the Self-Learning Loop based on feedback. If proactive suggestions keep getting acted on → cooperation weight rises. If the system keeps breaking → preservation weight rises.

**Bounds:** No single drive may drop below 0.10 or rise above 0.50. This prevents any drive from being effectively silenced or from dominating all reflection. Initial weights: preservation 0.35, curiosity 0.25, cooperation 0.25, competence 0.15.

**Normalization:** Drive weights are **independent sensitivity multipliers**, NOT a normalized budget that must sum to 1.0. "Preservation at 0.45" means health signals weigh 0.45x in reflection focus. This can coexist with "cooperation at 0.40" without conflict. If drives were normalized (zero-sum), raising one would necessarily lower others — preventing the system from responding to "I need more preservation AND more cooperation" simultaneously. The initial values happen to sum to 1.0 but this is coincidental, not a constraint.

---

## Layer 3: Self-Learning Loop

**Replaces:** Task retrospectives, lessons-learned extraction, post-mortem pipeline
**Type:** Agent Zero extension, runs after interactions and outreach events
**This IS the "Dopaminergic System" — learning from prediction errors**

### After Every Interaction

1. **Task retrospective:** What was attempted? What succeeded/failed? What was surprising? → store in memory-mcp (episodic)
2. **Root-cause classification:** Categorize the outcome to route feedback correctly:
   - `approach_failure` — Genesis tried an approach that didn't work. Feeds procedural memory adjustment (update procedure confidence, record failure mode).
   - `capability_gap` — Genesis lacked a tool, integration, or skill needed for the task. Does NOT penalize procedural memory. Logged to a capability gap accumulator for Strategic reflection review (see Capability Expansion in Loop Taxonomy).
   - `external_blocker` — Something outside Genesis's control blocked the task (user decision needed, API down, permission denied). Categorized further: (a) user-rectifiable (surface to user as a blocker), (b) current technology limitation that may become feasible later (parked as a future capability gap with a `revisit_after` date), (c) permanent constraint (logged, no action).
   - `success` — Task completed. Feeds procedural memory confidence increase.
3. **Lessons extraction:** Any reusable procedures learned? → store in memory-mcp (procedural). Only `approach_failure` and `success` outcomes update existing procedure confidence. `capability_gap` and `external_blocker` do not — the system shouldn't "learn" that it's bad at tasks it simply can't do yet.
4. **Prediction error logging:** "Expected X, got Y" → used by Reflection Engine to calibrate future expectations

### After Every Outreach Event

1. **Engagement tracking:** Store in outreach-mcp: `{signal_type, topic, salience_score, channel, delivered_at, opened_at, user_response, action_taken}`
2. **Prediction error:** `salience_score` predicted engagement. Actual engagement was higher/lower. Compute error.
3. **Drive weight adjustment:** Positive engagement on cooperation-driven outreach → increase cooperation weight. Ignored outreach → decrease.
4. **Salience calibration:** "Outreach about topic X at score 0.78 was ignored → adjust threshold for similar topics"

### Engagement Signal Heuristics (Per-Channel)

Engagement inference is the primary training signal for salience calibration.
Default heuristics (per-adapter, overridable):

| Channel | "Engaged" | "Ignored" | "Neutral" |
|---------|-----------|-----------|-----------|
| WhatsApp | Reply or read receipt + action within 4h | No read receipt in 24h, OR read but no reply to a question in 12h | Read receipt but no reply on non-question within 24h |
| Telegram | Reaction or reply | No reaction or reply in 24h | Message read (if available) but no reaction |
| Web UI | Click-through, reply, or explicit feedback button | Page loaded but no interaction in session | Viewed in digest but no action |

These heuristics are initial defaults. The Self-Learning Loop can propose adjustments (L6 autonomy — user-approved) if engagement patterns suggest the heuristics are miscalibrated.

### Over Time

This loop makes proactive behavior increasingly accurate:
- **Month 1:** Conservative. High thresholds. Mostly reactive with occasional blocker/alert outreach.
- **Month 3:** Calibrated. Engagement data has shaped salience thresholds. Finding/insight outreach begins to land.
- **Month 6+:** Anticipatory. Rich user model + calibrated drives + procedural memory = can identify opportunities the user hasn't thought of.

---

## 4 MCP Servers

### 1. memory-mcp

**Existing design from v3 plan, expanded with:**
- **Procedural memory type:** Structured "how-to" records, not narratives. Schema: `{task_type, steps[], tools_used[], success_rate, failure_modes[], context_tags[], last_used, times_used}`
- **Observations:** Folded in from the separate genesis-observations concept. Observations are processed reflections — a form of memory, not a separate concern.
- **User model cache:** Periodically synthesized user profile stored as a semantic record, refreshed by Reflection Engine during Light+ reflections.

**Memory tools:**
- `memory_recall` — Hybrid search (Qdrant vectors + FTS5 full-text, RRF fusion). Accepts `source` param: `memory | knowledge | both`
- `memory_store` — Store with source metadata + memory type tag
- `memory_extract` — Store fact/decision/entity extractions
- `memory_proactive` — Cross-session context injection
- `memory_core_facts` — High-confidence items for system prompts
- `memory_stats` — Health and capacity metrics
- `observation_write` — Write processed reflection/observation
- `observation_query` — Query by type/priority/source
- `observation_resolve` — Mark resolved with notes
- `evolution_propose` — Write identity evolution proposal (for SOUL.md / identity file changes)

**Knowledge base tools (post-v3 feature, groundwork laid in v3):**
- `knowledge_recall` — Hybrid search scoped by project/domain, authority-tagged results
- `knowledge_ingest` — Store distilled knowledge units with full provenance metadata
- `knowledge_status` — Collection stats, staleness report, project index

**Knowledge base concept:** A separate-but-colocated data layer for **immutable reference material** — course content, specs, reference docs — that Genesis treats as authoritative source of truth (not subject to memory consolidation, decay, or revision). Distilled by LLM into structured knowledge units before storage. Primary consumers are background agents, task execution sub-agents, and the Self-Learning Loop audit trail — not main conversation context injection (avoids context window budget pressure). See `post-v3-knowledge-pipeline.md` in project docs for full design.

> **V3 groundwork requirements (implement during v3, not post-v3):**
> - Retrieval interface accepts `source` parameter (`memory | knowledge | both`)
> - Qdrant client wrapper supports multiple named collections (not hardcoded to `episodic_memory`)
> - Context injection tags each block with `source_type` so the LLM distinguishes recalled memory from reference material
> - Token budget system for context injection is shared across memory AND knowledge retrieval
> - Raw text stored alongside vectors in knowledge collection (enables re-embedding on model change without re-ingestion)
> - FTS5 table schema supports a `collection` column for knowledge vs memory separation
>
> These are design decisions, not extra code: an enum instead of a hardcoded string, a collection name parameter instead of a constant, a `source_type` field on injected blocks.
>
> **Why knowledge lives in memory-mcp, not a separate server:** Applying the same test used
> to reject other servers: "Does this need its own process, persistent state, and lifecycle?"
> No. Knowledge shares infrastructure (Qdrant, embedder, FTS5, SQLite pool) and retrieval
> patterns (hybrid search, RRF fusion). It needs its own Qdrant collection, FTS5 table, and
> retrieval filter — not its own process.

### 2. recon-mcp

**Existing design from v3 plan.** Self-scheduling intelligence gathering:

| Job | Schedule | Source |
|-----|----------|--------|
| Email reconnaissance | Daily 5AM | Configured email sources |
| Web source monitoring | Friday 6AM | Configured URLs/feeds |
| GitHub landscape | Saturday 6AM | Repos, releases, trends |
| Model intelligence | Sunday 6AM | Provider announcements, benchmarks |
| Source discovery | Monthly | Discover new relevant sources |

Self-manages schedules internally. Pushes high-priority findings as notifications to Awareness Loop. Low-priority findings accumulate for triage during Deep/Strategic reflections.

**Tools:**
- `recon_findings` — Query/store findings
- `recon_triage` — Mark findings triaged with notes
- `recon_schedule` — View/modify gathering schedule
- `recon_sources` — Manage watched sources

### 3. health-mcp

**New.** Lightweight software health awareness — NOT an enterprise monitoring system. Genesis is a cognitive assistant that happens to be self-maintaining, not a sys admin. Health monitoring exists so Genesis can fix its own problems when they arise, not so it can spend cycles worrying about uptime.

**Focus: software reliability** (the real failure modes):
- **API/provider status:** Which APIs are responding? Which are returning errors? Which are rate-limited? (Crashes, dead APIs, and non-graceful degradation are the #1 real-world failure mode)
- **Error tracking:** Rolling window of errors with pattern detection — malformed JSON, config issues, unexpected exceptions, gateway crashes
- **Process health:** Are background services running? Did something crash silently?
- **Storage:** The one hardware check that matters — disk usage approaching limits (backups, logs, DB growth)

**NOT in scope:** CPU monitoring, memory profiling, network throughput, latency histograms, baseline learning for statistical deviation. This isn't Datadog. If something breaks, Genesis notices and fixes it. If nothing breaks, health-mcp is quiet.

**Tools:**
- `health_status` — Current system health snapshot (API status, error counts, process state, storage)
- `health_errors` — Recent error log with pattern grouping
- `health_alerts` — Active alerts (software failures, storage warnings)

### 4. outreach-mcp

**New.** Manages all proactive communication with the user:

- **Channel registry:** Pluggable adapter pattern. Initial channels: WhatsApp, Telegram, Agent Zero web UI. Channels are registered dynamically — adding Telegram, Slack, email, etc. requires only a new adapter, not architecture changes. No hardcoded "primary" — the system learns which channel the user prefers for which outreach type over time.
- **Delivery queue:** Messages queued with urgency level, preferred timing, and channel override
- **Quiet hours:** User-defined "don't disturb" windows (e.g., 10PM–7AM)
- **Engagement tracking:** Per-message: delivered → opened → responded → acted_on (or ignored). WhatsApp read receipts + reply detection.
- **Digest generation:** Batch low-priority items into periodic summaries (daily or weekly, user-configurable)
- **Feedback mechanism:** Channel-appropriate. Telegram: reaction buttons (👍/👎). WhatsApp: reply-based ("Reply 👍 or 👎"). Web UI: native UI elements. All channels also infer from engagement patterns (acted on = positive, ignored = negative). The adapter interface defines `get_engagement_signals()` so each channel reports feedback in its native way.

**Tools:**
- `outreach_send` — Queue a message for delivery
- `outreach_queue` — View pending messages
- `outreach_engagement` — Query engagement history (for Self-Learning Loop)
- `outreach_preferences` — Get/set user channel preferences and quiet hours
- `outreach_digest` — Generate a digest of queued low-priority items

---

## Why 4 MCP Servers, Not 7

We considered 7 (adding user-model, tasks, salience as servers). Each was rejected against the test: "Does this need its own process, persistent state, and lifecycle?"

| Rejected Server | Why Not |
|----------------|---------|
| **user-model-mcp** | No independent state. It's a SYNTHESIS from memory-mcp queries. The LLM builds the profile inline during reflection. A server would just be a caching layer in front of memory with sync complexity. |
| **tasks-mcp** | Agent Zero has native task management. A separate MCP server duplicates framework capability. |
| **salience-mcp** | It's an LLM evaluation (a prompt), not a service. The inputs (signals + user model + engagement data) come from other servers. The output (scores) is ephemeral. No persistent state to manage. |
| **observations-mcp** | Observations are a type of memory (processed reflections). Folded into memory-mcp with a type tag. |
| **knowledge-mcp** | Knowledge is stored information with different lifecycle rules (immutable, project-scoped, no decay) but shares all infrastructure (Qdrant, embedder, FTS5, SQLite pool) and retrieval patterns (hybrid search, RRF). Needs its own collection and filter, not its own process. Folded into memory-mcp as a namespace. |

---

## Proactive Outreach: From Reactive to Anticipatory

### The Three Capabilities

**1. Triage Autonomy — "I can handle this" vs "I need the human"**

The Governance Check prompt pattern in the Reflection Engine evaluates every potential autonomous action:
- Per-category autonomy permissions (inherited from nanobot's design)
- Reversibility assessment (can this be undone without user?)
- Budget check (within allocated spend?)
- Precedent check (has user previously approved/rejected similar?)

Actions within permissions → execute silently. Actions outside → queue in outreach-mcp for user decision.

**2. Proactive Escalation — "You need to know about this"**

Triggered by Awareness Loop + Reflection Engine when signals are urgent:
- System health alerts (provider down, budget exceeded)
- Blockers (task needs user decision to proceed)
- Time-sensitive findings (recon item with expiration)

These bypass normal salience evaluation — urgency overrides.

**3. Anticipatory Intelligence — "You don't know it yet, but you need this"**

The hardest and most valuable capability. Requires:
- Rich user model (interests, skills, goals, patterns, blind spots)
- Cross-referencing new information against that model
- Social simulation (will the user find this useful?)
- Feedback loop calibration (has similar outreach been valued before?)

Example flow:
```
recon-mcp finds new AI framework gaining traction
  → Reflection Engine (Light depth):
      Salience: user builds AI tools, active project could benefit → 0.82
      User model: user evaluated similar tool 3 months ago
      Simulation: "user would likely find this useful given current project"
      Governance: cooperation-type outreach, within permissions
  → outreach-mcp:
      Channel: WhatsApp (medium urgency)
      Timing: next morning (not urgent enough to interrupt)
      Message: "Saw [framework] gaining traction — could solve the [problem]
               in your [project]. Want me to evaluate it?
               (👍 / 👎)"
  → User replies 👍
  → Self-Learning Loop: positive engagement on recon-tech topic at 0.82
      → slightly lower threshold for similar topics next time
```

### Outreach Categories

| Type | Trigger | Urgency | Channel | Example |
|------|---------|---------|---------|---------|
| **Blocker** | Task needs user decision | Immediate | Preferred push channel | "I need approval to proceed with X" |
| **Alert** | Health/budget threshold | High | Preferred push channel | "API costs 40% over weekly budget" |
| **Finding** | Recon + salience passes threshold | Medium | Learned channel or digest | "New framework relevant to your project" |
| **Insight** | Reflection Engine pattern detection | Medium-low | Next session or digest | "You've built 3 similar pipelines — template?" |
| **Opportunity** | Cross-reference: user model + new info + capability | Low | Next session or digest | "Based on your skills + goals, high-leverage idea: ..." |
| **Digest** | Scheduled batch | Low | Learned channel (Telegram/WhatsApp/email) | "Here's what happened while you were away" |

Channel selection is learned, not prescribed. The system tracks which channel gets the fastest/most-positive engagement per outreach type and gravitates toward it. User can also set explicit preferences ("alerts always go to WhatsApp, digests go to Telegram").

---

## What We Took from the AGI Spec

| AGI Spec Concept | How It Maps to Genesis | Where It Lives |
|-----------------|----------------------|----------------|
| **Drive primitives** (curiosity, competence, cooperation, preservation) | Drive weighting system that shapes Reflection Engine focus | Reflection Engine prompt + Self-Learning Loop feedback |
| **World Model / Imagination Engine** | Social simulation — "imagine user's reaction before sending outreach" | Reflection Engine prompt pattern |
| **Constitutional Subagent** | Governance check — permissions, reversibility, budget, precedent | Reflection Engine prompt pattern |
| **Procedural Memory** | Structured "how-to" records alongside episodic/semantic | memory-mcp (new memory type) |
| **Phased training curriculum** | Bootstrap sequence: observe → react → light proactive → anticipatory | Deployment phasing (see Bootstrap below) |
| **Survival Subagent** | health-mcp (software health, reactive) + Awareness Loop signal collection | MCP server + internal extension — self-maintenance, not self-monitoring |
| **Ego/Meta-Controller** | Agent Zero core + Awareness Loop + Reflection Engine | Framework + extensions |
| **Audit & Explainability** | Memory-stored retrospectives + engagement logs | memory-mcp + outreach-mcp |

**Rejected from spec:** Perception/sensorium (text-only context), RL core (LLM is the policy), simulation environments (Unity/MuJoCo irrelevant), HSM/multi-sig quorum (overkill for personal assistant), formal verification (impractical for LLM systems), training curricula (orchestrating pretrained models, not training).

---

## Bootstrap / Cold Start Strategy

### Phase 1: Observation (Weeks 1-2)
- All autonomous behavior active, outreach DISABLED
- Reflection Engine runs at all depths, builds user model from conversations
- Recon gathers findings but doesn't surface them
- Engagement tracking has no data — use conservative salience thresholds (0.9+)
- System learns normal patterns (health baselines, conversation frequency, topic distribution)

### Phase 2: Light Proactive (Weeks 3-4)
- Enable blocker + alert outreach (high-confidence, low noise risk)
- Begin digest generation (weekly summary of activity + recon)
- User model has initial shape → start finding outreach with high threshold (0.85+)
- First feedback data from engagement tracking begins calibrating

### Phase 3: Full Proactive (Month 2+)
- Lower outreach thresholds as engagement data accumulates
- Enable insight suggestions (pattern detection from user behavior)
- Drive weights have initial calibration from feedback loop

### Phase 4: Anticipatory (Month 3+)
- Enable opportunity suggestions (highest value, highest noise risk)
- Rich user model + calibrated drives + procedural memory
- System can explain WHY it's suggesting something
- Can identify things the user doesn't know they need

**Optional accelerator:** Explicit onboarding questionnaire — "What are your current goals? What topics interest you? How often do you want proactive messages? What's too noisy?" This front-loads user model data that would otherwise take weeks to observe.

---

## Neuroscience Mapping (Thinking Tool)

This mapping informed the architecture but doesn't dictate deployment:

| Brain System | Function | Genesis Equivalent |
|-------------|---------|-------------------|
| Reticular Activating System | Filter input, decide what reaches consciousness | Awareness Loop (extension) |
| Default Mode Network | Idle processing, creativity, self-reflection | Reflection Engine at Deep/Strategic (extension) |
| Salience Network | "Is this important?" switching | Salience evaluation (prompt pattern in Reflection Engine) |
| Hippocampus | Memory encoding, consolidation, pattern completion | memory-mcp |
| Mirror Neurons / Theory of Mind | Model other minds, predict needs | User model synthesis (prompt pattern, data in memory-mcp) |
| Insular Cortex | Internal state awareness | health-mcp (software health, not hardware) |
| Anterior Cingulate | Error/conflict detection | health-mcp error pattern detection |
| Basal Ganglia | Habits, routines, learned procedures | Procedural memory (memory type in memory-mcp) |
| Dopaminergic System | Reward prediction error, learning what's valuable | Self-Learning Loop (extension) |
| Prefrontal Cortex | Executive function, planning, impulse control | Agent Zero core (LLM) |
| Amygdala | Emotional valence, urgency tagging | Part of salience evaluation |
| Cerebellum | Automated skills, practiced routines | Agent Zero instruments/tools |

---

## Comparison: Current (Nanobot) vs. Genesis v3

| Aspect | Current (6+ independent services) | Genesis v3 (3 layers + 4 MCP) |
|--------|----------------------------------|-------------------------------|
| **Scheduling** | Fixed intervals per service (2h, 30min, 5min, nightly, weekly, monthly) | Event-driven with adaptive calendar floors/ceilings |
| **Coordination** | `is_running` mutex flag (hack) | Awareness Loop is single coordinator |
| **Depth** | Fixed — dream cycle runs all 13 jobs every night | Adaptive — only runs jobs with pending work |
| **Feedback** | None — weekly doesn't influence daily behavior | Self-Learning Loop adjusts drives, thresholds, salience |
| **Proactive outreach** | None — user must check in | WhatsApp push, engagement-calibrated |
| **User modeling** | None | Synthesized from memory, used for salience + simulation |
| **Cognitive focus** | Fragmented across 6 services, health-check-heavy | User value + self-improvement dominant, health reactive-only |
| **Adding new behavior** | New service class + wiring + interval + contention management | New prompt section in Reflection Engine or new MCP tool |
| **Procedural learning** | Narratives in episodic memory | Structured procedural records, directly retrievable |
| **World model** | None | Social simulation (imagine user reaction) |
| **Governance** | Autonomy permissions (per-category flags) | Governance check (permissions + reversibility + budget + precedent) |

---

## Task Execution Architecture: The Invisible Orchestrator

### The Core Abstraction

The user says "do X." Genesis figures out everything else — invisibly. Whether X requires a simple tool call, multi-file code editing via Claude SDK, browser automation, computer use, or a combination of all four, the user never thinks about which engine did it. They just get the result.

This is NOT a new system on top of Agent Zero. It's how Agent Zero's multi-agent orchestration already works, enhanced by Genesis's cognitive layer.

### How Execution Flows

```
User: "Do X"
         │
         ▼
Genesis (main agent): Planning pass
  "This requires capabilities: [code editing, web browsing, UI interaction]"
  "Sequence: first browse to gather info, then write code, then test in browser"
  "Memory: retrieved 2 similar past tasks, procedural memory says do A before B"
         │
         ▼
Genesis spawns subordinate agents as needed:
  ├── Sub-agent 1: browser_tool for information gathering
  ├── Sub-agent 2: claude_code tool for code writing (or opencode_fallback if rate-limited)
  └── Sub-agent 3: computer_use for UI testing
         │
         ▼
Quality gate: Did sub-agents produce correct outputs?
  "Review code against requirements"
  "Verify browser found what we needed"
  "Test results match expected behavior"
         │
         ▼
Memory integration: Store execution trace
  Episodic: what happened, what was tried, what succeeded
  Procedural: if novel approach worked, extract as reusable procedure
  Retrospective: lessons for the Self-Learning Loop
         │
         ▼
Result delivered to user (clean, no implementation details exposed)
```

### Complex Situations Genesis Must Handle

**Mid-task discovery changes the plan:**
"Write a Python API wrapper for X" → Claude SDK finds X's API is undocumented → Genesis pauses, uses browser tool to scrape docs, updates CLAUDE.md with findings → resumes Claude SDK session with new context. No user involvement needed unless discovery reveals a blocker requiring a decision.

**Mixed capability task:**
"Build and test a web scraper for Y" → Plan: browser tool to understand target structure, Claude SDK to write the scraper, computer use to run it and verify output in a terminal UI, Claude SDK again to fix any issues. Coordinated transparently.

**Tool failure mid-execution:**
Claude SDK hits rate limit during a multi-step refactor → Genesis resumes the session on Bedrock fallback → if all Claude paths fail, switches to OpenCode → stores the failure and fallback path in procedural memory so future similar tasks route better from the start.

**Blocker requiring user input:**
Task reaches a decision point that genuinely requires the user ("I found two ways to architect this, each with real trade-offs"). Genesis surfaces the decision via outreach-mcp with enough context to decide quickly, parks the task, resumes when the user responds.

**Computer use + code in sequence:**
"Update my Notion dashboard with our new metrics" → computer use to navigate Notion UI and understand current structure → Claude SDK to write a Python script that automates the update → computer use again to verify the script ran correctly. Entirely autonomous unless it hits permissions.

### What the Backend Must Ensure (Invisibly)

The "make it happen" abstraction requires these always-on behaviors behind the scenes:

1. **Governance at every capability boundary** — Before spawning a sub-agent that uses computer use or external APIs, governance check: is this action within autonomy permissions? Is it reversible? Is it within budget? If no → surface to user first.

2. **Memory continuity across sub-agents** — Each sub-agent's output is stored in memory. If a sub-agent fails and a new one is spawned to retry, the new one retrieves context from the failed attempt. No starting from scratch.

3. **Quality gates, not just completion** — "Claude SDK returned code" ≠ task done. Quality gate checks: does it run? does it meet the stated requirements? does it follow the project's patterns (from procedural memory)? A task that produces bad output isn't complete.

4. **Budget tracking per task** — Every tool call, every token, every sub-agent spawn is tracked against the task's budget. When approaching the limit, Genesis either optimizes (use cheaper models for remaining steps) or surfaces to user.

5. **Transparent audit trail** — The user can always ask "what did you do?" and get a coherent explanation. The execution trace is stored in memory-mcp as an episodic record.

6. **Graceful degradation** — If a preferred tool is unavailable, Genesis routes to the next best option. The routing chain is cost-aware: routine code → OpenCode, complex code → Claude CLI subprocess (subscription) → Claude SDK API (with cost notification) → Bedrock/Vertex → OpenCode fallback.

### Execution Trace Schema

Every task execution is stored in memory-mcp as an episodic record:

```json
{
  "task_id": "task_abc123",
  "user_request": "Build and test a web scraper for Y",
  "plan": ["browser: understand target structure", "claude_code: write scraper", "computer_use: verify output"],
  "sub_agents": [
    {"type": "browser", "input": "...", "output": "...", "status": "success", "cost_usd": 0.02, "duration_s": 45},
    {"type": "claude_code", "input": "...", "output": "...", "status": "success", "cost_usd": 0.34, "session_id": "sess_xyz"},
    {"type": "computer_use", "input": "...", "output": "...", "status": "failed", "error": "permission denied"}
  ],
  "quality_gate": {"passed": false, "reason": "computer_use failed — permission issue", "action": "surfaced to user"},
  "total_cost_usd": 0.36,
  "procedural_extractions": ["proc_def456"],
  "retrospective_id": "retro_ghi789"
}
```

### Governance at Capability Boundaries

Before spawning any sub-agent, a programmatic check runs (not LLM — too slow for every spawn):

1. Check autonomy permissions for the capability type (code_edit, browser, computer_use, external_api)
2. Check budget: cumulative task cost + estimated sub-agent cost < task budget
3. Check reversibility flag on the capability type (code_edit = reversible via git, computer_use = NOT reversible, external_api = depends on endpoint)
4. **Check cost tier of the engine being invoked** (see below)

If all pass → spawn. If budget fails → downgrade model or surface to user. If reversibility fails on a non-approved capability → surface to user.

The LLM-based governance check (permissions + precedent + social simulation) runs only for OUTREACH and STRATEGIC decisions, not for every sub-agent spawn.

### Cost-Conscious Engine Selection

Claude Agent SDK bills at API rates (~$15/$75 per MTok for Opus), not subscription
rates. This makes engine selection a cost governance concern, not just a capability
routing decision.

**Routing logic for code tasks:**

| Task Complexity | Primary Engine | Fallback | User Notification |
|----------------|---------------|----------|-------------------|
| Routine (add function, fix bug, write tests) | OpenCode (cost-efficient model) | Agent Zero LiteLLM | None — within normal budget |
| Complex (multi-file refactor, architecture) | Claude CLI subprocess (subscription) | Claude SDK API (with cost estimate) | "This task may cost $X via Claude SDK. Proceed?" |
| Rate-limited | OpenCode (best available model) | — | "Claude unavailable, using OpenCode with [model]" |

**Cost estimation before invocation:**
Before spawning a Claude SDK sub-agent, Genesis estimates cost based on:
- Number of files likely to be read (from task plan)
- Estimated conversation turns (from procedural memory of similar tasks)
- Model tier (Opus vs. Sonnet)
- Historical cost of similar tasks (from execution traces in memory-mcp)

This estimate is surfaced to the user as part of task confirmation:
"This task will use Claude SDK (Opus) for multi-file refactoring. Estimated cost:
$5-8. Approve / Use cheaper model / Cancel"

**Claude CLI subprocess (experimental):**
Agent Zero can attempt to invoke the `claude` CLI binary as a subprocess, which
uses the user's subscription OAuth rather than API billing. This is running
Anthropic's own product, not the SDK. Risks: Anthropic could restrict automated
invocation; the CLI's interactive nature may not map cleanly to Agent Zero's tool
interface. If it works, it's the preferred path for subscription holders. If not,
fall back to SDK with cost notification.

**Per-engine budget tracking:**
Execution traces (see schema above) track `cost_usd` per sub-agent. Aggregate
reporting by engine type (Agent Zero LiteLLM, Claude SDK, OpenCode, CLI subprocess)
enables the user to see where money goes and adjust routing preferences.

### Quality Gate

After each sub-agent returns, a lightweight check (utility model, cheap):
- Code sub-agents: "Does this code run? Does it address the stated requirement?"
- Browser sub-agents: "Did we get the information we needed?"
- Computer use: "Did the UI reach the expected state?"

Failure → retry with error context (max 2 retries) → if still failing, surface to user.
Success → proceed to next sub-agent or deliver result.

---

## Memory Separation: Conversational vs. Task-System

A design question the dual-engine architecture introduces: when Genesis is executing a task using Claude SDK as a tool, there are potentially two memory systems active (Genesis's memory-mcp and Claude SDK's in-session context). And there are two types of learnings accumulating: conversational (what the user likes, their communication style) and task-execution (how to approach certain types of code problems).

### The Separation

**Conversational memory** (feeds user model, drives proactive behavior):
- User preferences and communication style
- Interests, goals, patterns, frustrations
- Feedback on proactive outreach
- High-level project awareness ("user is building Genesis on Agent Zero")

**Task-execution memory** (feeds procedural memory, improves task quality):
- How to approach specific task types (code architecture, debugging patterns)
- Which tools work best for which sub-problems
- Failure modes and their resolutions
- Quality patterns from past successful outputs

Both live in memory-mcp, tagged differently. The distinction matters for retrieval:
- When assembling context for a conversation → weight conversational memory higher
- When assembling context for task planning → weight task-execution memory higher
- When assembling context for heartbeat/reflection → both equally

### Claude SDK Session Memory vs. Genesis Memory

Claude SDK sessions have their own deep context (file-level understanding of a codebase). This is ephemeral within a session but resumable via session IDs.

**The handshake:** Genesis owns the persistent layer. Claude SDK owns the deep-context layer for the duration of a task. Before invoking Claude SDK, Genesis writes a dynamic CLAUDE.md populated with relevant Genesis memories (past retrospectives, known patterns, procedural memory about this codebase). After the session, Genesis extracts learnings back into memory-mcp.

**Per-task isolation:** Agent Zero can spawn concurrent subordinates. If two tasks both invoke Claude SDK, their CLAUDE.md contexts must be isolated — otherwise the second write overwrites the first and the first session reads wrong context. Implementation: per-task CLAUDE.md files (e.g., `CLAUDE-{task_id}.md`) or per-sub-agent working directories. The handshake cycle (write → invoke → extract) is per-task, not global.

**What doesn't cross into Claude SDK by default:** User model data, salience weights, outreach preferences, system health data. Claude SDK is a specialist tool — it needs task context, not cognitive system state. Exception: if the task itself involves these systems (e.g., "fix the outreach timing"), relevant data is included in the dynamic CLAUDE.md.

---

## Self-Evolving Learning: The Autonomy Hierarchy

### The Core Goal

Genesis should learn not just FROM outcomes but HOW to learn better — adjusting its own review schedules, calibrating its own salience thresholds, proposing changes to its own cognitive parameters. This is what the ICML 2025 paper calls "intrinsic metacognition" vs. the "extrinsic metacognition" (fixed human-designed loops) that most systems fake.

But self-modification of learning systems has the **highest catastrophic potential**. A miscalibrated salience threshold is annoying. A miscalibrated learning system causes systematic drift away from user values — and does it invisibly, over time.

### The Autonomy Hierarchy

Actions are stratified by their blast radius and reversibility. Autonomy grows with demonstrated trustworthiness over time — not on a calendar, but based on evidence.

| Level | Action type | Default | Grows to |
|-------|------------|---------|----------|
| **L1** | Simple tool use (search, read, compute) | Fully autonomous | No change needed |
| **L2** | Task execution with known patterns | Mostly autonomous | Can reduce check-ins as confidence builds |
| **L3** | Novel task execution | Propose + execute with checkpoint | Can execute autonomously after N similar successes |
| **L4** | Proactive outreach | Threshold-gated + governance check | Threshold lowers as engagement data accumulates |
| **L5** | System configuration (thresholds, weights) | Propose only, user approves | Can self-adjust bounded parameters after high confidence |
| **L6** | Learning system modification (review schedules, drive weights, salience calibration) | Propose only, **always user review** | Bounded self-adjustment possible, but fundamental changes always user-approved |
| **L7** | Identity evolution (SOUL.md changes) | Draft only, user decides | Never fully autonomous — identity is the user's call |

**Key principle:** Autonomy for L5/L6 is bounded. The system can adjust salience weights ±20% within a session without approval, but can't fundamentally restructure how salience works. It can propose to change the review schedule but can't implement that change without user approval.

**The evidence threshold:** To unlock more autonomy at a level, the system needs:
- N successful executions without user correction
- No negative engagement signals indicating systematic error
- At least M weeks of operation at that level
- User explicitly acknowledging the autonomy grant (not just absence of correction)

The last point matters. Silence ≠ approval. The system should periodically ask: "I've been handling [category] autonomously for [period] with [X% success rate]. Would you like me to continue, or do you want to adjust my autonomy for this?"

### Autonomy Regression

Trust is harder to build than to lose. Regression triggers:
- 2 consecutive user corrections at a level → drop one level, require re-earning
- 1 user-reported harmful action → drop to default for that category, full re-earn
- System detects its own systematic error (e.g., 5 ignored outreach in a row at a topic) → self-proposes regression for that category

Regression is announced: "I've been making mistakes with [category]. Dropping back to [level] until I rebuild confidence. You can override this."

### Context-Dependent Trust Ceiling

Earned autonomy has a ceiling imposed by the interaction context. Regardless of
the system's earned level for a capability category, the *channel or invocation
context* can cap the effective autonomy:

| Context | Max Effective Autonomy | Rationale |
|---------|----------------------|-----------|
| Direct user session (WhatsApp, Web UI) | Earned level (no cap) | User is present, can intervene |
| Background cognitive (Reflection Engine) | L3 (notify + act) | No user in the loop — keep actions reversible |
| Sub-agent spawned by task | L2 (act with confirmation) for irreversible; earned for reversible | Sub-agents inherit task permissions, not global permissions |
| Outreach (proactive messaging) | L2 (act with confirmation) until engagement data proves calibration | Wrong outreach erodes trust faster than wrong internal action |

The principle: **later contexts restrict but never expand** effective autonomy.
A system with L5 earned autonomy for code operations still caps at L2 when a
sub-agent attempts an irreversible action inside a background task with no user
present. This prevents earned trust in supervised contexts from being exploited
in unsupervised ones.

### What "Learns HOW to Learn" Actually Means in Practice

At L6, the system can observe that its own learning is working or not:

- "My Deep reflections have been producing no actionable observations for 3 weeks. Either the threshold for what triggers Deep reflection is too high, or the quality of the reflection itself is poor. Proposing: lower Deep trigger threshold from composite score 0.7 to 0.6, trial for 2 weeks."

- "I've been recalibrating salience weights after every outreach event, but this is causing oscillation — my threshold for 'architecture insights' has swung between 0.6 and 0.9 in the past month. Proposing: introduce a damping factor to smooth weight updates."

- "The Strategic reflection is generating useful findings but they're not influencing my Light reflections at all. Proposing: add a step to Light reflections that checks for pending Strategic recommendations before completing."

These are proposals — concrete, evidence-based, with a stated rationale — surfaced via outreach for user review. The user can approve, reject, or modify. Over time, if proposals are consistently approved, some bounded class of them (e.g., ±threshold adjustments) might become auto-approved. But never the structural ones.

**Measuring learning value:** The meta-learning loop must measure **downstream utility**, not output volume. "Did this reflection produce observations?" is the wrong metric — it optimizes for busywork. The right metric: "Were the outputs of this reflection USED? Did an observation get retrieved by a subsequent reflection or task? Did an outreach item get acted on? Did a configuration change produce measurably different behavior?" Observations that accumulate without being retrieved or acted upon are evidence of waste, regardless of quantity. Track observation utility (retrieved, influenced a decision, acted on) not just creation count.

---

## What We Learned from the Research Landscape

### Where Genesis is Ahead of the Field

- **Integrated periodic cognition:** The dream cycle / heartbeat / health check layered architecture is more sophisticated than anything found in production. Most systems have one cognitive loop; Genesis has multiple at different frequencies with coordination.
- **Identity persistence:** SOUL.md + user model + memory-mcp is a richer identity substrate than most systems.
- **Recon system:** No other system has an equivalent autonomous environmental scanning layer that actively gathers intelligence on a schedule. ChatGPT Pulse curates topics from user signals; Genesis also generates its own intelligence.

### Where Genesis Has Gaps (and the Fixes)

**Gap: No explicit user feedback loop on proactive outputs**
ChatGPT Pulse's thumbs-up/down on morning briefing cards is simple and effective.
→ **Fix:** outreach-mcp tracks engagement with inline feedback (WhatsApp: reply-based, Telegram: reactions). The Self-Learning Loop uses this as primary training signal for salience calibration.

**Gap: Append-only memory accumulation**
Genesis memories accumulate and are periodically cleaned up. More dynamic: new memories should update related existing ones.
→ **Fix (from A-MEM):** When storing new observations, run a lightweight pass to find related existing memories and link them (or update confidence/context if the new info changes the old). The dream cycle does a heavier version of this during consolidation, but the lightweight linking should happen at storage time.

**Gap: Flat memory retrieval (similarity search only)**
Embedding similarity is good but misses activation patterns — frequently-accessed important memories should be easier to retrieve than rarely-accessed ones.
→ **Fix (from ACT-R + Mnemosyne):** Add an activation score to memories: `activation = base_score * recency_factor * access_frequency_factor * connectivity_factor`. Retrieval weights activation alongside embedding similarity. Memories that are accessed often, recently, and are well-connected stay highly accessible even if they're semantically distant from the query.

**Gap: Context window assembly is ad hoc**
When assembling the heartbeat prompt or task context, what gets included is mostly intuitive.
→ **Fix (from Engram):** Salience-ranked greedy knapsack for context assembly. Each candidate memory/signal has a salience score. Fill the context window budget greedily from highest-salience down. This makes context assembly principled and optimizable.

**Gap: Dual-context separation before proactive decisions**
The decision "should I reach out?" currently mixes situation signals and user model signals without formal separation.
→ **Fix (from ContextAgent):** Formalize two evaluation passes before proactive decisions: (1) situation assessment — "what is happening and how important is it?" (2) persona assessment — "given who this user is, would they want to know this now?" Both pass through the Reflection Engine, but as distinct steps with distinct context.

**Gap: Proactive suggestion noise floor is unknown**
Without data, we don't know how often proactive suggestions will be welcome.
→ **Calibration from ProactiveBench:** Even trained models get proactive suggestions right ~66% of the time. Meaning 1 in 3 will be unwelcome even with a good user model. Set expectations accordingly. The engagement feedback loop should improve this over time, but never expect 95%+ precision.

**Gap: No impasse-driven learning**
Genesis learns from successes and explicit lessons. It doesn't systematically learn from failures and dead ends.
→ **Fix (from SOAR):** When tasks fail or produce poor output, log the failure as an explicit learning event — what was attempted, what failed, what the failure mode was. These "impasse records" feed the Self-Learning Loop and the procedural memory deprecation mechanism.

**Warning: Don't over-scaffold**
Letta deprecated heartbeats in V1 because modern models work better without framework-imposed patterns. Genesis's heartbeat is scheduled background cognition (different from in-conversation reasoning), so the direct comparison doesn't apply. But the principle stands: as models improve, periodically audit whether Genesis's scaffolding is still adding value or has become overhead.

**Warning: Proactive AI is perceived as threatening**
CHI 2025 study: unsolicited AI help is perceived as MORE threatening than unsolicited human help. Tone, timing, and opt-out mechanisms are not cosmetic — they directly affect adoption. Genesis must frame proactive outreach as assistance, not surveillance. And the opt-out path must be effortless ("Reply STOP to pause proactive updates").

### AutoGPT: Historical Context

AutoGPT (2023) pioneered autonomous LLM task loops but is now largely a historical reference point. The lessons it taught:
- **What it proved:** LLMs can chain tasks autonomously
- **What it got wrong:** Unbounded loops, no cost controls, no quality gates, no human checkpoints
- **Current state:** Still active as a cloud platform with human-in-the-loop features bolted on
- **Relevance to Genesis:** Confirms what NOT to do. Genesis's governance checks, bounded autonomy, and budget controls are direct corrections to AutoGPT's failure modes.

---

## Procedural Memory Design

*(Confidence decay mechanics are deferred — complex guardrail issues to revisit separately.)*

### Schema

```json
{
  "id": "proc_abc123",
  "task_type": "data_pipeline_construction",
  "principle": "Validate data schema before transformation, not after",
  "steps": [
    "Inspect source data schema",
    "Define expected output schema",
    "Write validation function",
    "Then write transformation logic"
  ],
  "tools_used": ["python", "pandas", "pytest"],
  "context_tags": ["python", "data", "ETL", "pandas"],
  "success_count": 4,
  "failure_count": 1,
  "failure_modes": ["Fails when source schema is dynamic/undeclared"],
  "confidence": 0.78,
  "last_used": "2026-02-20T14:22:00",
  "last_validated": "2026-02-20T14:22:00",
  "deprecated": false,
  "deprecated_reason": null,
  "superseded_by": null
}
```

### Anti-Rigidity Mechanisms

Procedures are **advisory context, never imperative instructions**. The LLM always sees them framed as:

> "Previous approach for [task type] (success rate 78%, last used 3 days ago):
> Principle: [principle]
> Steps: [steps]
> Known failure mode: [when it fails]
>
> Consider whether current circumstances warrant this approach, a variation, or something different."

**Failure tagging on the procedure:** When a procedure is followed and the task fails, the failure is recorded on that procedure record — not just as a separate episodic memory. After N failures, the procedure is flagged for deprecation during the next Deep reflection. The LLM reviews it: deprecate outright, update steps, or add a context restriction ("only applies when X, not when Y").

**Dual-level storage (from Mem^p):** Store both the specific steps AND the higher-level principle. The principle ("validate before transforming") is more durable than the steps ("run pandas.DataFrame.describe() first"). When specific steps become outdated, the principle may still apply with different steps.

**Context-conditional retrieval:** Procedures are only retrieved when their context_tags overlap meaningfully with the current task. A procedure that worked for Python data pipelines isn't surfaced for a Rust CLI tool even if the task_type superficially matches.

*(Note: Confidence decay over time with guardrails against amnesia — deferred to separate design session.)*

---

## Awareness Loop: Signal-Weighted Trigger System

"Triggers when warranted" is not sufficient. The concrete mechanism:

### Composite Urgency Score

Every 5 minutes, for each depth level:

```
urgency_score(depth) = Σ(signal_value_i × weight_i) × time_multiplier(depth)
```

Where `time_multiplier` rises as time passes since last reflection at that depth:

```
Micro time_multiplier:
  At 0min since last Micro:  0.3x  (just reflected)
  At 15min:                  0.7x
  At 30min (floor):          1.0x  (baseline)
  At 45min:                  1.5x
  At 60min:                  2.5x  (overdue)

At 0h since last Light:   0.5x  (suppressed — just reflected)
At 3h:                    1.0x  (baseline)
At 6h (floor):            1.5x  (heightened)
At 8h:                    2.0x  (approaching overdue)
At 12h:                   3.0x  (something is wrong if this is reached)

Deep time_multiplier:
  At 0h since last Deep:    0.3x  (heavily suppressed)
  At 24h:                   0.7x
  At 48h (floor start):     1.0x  (baseline)
  At 72h (floor end):       1.5x  (heightened)
  At 96h:                   2.5x  (overdue)

Strategic time_multiplier:
  At 0d since last Strategic:  0.2x  (heavily suppressed)
  At 3d:                       0.5x
  At 7d (floor start):         1.0x  (baseline)
  At 10d:                      1.5x
  At 14d (floor end):          2.0x  (heightened)
  At 21d:                      3.0x  (overdue)
```

When `urgency_score ≥ threshold_for_depth` → trigger that depth. Calendar floor is implicit in the rising multiplier — even weak signals eventually cross the threshold.

### Signal Sources and Initial Weights

| Signal | Source | Initial Weight | Feeds | Rationale |
|--------|--------|---------------|-------|-----------|
| Conversations since last reflection | Agent Zero | 0.40 | Micro/Light | User interaction is the primary input — the thing we're here for |
| Task completion / quality signal | Agent Zero | 0.50 | Micro/Light | "Am I actually helping? Am I getting better?" |
| Outreach engagement data | outreach-mcp | 0.45 | Micro/Deep | "Are my proactive suggestions landing?" — core learning signal |
| Recon findings pending triage | recon-mcp | 0.35 | Light/Deep | New intelligence that might help the user |
| Unprocessed memory backlog | memory-mcp | 0.30 | Deep | Learning debt — things experienced but not consolidated |
| Budget % consumed since check | health-mcp | 0.40 | Light/Deep | Cost awareness, but not the main event |
| Software error spike | health-mcp | 0.70 | Micro/Light | Something broke — fix it. But only fires when errors actually happen. |
| Critical failure (crash, dead API) | health-mcp | 0.90 | Light (immediate) | Reactive — fire fast, fix fast, move on |
| Time since last Strategic | Clock | 0.50 | Strategic | Ensure periodic big-picture thinking happens |

**Design intent:** The top 4 signals by weight are all about **user value and self-improvement**. Health signals are reactive (high weight but only fire when something is actually wrong). Genesis should spend 80%+ of its cognitive budget thinking about how to be more useful, not whether its processes are running.

### How Weights Adapt

The Self-Learning Loop tracks: "When signal X triggered a reflection, did that reflection produce value?" Value = observations written, outreach sent, procedures updated, or configuration changed.

- Signal consistently triggers reflections that produce nothing → weight drops
- Signal consistently triggers reflections that produce actions → weight rises
- Strategic reflection can temporarily override weights ("this week, raise error weight because we're deploying")

### Ceiling: Preventing Thrashing

A per-depth boolean resets after each reflection: "Has this depth fired within its minimum interval?" If yes, accumulate score but don't trigger. Three budget alerts in one hour shouldn't produce three Deep reflections — they should be batched into one.

---

## Loop Taxonomy: Complete Feedback Cycle Inventory

This section maps every feedback cycle in the Genesis v3 architecture — autonomous processes, integrated operational cycles, calibration feedback loops, and emergent spirals that arise from their interaction. The taxonomy serves two purposes: (1) a mental model for reasoning about how the system improves over time, and (2) a checklist ensuring no feedback cycle falls through the cracks during implementation.

### How to Read This Map

Loops are organized by **what drives them**, not by implementation type. Each tier depends on the tier below it:

- **Tier 0** — The metronome. Ticks autonomously. Everything else is downstream.
- **Tier 1** — The cognitive engines. Triggered by Tier 0.
- **Tier 2** — Operational cycles. Driven by events, user actions, or Tier 1.
- **Tier 3** — Calibration loops. Feedback cycles embedded in Tiers 1-2 that tune the system.
- **Tier 4** — Emergent spirals. No dedicated code — they arise from the interaction of everything above.

**Tiers 0-2 are what the system DOES. Tiers 3-4 are how the system IMPROVES at what it does.** Most AI systems only have Tiers 0-2. The calibration and emergent layers are what make Genesis a learning system rather than just an executing system.

```
Tier 4 (Emergent)     ┌─────────────────────────────────────────────┐
                      │  User Model    Identity    Meta-Learning     │
                      │  Deepening     Evolution   Loop              │
                      │  Spiral        Spiral      ("learn to learn")│
                      │                                              │
                      │  Capability                                  │
                      │  Expansion                                   │
                      └──────────────────┬──────────────────────────┘
                                         │ emerge from
Tier 3 (Calibration)  ┌──────────────────┴──────────────────────────┐
                      │  Salience      Drive Weight   Signal Weight   │
                      │  Learning      Loop           Adaptation      │
                      │                                              │
                      │  Autonomy      Procedural                    │
                      │  Progression   Memory Loop                   │
                      └──────────────────┬──────────────────────────┘
                                         │ tune
Tier 2 (Operational)  ┌──────────────────┴──────────────────────────┐
                      │  Memory         Task          Recon           │
                      │  Store/Recall   Execution     Gathering       │
                      │  Cycle          Cycle         Cycle           │
                      │                                              │
                      │  CLAUDE.md Handshake Cycle                   │
                      └──────────────────┬──────────────────────────┘
                                         │ driven by
Tier 1 (Cognitive)    ┌──────────────────┴──────────────────────────┐
                      │  Reflection Engine    Self-Learning Loop      │
                      │  (Micro→Light→        (Dopaminergic —         │
                      │   Deep→Strategic)      after interactions)    │
                      └──────────────────┬──────────────────────────┘
                                         │ triggered by
Tier 0 (Foundation)   ┌──────────────────┴──────────────────────────┐
                      │           AWARENESS LOOP                     │
                      │      5min tick, programmatic, zero LLM       │
                      └──────────────────────────────────────────────┘
```

### Tier 0: The Metronome

**Loop 1: Awareness Loop** — 5-minute tick, programmatic, zero LLM cost.

The metronome. Everything else either IS this loop, is triggered BY this loop, or feeds data BACK to this loop. Cycle: collect signals → compute composite urgency scores per depth → compare against thresholds → trigger Reflection Engine (or don't) → process escalation flags → wait 5 minutes → repeat.

What it tunes: nothing. It's pure perception. It fires and forgets.

*Detailed design: see Layer 1: Awareness Loop section above.*

### Tier 1: The Cognitive Engines

**Loop 2: Reflection Engine** — triggered by Awareness Loop, adaptive depth.

Where cognition happens. Cycle: triggered at a depth → assemble context (signals, memory, user model) → reason about what matters → produce observations, outreach, configuration changes → write outputs to memory/outreach → done until next trigger.

This is NOT a fixed-interval loop. Its frequency is emergent from signal urgency + time multipliers. Could fire 4 times in a busy hour or once in a quiet day. It also HOSTS the inline prompt patterns (salience eval, user model synthesis, governance, drive weighting) that feed the calibration loops — but the Reflection Engine itself doesn't tune parameters. It reads them.

*Detailed design: see Layer 2: Reflection Engine section above.*

**Loop 3: Self-Learning Loop** — event-driven, fires after interactions and outreach events.

The "dopaminergic system." Cycle: interaction completes → task retrospective with root-cause classification → lessons extracted → prediction errors logged → drive weights adjusted → salience model updated → procedural memory updated → capability gaps accumulated.

This is the ONLY loop that writes to calibration parameters. The Reflection Engine reads them; the Self-Learning Loop writes them. This clean separation prevents conflicting writes.

*Detailed design: see Layer 3: Self-Learning Loop section above.*

### Tier 2: The Operational Cycles

**Loop 4: Memory Store/Recall Cycle** — integrated into every conversation turn.

Cycle: message arrives → proactive recall injects relevant context → core facts loaded → response generated → exchange stored → facts/entities extracted → new memories linked to related existing memories (lightweight A-MEM pass).

Highest-frequency loop in the system (every conversation turn). Invisible to the user. This is what gives the system continuity across sessions.

**Loop 5: Task Execution Cycle** — on-demand, per user request.

Cycle: user request → planning pass (retrieve procedural memory) → spawn sub-agents → governance check at each capability boundary → quality gate per sub-agent → retry on failure (max 2) → deliver result → retrospective with root-cause classification → procedural memory extraction.

Each execution is a single pass, not a recurring loop. But across many executions, the retrospective → procedural memory → future planning chain creates a feedback cycle that spans tasks.

*Detailed design: see Task Execution Architecture section above.*

**Loop 6: Recon Gathering Cycle** — self-scheduled (recon-mcp manages its own cron).

Cycle: scan configured sources on schedule → store findings → push high-priority to Awareness Loop → low-priority accumulates → triage during Deep/Strategic reflection → acted-on findings feed future source prioritization.

The ONLY operational loop with its own internal scheduler, independent from the Awareness Loop. It pushes signals TO the Awareness Loop rather than being triggered BY it. Potential concurrent access during Deep reflection triage is handled by recon-mcp being the single writer; the Reflection Engine is a reader.

*Detailed design: see recon-mcp in 4 MCP Servers section above.*

**Loop 7: CLAUDE.md Handshake Cycle** — per Claude SDK invocation.

Cycle: Genesis recalls relevant memories → writes per-task dynamic CLAUDE.md → invokes Claude SDK → Claude SDK works with full persistent context → session completes → Genesis extracts learnings back into memory-mcp → next invocation's CLAUDE.md is richer.

The cross-engine learning bridge. Without it, Claude SDK sessions are stateless tools. With it, each invocation benefits from everything every previous invocation learned. Per-task isolation required for concurrent sub-agents (see Memory Separation section above).

### Tier 3: The Calibration Loops

These are not autonomous processes. They are **feedback cycles embedded within Tiers 1-2**, driven primarily by the Self-Learning Loop (Loop 3). Each follows the pattern: act → observe outcome → adjust parameter → future actions are different.

**Loop 8: Salience Learning** — tunes the world model that generates salience scores.

Cycle: world model predicts engagement for a signal → Reflection Engine uses prediction to decide outreach → outreach delivered → user engages or ignores → Self-Learning Loop computes prediction error → world model updated → future predictions are more accurate.

Timescale: days to weeks. Needs ~20-30 data points per topic category before calibration is meaningful. Thresholds can't drop below a noise floor (prevents spam) or rise above a ceiling (prevents going silent).

**Design note:** This loop merges what were originally two separate concepts — engagement calibration (adjusting thresholds) and world model refinement (improving the prediction model). They were merged because separating them creates a double-adjustment problem: if the prediction model gets more pessimistic AND the threshold rises independently, the system over-corrects and permanently suppresses certain topic types. The learning happens in the prediction model (world model); the threshold is fixed or very slowly adjusted at Strategic depth.

**Loop 9: Drive Weight Loop** — tunes the four drives (curiosity, competence, cooperation, preservation).

Cycle: drives shape Reflection Engine focus → actions taken → outcomes tracked → positive outcomes on cooperation-driven actions → cooperation sensitivity rises → Reflection Engine prioritizes cooperation signals → more cooperation actions.

Timescale: weeks. Slow-moving by design. Independent sensitivity multipliers, not a normalized budget (see Drive Weighting clarification in Reflection Engine section).

**Loop 10: Signal Weight Adaptation** — tunes Awareness Loop signal weights.

Cycle: signal X triggers reflection → reflection produces value (or doesn't) → Self-Learning Loop adjusts signal X's weight → signal X is more/less likely to trigger future reflections.

Timescale: days. Faster than drive weights because it's more granular. Strategic reflection can set temporary overrides ("raise error weight this week because we're deploying") that decay after the stated period.

**Loop 11: Autonomy Progression** — tunes per-category autonomy levels (L1-L7).

Cycle: action at current autonomy level → outcome (success/correction/failure) → evidence accumulates → N successes without correction → propose level increase → user explicitly approves → autonomy rises → more actions taken autonomously.

Regression: 2 corrections → drop one level. 1 harmful action → full reset. Self-detected systematic error → self-proposed regression. Silence ≠ approval — system periodically asks for explicit confirmation.

Timescale: weeks to months. Slowest calibration loop, by design.

*Detailed design: see Self-Evolving Learning: The Autonomy Hierarchy section above.*

**Loop 12: Procedural Memory Loop** — tunes "how to do things."

Cycle: novel approach tried → outcome with root-cause classification → if `success` or `approach_failure`: procedure extracted or updated → future similar task retrieves procedure → procedure used/adapted → outcome updates confidence → N failures → flagged for deprecation → Deep reflection reviews.

Dual-level: stores both specific steps AND underlying principle. Steps decay; principles persist. Procedures are always advisory context, never imperative instructions.

`capability_gap` and `external_blocker` outcomes do NOT feed into procedural memory adjustment — the system shouldn't "learn" that it's bad at tasks it simply can't do yet.

*Detailed design: see Procedural Memory Design section above.*

### Tier 4: The Emergent Spirals

These have no dedicated code. They arise from the interaction of the loops above. Calling them "spirals" rather than "loops" because they don't return to the same starting point — they compound.

**Spiral 13: User Model Deepening**

Powered by: Memory Store/Recall (4) + Salience Learning (8) + Reflection Engine user model synthesis.

Motion: interactions → user model synthesis → richer model → better salience evaluation → better outreach → user engages more meaningfully → richer interaction data → even richer model.

Timescale: Month 1 = shallow profile. Month 3 = calibrated. Month 6+ = anticipatory. Diminishing returns after ~6 months of active interaction.

**Spiral 14: Identity Evolution**

Powered by: Reflection Engine observations + Self-Learning Loop + user approval.

Motion: behavior produces observations → patterns accumulate → Deep/Strategic reflection proposes SOUL.md changes → user approves/rejects/modifies → identity files change → LLM reads different identity context → behavior shifts → new observations.

Timescale: months. Slowest spiral. Always requires user's hand on the steering wheel (L7 — never autonomous). This is the spiral that determines what KIND of system Genesis becomes. Everything else determines how well it performs; this determines what it IS.

**Spiral 15: Meta-Learning ("Learning how to learn")**

Powered by: Self-Learning Loop (3) observing its OWN effectiveness.

Motion: learning system produces calibration changes → changes produce outcomes → outcomes are measured by downstream utility (not output volume) → Self-Learning Loop notices effectiveness drift → proposes adjustment to learning parameters (trigger thresholds, damping factors, review structure) → user approves → learning system changes → different calibrations → different outcomes.

Timescale: months. Always user-approved for structural changes. Bounded self-adjustment (±20% on parameters) possible at L6.

Why this matters: without this, every other calibration loop has a fixed learning rate. With this, the learning rates themselves are learned.

*Detailed design: see "What 'Learns HOW to Learn' Actually Means in Practice" in the Autonomy Hierarchy section above.*

**Spiral 16: Capability Expansion**

Powered by: Task Execution Cycle (5) + Self-Learning Loop root-cause classification + Strategic reflection.

Motion: task attempted → capability gap discovered (root-cause = `capability_gap` or `external_blocker` with future feasibility) → gap logged to accumulator → Strategic reflection reviews accumulated gaps → evaluates ROI: "How many times was this gap hit? What would it take to close it? Is the investment justified?" → proposes capability acquisition (new tool, MCP integration, skill) → user approves → capability added → future tasks succeed → new gaps discovered at the frontier.

`external_blocker` outcomes with `revisit_after` dates are re-evaluated during Strategic reflection: "Has the technology landscape changed? Is this now feasible?" Blockers that become feasible are promoted to capability gaps.

Autonomy: L5 for proposing acquisitions, L6+ for self-acquiring (e.g., installing a new tool). User always approves new external integrations.

Why this matters: without this, the system gets better at what it already CAN do but never expands WHAT it can do. This is what prevents capability plateaus.

### Loop Interaction Map

How the loops feed each other:

```
                    ┌─── Loop 1: Awareness Loop ───┐
                    │         (5min tick)            │
                    │    collects signals from:      │
                    │    • Loop 4 (memory backlog)   │
                    │    • Loop 6 (recon findings)   │
                    │    • Loop 8 (engagement data)  │
                    │    • health-mcp                │
                    └──────────┬────────────────────┘
                               │ triggers
                    ┌──────────▼────────────────────┐
                    │ Loop 2: Reflection Engine      │
                    │  reads from:                   │
                    │  • Loop 9 (drive weights)      │
                    │  • Loop 13 (user model)        │
                    │  • Loop 12 (procedures)        │
                    │  • Loop 11 (autonomy levels)   │
                    │  writes to:                    │
                    │  • Observations (memory-mcp)   │
                    │  • Outreach queue              │
                    │  • Loop 14 (evolution proposals)│
                    │  • Escalation flags (Loop 1)   │
                    └──────────┬────────────────────┘
                               │ feeds
                    ┌──────────▼────────────────────┐
                    │ Loop 3: Self-Learning Loop     │
                    │  THE KEYSTONE — sole writer to:│
                    │  • Loop 8 (salience model)     │
                    │  • Loop 9 (drive weights)      │
                    │  • Loop 10 (signal weights)    │
                    │  • Loop 11 (autonomy evidence) │
                    │  • Loop 12 (procedures)        │
                    │  • Spiral 16 (capability gaps)  │
                    └───────────────────────────────┘
```

The Self-Learning Loop is the keystone. Remove it and Tiers 0-2 still work — the system perceives, thinks, and acts. But nothing improves. The system is frozen at its initial calibration forever.

### Design Caveats

**Salience learning is a single adjustment, not two.** Engagement calibration and world model refinement share one parameter space. The learning happens in the world model (prediction accuracy); thresholds are fixed or adjusted only at Strategic depth. Separate adjustment creates oscillation through double-punishment of topics.

**Meta-learning measures downstream utility, not output.** "Did this reflection produce observations?" is the wrong metric. The right metric: "Were the outputs USED? Retrieved by a subsequent process? Acted on by the user?" Volume of observations is not evidence of value.

**Root-cause classification prevents false learning.** `capability_gap` and `external_blocker` outcomes bypass procedural memory adjustment. Without this distinction, the system "learns" it's bad at tasks it simply lacks tools for, creating a negative prior that persists even after the capability is added.

**External blockers have a lifecycle.** They aren't dead ends. Classification: (a) user-rectifiable — surface as blocker via outreach; (b) future capability gap — parked with `revisit_after` date, re-evaluated during Strategic reflection as technology landscape changes; (c) permanent constraint — logged and accepted.

**Depth escalation preserves single-coordinator authority.** The Reflection Engine can flag that deeper analysis is needed, but the Awareness Loop is ALWAYS the one that invokes it. Critical escalations get an immediate out-of-cycle tick; everything else waits for the next 5-minute tick. No self-triggering.

**Per-task CLAUDE.md isolation.** Concurrent sub-agents each get their own CLAUDE.md context to prevent overwrite races. The handshake cycle is per-task, not global.

---

## LLM Weakness Compensation: Architectural Patterns

LLMs are remarkably good at the things Genesis needs most — contextual reasoning, pattern recognition, natural language understanding, flexible judgment. But an autonomous system that runs for months amplifies specific weaknesses that are tolerable in single conversations. This section documents the weaknesses that matter, the compensating patterns adopted, and the patterns considered but deferred.

**Core principle:** The architecture doesn't "fix" the LLM. It plays to its strengths (judgment, interpretation, synthesis) and puts guardrails on the specific situations where it predictably fails (computation, calibration, confabulation under uncertainty). LLMs interpret; code computes.

### The Weaknesses That Compound Over Time

These are ranked by damage to a system that runs autonomously for months, not by frequency in single conversations.

**1. Confabulation under uncertainty (CRITICAL).** LLMs fabricate plausible answers rather than saying "I don't know." In a conversation this is annoying. In an autonomous system that writes to persistent memory, it's corrosive. Confabulated user preferences get stored → retrieved as facts → inform future reasoning → produce more confident (but still wrong) conclusions → stored again. The system drifts from reality through accumulated micro-confabulations that reinforce each other. Affects: user model synthesis, procedural memory extraction, recon triage.

**2. Tunnel vision / anchoring in long contexts (HIGH).** The LLM that produced reasoning is anchored to it. A fresh LLM seeing only the output often reaches a completely different conclusion. Affects: quality gates, Deep reflection (early jobs color late jobs), identity evolution proposals (anchored to existing SOUL.md framing).

**3. Overconfidence / poor calibration (HIGH).** LLMs express certainty regardless of actual reliability. Salience scores, confidence values, and prediction errors LOOK precise but have wide error bars. Learning from the "error" between two poorly calibrated numbers is learning from noise. Affects: salience scoring, procedural memory confidence, Self-Learning Loop prediction errors.

**4. Mode collapse under repetition (MEDIUM-HIGH).** Same prompt running repeatedly → outputs converge to formulaic patterns. By day 3, Micro reflections will sound identical: "No significant anomalies detected. System operating normally." Even when there IS something worth noticing. Affects: Micro reflection, task retrospectives, engagement prediction.

**5. Sycophancy / prompt compliance bias (MEDIUM).** LLMs produce outputs matching what the prompt seems to want. "Find problems" → problems found (even when there aren't any). "Evaluate how well you're doing" → favorable self-assessment. Affects: Self-Learning Loop self-evaluation, identity evolution (always proposes changes because the prompt asks), Reflection Engine productivity (always finds something "worth noting").

**6. Temporal reasoning weakness (MEDIUM).** LLMs are bad at sequences, trends, and causality over time. Affects: trend detection in reflection, engagement trajectory analysis, cost projection.

**7. Positional bias — "lost in the middle" (LOW-MEDIUM).** LLMs pay more attention to the beginning and end of context. Middle content gets underweighted. Affects: memory injection, multi-job reflection, recon triage with multiple findings.

### Adopted Patterns

#### Pattern 1: Compute Hierarchy — Right Model for Each Job

The foundation runs on free/cheap compute. Expensive models are used surgically for judgment calls. This is not "good, cheap, fast — pick two." It's using the right tool for each job.

**Availability note:** The local machine that runs 20-30B models is NOT available 24/7. When local models are unavailable, their tasks fall back to cheap cloud models (Gemini Flash free tier, GLM5, or equivalent). The system must detect local model availability and route accordingly. Gemini's free API tier (~10-30 calls/day) is a valuable resource — use it rather than leaving it idle.

```
┌─────────────────────────────────────────────────────────┐
│  ALWAYS ON (24/7, zero marginal cost)                    │
│                                                          │
│  Programmatic layer (no LLM)                             │
│  • Awareness Loop signal collection + urgency scoring    │
│  • Engagement statistics (rates, trends, moving averages)│
│  • Cost tracking + budget arithmetic                     │
│  • Confidence score calculation (success_count / total)  │
│  • Trend detection (change point detection, baselines)   │
│  • Context assembly with position weighting              │
│  • Root-cause classification routing (once classified)   │
│  • Maturity metrics (data volume tracking — see below)   │
│                                                          │
│  Local 3B model (when local machine available)           │
│  • JSON/structured output parsing and validation         │
│  • Binary classification ("is this well-formed?")        │
│  • Simple tagging (memory type, source type)             │
│  • Keyword/entity extraction from short text             │
│  Fallback when unavailable: regex/heuristic or skip      │
│                                                          │
│  ⚠ 3B models CANNOT reliably:                           │
│  • Evaluate quality or relevance of content              │
│  • Perform root-cause classification (judgment call)     │
│  • Synthesize across multiple inputs                     │
│  • Generate natural language that will be user-facing     │
│  • Assess salience, urgency, or importance               │
│  If in doubt about 3B capability → escalate to 20-30B    │
└──────────────────────────────┬──────────────────────────┘
                               │ escalates to
┌──────────────────────────────▼──────────────────────────┐
│  HIGH FREQUENCY, LOW COST                                │
│                                                          │
│  Local 20-30B model (when available)                     │
│  • Micro reflections (every 30min)                       │
│  • Task retrospective drafting + root-cause classification│
│  • Routine procedural memory extraction                  │
│  • Memory consolidation (batch processing)               │
│  • Fact/entity/relationship extraction from conversations │
│  • Speculative hypothesis generation (with tags)         │
│  Fallback when unavailable: Gemini Flash free tier / GLM5│
│                                                          │
│  Gemini Flash free tier (~10-30 calls/day)               │
│  • Default fallback for local 20-30B when unavailable    │
│  • Light reflections (every 6h) when local unavailable   │
│  • Recon finding preliminary evaluation                  │
│  • Cross-check on 20-30B outputs (cheap second opinion)  │
│  • Outreach draft generation (not final review)          │
│                                                          │
│  GLM5 / other affordable API models                      │
│  • Overflow when Gemini free tier exhausted               │
│  • Routine task execution for simple tasks               │
│  • Bulk memory operations                                │
│                                                          │
│  ⚠ 20-30B / Flash-class models CANNOT reliably:         │
│  • Complex multi-step reasoning chains                   │
│  • Nuanced judgment about user intent or preferences     │
│  • Architectural or strategic analysis                   │
│  • Identity evolution proposals (stakes too high)        │
│  • Quality gates on complex task outputs                 │
│  If in doubt → escalate to Sonnet-class                  │
└──────────────────────────────┬──────────────────────────┘
                               │ escalates to
┌──────────────────────────────▼──────────────────────────┐
│  JUDGMENT CALLS (surgical, high-value)                   │
│                                                          │
│  Sonnet / GPT-4o class                                   │
│  • Deep reflection (adaptive, only when warranted)       │
│  • Light reflection (when local models unavailable)      │
│  • Fresh-eyes review on outreach before sending          │
│  • Quality gates on complex task outputs                 │
│  • Cross-model review (different provider than primary)  │
│  • Meta-prompting for Deep/Strategic reflection          │
│  • User model synthesis (nuanced judgment required)      │
│                                                          │
│  Opus / best-available                                   │
│  • Strategic reflection                                  │
│  • Identity evolution proposals + second opinion         │
│  • Complex task planning and orchestration               │
│  • Capability gap ROI assessment                         │
│  • Configuration change review (high blast radius)       │
│  • The decisions that shape everything downstream        │
└─────────────────────────────────────────────────────────┘
```

**The operating principle:** Classification and computation don't need intelligence. Routine extraction needs moderate intelligence. Judgment calls that persist or are hard to reverse need the best available. The 3B + programmatic layer handles ~80% of all "calls" at zero cost. The 20-30B / Flash tier handles ~15%. The expensive models handle ~5% — but those are the 5% that shape the system's trajectory.

**Default: escalate when uncertain.** If there's any doubt about whether a smaller model can handle a task, escalate. A wasted Sonnet call costs cents. A bad judgment from a 3B model that gets stored in memory costs far more to fix downstream.

#### Pattern 2: Meta-Prompting for Adaptive Reflection

Instead of hardcoding what Deep/Strategic reflection should focus on, a cheap model examines the signal landscape and generates the reflection questions. An LLM that prompts an LLM.

This solves two problems simultaneously:
- **Mode collapse:** Questions are different each time because the signal landscape is different
- **Decomposition vs. synthesis:** The meta-prompter sees everything (holistic), generates focused questions (decomposed), and a synthesis pass catches cross-cutting patterns

```
Step 1: Meta-prompt (cheap — 20-30B local or Gemini Flash)
  Input: Full signal landscape from Awareness Loop
  Task: "Given these signals, what are the 3-5 most important
         questions this reflection should answer? Consider
         cross-cutting patterns across signals, not just
         individual items. What might connect seemingly
         unrelated signals?"
  Output: 3-5 focused questions with relevant context scope

Step 2: Deep reflection (capable — Sonnet or Opus)
  Input: Each question + only its relevant context (from MCP)
  Task: Answer each question with grounded evidence
  Output: Observations, proposals, actions per question

Step 3: Synthesis (capable — fresh call, same or different model)
  Input: ONLY the answers from Step 2 (not the reasoning)
  Task: "Do any of these answers interact? Are there patterns
         across them that the individual answers missed?"
  Output: Cross-cutting insights, integrated observations
```

**Why the meta-prompter is the most critical call in the system:** If the meta-prompter asks the wrong questions, the entire reflection is wasted regardless of how capable the answering model is. A brilliant answer to the wrong question is worthless. The meta-prompter should err toward breadth — it's better to ask one unnecessary question (cheap to answer, easily discarded) than to miss a question that mattered.

**Cost profile:** Step 1 is cheap (~100-500 tokens output). Step 2 is the expensive part but is focused and efficient. Step 3 is moderate. Total cost is often LESS than a single monolithic Deep reflection prompt because each step's context is smaller.

#### Pattern 3: Speculative vs. Grounded Claims

Every factual claim written to persistent memory must be either grounded in evidence or explicitly tagged as speculative.

**Grounded claims:** The Reflection Engine prompt includes the constraint:
> "For factual claims about the user, the system, or patterns, cite the specific memory ID, observation ID, or data point that supports them. If you have evidence, cite it. If you're inferring from indirect signals, say so explicitly."

**Speculative claims (hypotheses):** The LLM's ability to notice fuzzy patterns IS its superpower — don't suppress it. But speculative insights get stored differently:
- Tagged with `speculative: true`
- Given a `hypothesis_expiry` timestamp (e.g., 14 days from creation)
- Stored with `evidence_count: 0`
- NEVER used as context for future reasoning UNTIL confirmed

**Confirmation cycle:** When new evidence appears that supports a hypothesis, `evidence_count` increments and `speculative` can be flipped to `false` once count reaches a threshold (default: 3 independent evidence points). Hypotheses that expire without confirmation are archived, not used as context.

**This breaks the confabulation compound loop.** Hallucinated preferences can't propagate into future context because they're quarantined until confirmed. They die in one generation instead of compounding.

#### Pattern 4: Fresh-Eyes Review (Selective)

A separate LLM call reviews ONLY the output, without the reasoning chain. Applied selectively to high-stakes, persistent, or hard-to-reverse outputs.

| Process | Primary Model | Reviewer | What reviewer sees |
|---------|--------------|----------|-------------------|
| Identity evolution proposals | Opus (Strategic) | Sonnet (different provider preferred) | Current SOUL.md + proposed changes only. NOT the observations that led there |
| Strategic config changes | Opus (Strategic) | Sonnet (fresh call) | Current config + proposed change + stated rationale only |
| Outreach before sending | Sonnet (Reflection Engine) | Flash/20-30B (cheap) | Draft message + user model summary. "Would the user want to receive this?" |
| Complex task quality gate | Claude SDK (task agent) | Different model (Gemini/GPT) | Original request + final output only. NOT the execution trace |

**Cross-model review is stronger than same-model review.** Same model shares training biases. Different providers catch different blind spots. The multi-model capability through LiteLLM exists for this purpose.

**NOT applied to:** Micro reflections (defeats zero-cost purpose), intermediate reasoning, memory recalls, routine procedural extraction. The cost of review must be justified by the blast radius of the output.

#### Pattern 5: Prompt Variation for High-Frequency Loops

Micro reflection and task retrospectives use rotating prompt framings to fight mode collapse.

**Micro reflection pool (rotate through):**
1. "What would surprise the user if they looked at the system right now?"
2. "What's the weakest link in the system's current state?"
3. "If I had to bet on what will go wrong in the next 6 hours, what would it be?"
4. "What signal am I NOT paying attention to that I should be?"
5. "What's the most valuable thing I could do right now that I'm NOT doing?"
6. "What assumption am I making that I haven't verified recently?"
7. "If a new operator took over right now, what would they notice first?"

**Task retrospective framings (rotate):**
1. "What surprised me about this task?"
2. "What would I do differently next time?"
3. "What did I assume that turned out to be wrong?"
4. "What capability would have made this easier?"

Each framing biases the LLM toward different types of observations. The aggregate across rotations gives broader coverage than any single prompt repeated indefinitely.

**Note:** With meta-prompting (Pattern 2) applied to Deep/Strategic reflections, prompt variation is only needed for the high-frequency loops (Micro, retrospectives) where meta-prompting would be overkill. The meta-prompter provides natural variation for the deeper reflections.

#### Pattern 6: Null Hypothesis with Maturity Calibration

For evaluative prompts, explicitly offer "nothing to report" as a valid — even preferred — output. But calibrate the threshold to the system's maturity, measured by DATA VOLUME rather than time elapsed.

**The framing:**
> "Review recent activity. The default answer is 'no significant patterns.' Only override this default if you find something meeting ALL of these criteria: [specific, evidence-backed criteria]. If nothing meets ALL criteria, output exactly: `NO_SIGNAL`."

**Why data volume, not time:** Time is an unreliable proxy for system maturity. A system that processes 500 interactions in week 1 is more mature than one that processes 50 interactions in month 2. The relevant maturity milestones are:

| Metric | "Early" (low threshold) | "Calibrated" (moderate) | "Mature" (high threshold) |
|--------|------------------------|------------------------|--------------------------|
| Procedural memory entries | < 50 | 50-200 | 200+ |
| User model evidence points | < 30 | 30-100 | 100+ |
| Outreach engagement data points | < 20 | 20-80 | 80+ |
| Task execution traces | < 100 | 100-500 | 500+ |
| Total memory items | < 500 | 500-2000 | 2000+ |

**Extraction threshold calibration:**
- **Early:** Most tasks WILL produce novel procedures or lessons. Threshold for "this is worth extracting" should be LOW. You're building the foundation.
- **Calibrated:** Common patterns are captured. Threshold rises. Looking for genuine novelty or refinements to existing procedures.
- **Mature:** Genuine novelty is rare. Threshold is high. Most extractions should be updates to existing procedures, not new entries.

**Predicting data milestones:** The system should track its own data accumulation rate and estimate when it will transition between maturity phases. This is purely programmatic: `current_procedural_count / daily_accumulation_rate = days_to_next_milestone`. Strategic reflection can use these projections to plan ahead ("approaching calibrated phase — tighten extraction threshold in ~2 weeks").

**The Self-Learning Loop tracks extraction utility over time.** If novel procedure discovery drops to near-zero but task quality isn't improving, that signals either: procedures aren't being used effectively, or the system is failing to learn from genuinely new situations. If discovery stays HIGH after reaching "mature" data volumes, that signals either: genuinely novel domains (good), or failure to recognize variants of existing procedures (dedup problem).

#### Pattern 7: LLM Interprets, Code Computes

The LLM should NEVER perform arithmetic, statistical analysis, or trend detection. These are computed programmatically and presented to the LLM as data to interpret.

| Ask the LLM | Compute programmatically |
|-------------|------------------------|
| "Is engagement declining?" | `engagement_rate_last_7d` vs `engagement_rate_prior_7d`. Present: "Engagement: 54% (last 7d) vs 72% (prior 7d). Delta: -18pp." |
| "Am I within budget?" | `spend_today / daily_budget`. Present: "Spent $4.20 of $8.00 daily budget (52.5%)." |
| "Is this error rate unusual?" | `current_rate` vs `30d_moving_avg`. Present: "Error rate 3.2%, vs 30-day avg 0.8% — 4x elevated." |
| "How confident is this procedure?" | `success_count / total_count`. Present: "4 successes, 1 failure (80%)." |
| "Salience of this signal?" | Compute base from historical engagement for similar topic. LLM adjusts ±contextual modifier. Present: "Base salience 0.70 (historical). Your contextual adjustment: [LLM fills in]." |

**Present computed data as measurements, not facts.** Include possible confounds: "Measurement: engagement dropped 18pp. Note: user was traveling last week — this may not reflect actual preference change." The LLM's job is to interpret in context, not to trust blindly.

### Failure Modes of These Patterns (Honest Assessment)

**Programmatic scaffolding creates rigidity.** Pre-computed metrics become unquestionable axioms. The LLM loses the ability to question whether the measurement ITSELF is meaningful. Mitigation: always present with confounds and interpretation framing.

**Grounded claims can suppress genuine intuition.** The speculative/grounded split helps, but the LLM may learn to avoid speculative claims to seem "more rigorous." Mitigation: explicitly prompt for hypotheses in addition to grounded observations. "What do you SUSPECT but can't prove?"

**Fresh-eyes review can create false confidence.** "Two models agreed, so it must be right." Two models sharing similar training data have correlated blind spots. Agreement doesn't equal correctness. Mitigation: treat agreement as higher confidence, not certainty. Track review agreement rate — if it's >95%, the review is probably not adding value.

**Meta-prompting adds a new failure mode: wrong questions.** If the meta-prompter asks the wrong questions, the entire reflection is misdirected. A brilliant answer to the wrong question is worthless. Mitigation: Strategic reflection periodically audits meta-prompt question quality — "Were the questions I asked last Deep reflection the right ones, in hindsight?"

**Maturity calibration requires accurate data volume tracking.** If the system miscounts its own data, it miscalibrates its thresholds. A data corruption event could reset maturity perception. Mitigation: data volume metrics are computed from actual MCP queries, not maintained counters. Can't drift from reality.

**Over-verification creates decision paralysis.** Every review pass, confidence check, and grounding requirement adds latency and creates opportunities to defer action. For a proactive assistant, being too cautious may be worse than being too confident — a system that never reaches out because it's never confident enough generates no engagement data to learn from. Mitigation: verification budget. Each loop gets a maximum number of review passes. After that, act on best available judgment.

### Deferred Patterns (Considered, Not Adopted)

These patterns were evaluated and deferred — either because they're lower-impact than initially assessed, introduce more complexity than they're worth at v3 scope, or are premature before real operational data exists.

**Position-aware context assembly.** Placing high-salience memories at the start/end of injection blocks to compensate for "lost in the middle" bias. Status: LOW-MEDIUM impact. The effect is real but smaller than the other patterns. Salience-ranked inclusion (already in design) matters more than position within the included set. **Revisit when:** operational data shows that mid-position memories are systematically underweighted in reflection outputs.

**Disagreement-as-signal tracking.** When primary and reviewer LLMs disagree, storing both assessments with a disagreement flag for later adjudication. Status: interesting but adds schema complexity for uncertain gain. **Revisit when:** fresh-eyes review is operational and disagreement rates can be measured. If disagreement is rare (>90% agreement), the tracking adds no value. If frequent (<70% agreement), the system has bigger problems than tracking can solve.

**Per-claim citation verification.** Programmatically parsing every LLM output to verify that cited memory IDs actually exist. Status: too rigid. Kills soft pattern recognition. The speculative/grounded tag system (Pattern 3) achieves the same goal with less brittleness — it doesn't verify citations, it separates claims into different trust tiers. **Revisit when:** confabulation is observed to be a real problem despite Pattern 3. If speculative tagging successfully prevents compound confabulation, this isn't needed.

**Full decomposition of Deep reflection into independent calls.** Running each of Deep reflection's jobs as a separate focused LLM call. Status: overengineered. Loses cross-cutting insights (the monolithic prompt's weakness is also its strength). Meta-prompting (Pattern 2) provides better decomposition — the meta-prompter sees everything holistically while the answerer gets focused questions. **Revisit when:** Deep reflection quality is observably poor due to tunnel vision or positional bias. Meta-prompting should be tried first.

**Adversarial "devil's advocate" pass.** A separate prompt that asks "what could go wrong with this?" before committing to an action. Status: redundant with fresh-eyes review (Pattern 4). The reviewer already provides a different perspective. Adding a dedicated adversarial pass on top of that is diminishing returns. **Revisit when:** fresh-eyes review is consistently failing to catch problems that an adversarial framing would catch. Possible indicator: user corrections on reviewed outputs.

**Relationship rhythm loop.** Dynamic matching of the system's interaction rhythm to the user's life patterns ("less responsive on weekends → shift outreach"). Status: deferred to post-v3. Static quiet-hours config is sufficient for v3. Dynamic rhythm learning requires substantial engagement data that won't exist until post-bootstrap. **Revisit when:** 3+ months of engagement data with clear temporal patterns. See Open Design Questions #11.

**Cost optimization loop.** Explicit feedback cycle for optimizing model/engine routing based on cost-per-value-delivered. Status: implicit in the compute hierarchy, not worth a dedicated loop at v3. Budget tracking exists. Engine selection exists. The explicit ROI optimization loop is premature before real cost data accumulates. **Revisit when:** 1+ month of per-engine cost tracking shows clear optimization opportunities.

---

## Open Design Questions (For Future Implementation Planning)

1. **Procedural memory confidence decay:** How does confidence decay without creating amnesia? Deferred — known to be complex, needs its own design session.

2. **User model persistence format:** Lean toward: structured JSON (machine-queryable) as the source of truth, with a periodically-regenerated human-readable summary document (USER_MODEL.md equivalent) for transparency.

3. **Drive weight initialization:** DECIDED — Initial weights: preservation 0.35, curiosity 0.25, cooperation 0.25, competence 0.15. Bounds: no drive below 0.10 or above 0.50. Weights are independent sensitivity multipliers, NOT normalized (sum-to-1 is coincidental). See Drive Weighting section.

4. ~~**Per-channel engagement inference:**~~ DECIDED — Promoted to design decision. See "Engagement Signal Heuristics (Per-Channel)" in the Self-Learning Loop section.

5. **Outreach rate limiting:** Max 3 proactive messages/day (not counting blockers/alerts). Prevents well-calibrated suggestions from becoming noise at volume.

6. **Health-mcp → outreach routing:** Critical alerts bypass the pipeline and go directly to outreach. Non-critical go through Awareness Loop → Reflection Engine for contextual assessment.

7. **Reflection Engine model selection:** DECIDED — See Compute Hierarchy in LLM Weakness Compensation section. Micro = local 20-30B (fallback: Gemini Flash free tier). Light = 20-30B or Gemini Flash. Deep = Sonnet-class. Strategic = Opus/best-available. Local model availability detection required (local machine not 24/7). Default: escalate when uncertain about model capability.

8. **Activation-based memory retrieval:** ACT-R's activation model (recency + frequency + connectivity) vs. pure embedding similarity. Explore hybrid during implementation — embedding for semantic match, activation for retrieval priority.

9. **Memory linking at storage time:** A-MEM's approach of linking new memories to related existing ones at write time (not just during dream cycle cleanup). Lightweight pass on every memory store — feasibility and cost to be validated during implementation.

10. **Capability gap accumulator schema:** What's the minimal schema for tracking capability gaps? Needs: task context, gap description, frequency count, first_seen/last_seen, feasibility assessment, `revisit_after` date for external blockers. Where does it live — memory-mcp as a memory type, or a dedicated SQLite table?

11. **Relationship rhythm loop (post-v3):** Dynamic interaction rhythm matching — "user is less responsive on weekends" → shift outreach timing. "User has been quiet for 3 days" → contextual check-in. Static quiet-hours config is v3; dynamic rhythm learning is deferred to post-v3.

12. **Observation utility tracking:** How to measure whether observations produced by the Reflection Engine are subsequently USED (retrieved, influenced a decision, acted upon). Needed for meta-learning loop (Spiral 15) to measure downstream utility rather than output volume. Possible: tag observations on creation, increment a `retrieved_count` on recall, track if retrieval led to action.

13. **Speculative hypothesis schema:** Schema for storing speculative claims from Pattern 3 (LLM Weakness Compensation). Needs: claim text, `speculative: true/false`, `evidence_count`, `hypothesis_expiry` timestamp, `confirmed_by` (list of memory IDs that provided confirming evidence), `source_reflection_id`. Confirm or archive logic: evidence_count >= 3 → confirm; past expiry with evidence_count == 0 → archive. Default expiry: 14 days.

14. **Local model availability detection:** The local machine running 20-30B models is not available 24/7. The system needs: (a) health check to detect whether local inference endpoint is reachable, (b) automatic fallback to Gemini Flash free tier / GLM5 when local is down, (c) re-routing back to local when it comes online, (d) tracking which model actually handled each call for cost/quality analysis. Implementation: likely a lightweight wrapper in the compute routing layer that checks endpoint health before dispatching.

15. **Meta-prompt question quality audit:** Strategic reflection should periodically audit whether the meta-prompter (Pattern 2) is asking the right questions. Metric: did the Deep/Strategic reflection that followed produce observations that were subsequently used (ties into #12)? If meta-prompt questions consistently lead to unused observations, the meta-prompter's signal interpretation needs adjustment. Open question: how to audit the auditor without infinite regress.

16. **Verification budget per loop:** Pattern failure mode: over-verification creates decision paralysis. Each loop needs a maximum review pass count. Proposed defaults: Micro = 0 review passes, Light = 0-1, Deep = 1 (meta-prompt + synthesis), Strategic = 2 (meta-prompt + synthesis + fresh-eyes on proposals), Outreach = 1 (fresh-eyes before sending). These should be configurable and auditable — if a loop consistently hits its review budget cap, either the cap is too low or the primary output quality needs investigation.
