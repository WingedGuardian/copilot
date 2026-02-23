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
- Output: strategic adjustments, configuration changes, high-level observations

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

---

## Layer 3: Self-Learning Loop

**Replaces:** Task retrospectives, lessons-learned extraction, post-mortem pipeline
**Type:** Agent Zero extension, runs after interactions and outreach events
**This IS the "Dopaminergic System" — learning from prediction errors**

### After Every Interaction

1. **Task retrospective:** What was attempted? What succeeded/failed? What was surprising? → store in memory-mcp (episodic)
2. **Lessons extraction:** Any reusable procedures learned? → store in memory-mcp (procedural)
3. **Prediction error logging:** "Expected X, got Y" → used by Reflection Engine to calibrate future expectations

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

**Tools:**
- `memory_recall` — Hybrid search (Qdrant vectors + FTS5 full-text, RRF fusion)
- `memory_store` — Store with source metadata + memory type tag
- `memory_extract` — Store fact/decision/entity extractions
- `memory_proactive` — Cross-session context injection
- `memory_core_facts` — High-confidence items for system prompts
- `memory_stats` — Health and capacity metrics
- `observation_write` — Write processed reflection/observation
- `observation_query` — Query by type/priority/source
- `observation_resolve` — Mark resolved with notes
- `evolution_propose` — Write identity evolution proposal (for SOUL.md / identity file changes)

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

6. **Graceful degradation** — If a preferred tool is unavailable, Genesis routes to the next best option without telling the user unless it affects quality or timeline. The fallback chain: Claude SDK → Bedrock → Vertex → OpenCode.

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

If all pass → spawn. If budget fails → downgrade model or surface to user. If reversibility fails on a non-approved capability → surface to user.

The LLM-based governance check (permissions + precedent + social simulation) runs only for OUTREACH and STRATEGIC decisions, not for every sub-agent spawn.

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

### What "Learns HOW to Learn" Actually Means in Practice

At L6, the system can observe that its own learning is working or not:

- "My Deep reflections have been producing no actionable observations for 3 weeks. Either the threshold for what triggers Deep reflection is too high, or the quality of the reflection itself is poor. Proposing: lower Deep trigger threshold from composite score 0.7 to 0.6, trial for 2 weeks."

- "I've been recalibrating salience weights after every outreach event, but this is causing oscillation — my threshold for 'architecture insights' has swung between 0.6 and 0.9 in the past month. Proposing: introduce a damping factor to smooth weight updates."

- "The Strategic reflection is generating useful findings but they're not influencing my Light reflections at all. Proposing: add a step to Light reflections that checks for pending Strategic recommendations before completing."

These are proposals — concrete, evidence-based, with a stated rationale — surfaced via outreach for user review. The user can approve, reject, or modify. Over time, if proposals are consistently approved, some bounded class of them (e.g., ±threshold adjustments) might become auto-approved. But never the structural ones.

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

## Open Design Questions (For Future Implementation Planning)

1. **Procedural memory confidence decay:** How does confidence decay without creating amnesia? Deferred — known to be complex, needs its own design session.

2. **User model persistence format:** Lean toward: structured JSON (machine-queryable) as the source of truth, with a periodically-regenerated human-readable summary document (USER_MODEL.md equivalent) for transparency.

3. **Drive weight initialization:** DECIDED — Initial weights: preservation 0.35, curiosity 0.25, cooperation 0.25, competence 0.15. Bounds: no drive below 0.10 or above 0.50. See Drive Weighting section.

4. ~~**Per-channel engagement inference:**~~ DECIDED — Promoted to design decision. See "Engagement Signal Heuristics (Per-Channel)" in the Self-Learning Loop section.

5. **Outreach rate limiting:** Max 3 proactive messages/day (not counting blockers/alerts). Prevents well-calibrated suggestions from becoming noise at volume.

6. **Health-mcp → outreach routing:** Critical alerts bypass the pipeline and go directly to outreach. Non-critical go through Awareness Loop → Reflection Engine for contextual assessment.

7. **Reflection Engine model selection:** Micro = local 20-30B or Gemini Flash free tier (near-zero cost). Light = utility model (cheap cloud). Deep = chat model (capable). Strategic = most capable available (high-stakes reasoning about system configuration).

8. **Activation-based memory retrieval:** ACT-R's activation model (recency + frequency + connectivity) vs. pure embedding similarity. Explore hybrid during implementation — embedding for semantic match, activation for retrieval priority.

9. **Memory linking at storage time:** A-MEM's approach of linking new memories to related existing ones at write time (not just during dream cycle cleanup). Lightweight pass on every memory store — feasibility and cost to be validated during implementation.
