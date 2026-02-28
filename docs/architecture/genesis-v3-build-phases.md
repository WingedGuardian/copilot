# Genesis v3: Build Phases — Safety-Ordered Implementation Plan

> **Ordering principle:** Build what's safest, most testable, and least likely to break first.
> Each phase depends on the previous phases working correctly. No phase should be started until
> its dependencies are verified.
>
> **This is a companion to the master design document** (`genesis-v3-autonomous-behavior-design.md`),
> which remains the full architectural reference. This document says WHAT to build and WHEN.
> The master doc says WHY and HOW each component works.

---

## Phase Dependency Map

```
Phase 0: Data Foundation
    │
    ├── Phase 1: The Metronome (Awareness Loop)
    │       │
    │       └── Phase 2: Compute Routing
    │               │
    │               └── Phase 3: Perception (Micro/Light Reflection)
    │                       │
    │                       ├── Phase 4: Memory Operations
    │                       │       │
    │                       │       └── Phase 5: Learning Fundamentals
    │                       │               │
    │                       │               └── Phase 6: Surplus Infrastructure
    │                       │
    │                       └── Phase 7: Deep Cognition
    │                               │
    │                               └── Phase 8: Outreach
    │                                       │
    │                                       └── Phase 9: Autonomy System
    │                                               │
    │                                               └── Phase 10: Calibration & Evolution
```

---

## Phase 0: Data Foundation

**Risk: LOW** — Pure schemas and CRUD. No LLM calls. No user-facing behavior. If a schema is wrong, you migrate it.

### What to Build

| Component | Schema/Table | Design Doc Reference |
|-----------|-------------|---------------------|
| Memory storage | Episodic, semantic, procedural memory tables | §4 MCP Servers → memory-mcp |
| Observation storage | Observations table with utility tracking fields (`retrieved_count`, `influenced_action`) | §Loop Taxonomy → Tier 4, Meta-Learning |
| Execution traces | Trace table per Execution Trace Schema | §Task Execution Architecture |
| Surplus staging | `surplus_insights` table (content, source_type, model, drive_alignment, confidence, TTL, promoted_to) | §Cognitive Surplus → Open Question #17 |
| Signal weights | Signal source weights table with adaptation bounds | §Awareness Loop → Signal-Weighted Trigger |
| Capability gaps | Gap tracking table (description, frequency, first/last seen, feasibility, revisit_after) | §Open Question #10 |
| Procedural memory | Procedures table with confidence, invocation_count, success_rate, version | §Procedural Memory Design |
| User model cache | Structured user model JSON store | §Open Question #2 |
| Speculative claims | Hypothesis table (claim, speculative flag, evidence_count, expiry, confirmed_by) | §Open Question #13 |
| Autonomy state | Per-category autonomy level tracking with evidence counts | §Autonomy Hierarchy |

### MCP Server Interfaces

Define the tool interfaces for all 4 MCP servers. Implementation can be stubs initially — the interface contract matters more than the implementation.

- **memory-mcp**: store, retrieve (hybrid: embedding + activation), link, update_activation, list_by_type
- **recon-mcp**: store_finding, query_findings, schedule_job, list_scheduled
- **health-mcp**: report_metric, query_health, get_error_rates, list_alerts
- **outreach-mcp**: queue_message, get_pending, record_engagement, get_channel_stats, list_channels

### Verification

- [ ] Every table can be created, read, updated, deleted
- [ ] Schema supports every query pattern described in the design doc
- [ ] MCP tool interfaces accept and return the expected types
- [ ] Foreign key relationships are correct (execution traces → procedures, observations → memories)

### What Breaks if This Is Wrong

Nothing user-facing. Worst case: schema migration later. But getting this right saves significant rework in later phases.

---

## Phase 1: The Metronome (Awareness Loop)

**Risk: LOW** — Purely programmatic. No LLM, no user-facing output. If the tick timing is wrong, signals queue up; they don't get lost.

### What to Build

- **5-minute tick scheduler** with hybrid event-driven + calendar guardrails
- **Signal collector** that reads from existing sources:
  - Inbox (new messages / pending tasks)
  - Health check results (from health-mcp)
  - Monitor state transitions
  - Recon findings (new items in recon-mcp)
  - Calendar events (scheduled reflection triggers)
- **Composite urgency score calculator** (formula in §Awareness Loop → Signal-Weighted Trigger)
- **Depth classifier**: score ranges → Micro / Light / Deep / Strategic
- **Critical event bypass**: urgent signals skip the 5-min tick and trigger immediately
- **Depth Escalation Protocol**: Awareness Loop stays sole coordinator; Reflection Engine sets escalation flags when micro/light depth is insufficient; critical override bypasses tick

### Dependencies

- Phase 0 (signal weights table, health-mcp interface for reading health data)

### Verification

- [ ] A signal with known weight produces the expected composite urgency score
- [ ] Score thresholds correctly classify to the right depth level
- [ ] Critical events bypass the tick and trigger immediately
- [ ] Calendar guardrails enforce minimum/maximum intervals between depth levels
- [ ] Multiple signals combine correctly (additive? weighted max? — implement per design doc)

### What Breaks if This Is Wrong

Reflections trigger at wrong depths or wrong times. Annoying but not dangerous — no user-facing output yet. Self-corrects once calibration loops (Phase 10) are active.

---

## Phase 2: Compute Routing

**Risk: LOW** — Infrastructure plumbing. No judgment calls. If routing is wrong, you get a slower or more expensive response, but the response still works.

### What to Build

- **Compute hierarchy dispatcher**:
  ```
  3B local (CPU)     → Embeddings, light extraction ONLY. No surplus, no reasoning.
  20-30B local (GPU) → Micro/Light reflection, extraction, surplus tasks. PRIMARY workhorse.
  Gemini Flash free  → DEFAULT FALLBACK for 20-30B when local is unavailable. Also surplus.
  Sonnet-class       → Deep reflection, judgment calls, quality gates.
  Opus-class         → Strategic reflection, identity proposals, high-stakes review.
  ```
- **Local model availability detection**: health check on local inference endpoint. Local machine is NOT available 24/7.
- **Automatic fallback**: when local is unreachable → route to Gemini Flash free tier seamlessly
- **Re-routing**: when local comes back online → route back to local for eligible tasks
- **Model tracking**: record which model actually handled each call (for cost/quality analysis)
- **Cost accounting**: per-call cost tracking, budget aggregation

### 3B Model Constraints (Explicitly)

The 3B model runs on CPU only and must stay responsive for embeddings and extractions. It CANNOT do:
- Reflection of any depth
- Root-cause classification
- Surplus thinking tasks
- Meta-prompting
- Any task requiring reasoning or judgment

### Dependencies

- Phase 0 (cost tracking schema)
- Network access to cloud model endpoints
- Local inference server setup

### Verification

- [ ] Request routes to correct tier based on task type
- [ ] Fallback triggers within reasonable timeout when local is unreachable
- [ ] Re-routing back to local works when endpoint comes back
- [ ] Every call is tracked with actual model used + cost
- [ ] 3B model is only dispatched embedding/extraction tasks

### What Breaks if This Is Wrong

Wrong model handles a task: either too expensive (waste) or too weak (bad output). Both are recoverable. The fallback chain prevents total failure.

---

## Phase 3: Perception (Micro/Light Reflection)

**Risk: MODERATE** — First LLM calls. But low stakes: no user-facing output, no config changes. If micro/light reflection produces poor observations, they just sit unused until learning corrects them.

### What to Build

- **Micro reflection**: Triggered by routine ticks with low urgency. Quick structured extraction:
  - Tag signals with categories
  - Extract key entities / topics
  - Produce structured summary (JSON, not prose)
  - Target model: 20-30B local or Gemini Flash fallback
- **Light reflection**: Triggered by moderate urgency or accumulated micro signals:
  - Situation assessment (what's happening?)
  - Memory queries (what do we know about this?)
  - Drive-relevant interpretation (why does this matter?)
  - Basic recommendation (what should we do about it?)
  - Target model: 20-30B local or Gemini Flash fallback
- **Prompt templates** for each depth level (parameterized, not hardcoded)
- **Structured output parsing** — validate LLM output against expected schema, retry on malformed

### Dependencies

- Phase 1 (Awareness Loop triggers reflection at correct depth)
- Phase 2 (Compute routing dispatches to correct model)
- Phase 0 (Observation schema for storing results)

### Verification

- [ ] Micro reflection produces valid structured tags from raw signals
- [ ] Light reflection produces coherent situation assessments
- [ ] Output conforms to expected schema (structured, not free-form prose)
- [ ] Malformed output triggers retry (with limit)
- [ ] Correct model tier handles each depth level

### What Breaks if This Is Wrong

Bad observations accumulate. Since nothing acts on them yet (learning loop isn't active), the blast radius is zero. Once Phase 5 connects the learning loop, bad observations could produce bad lessons — but null hypothesis defaults (Phase 5) mitigate this.

---

## Phase 4: Memory Operations

**Risk: MODERATE** — Extension of existing memory system. CRUD already exists in the current nanobot codebase. Adding semantic operations and activation scoring.

### What to Build

- **Activation scoring**: Each memory gets an activation score: `base_score × recency_factor × access_frequency × connectivity_factor`
- **Hybrid retrieval**: Combine embedding similarity with activation score for retrieval ranking
- **Observation storage**: Store observations from reflection engine with utility tracking fields (retrieved_count, influenced_action)
- **Lightweight memory linking at storage time**: When storing a new memory, run a quick similarity search and link to related existing memories (update connectivity scores)
- **Memory-mcp full implementation**: Replace stubs from Phase 0 with real operations

### Dependencies

- Phase 0 (schemas)
- Phase 3 (observations to store)
- Existing embedding infrastructure (3B model for embeddings)

### Verification

- [ ] Activation scores produce reasonable rankings (frequently accessed recent memories rank higher)
- [ ] Hybrid retrieval returns different results than pure embedding similarity (activation matters)
- [ ] New memories correctly link to related existing memories
- [ ] Utility tracking fields increment on retrieval and action

### What Breaks if This Is Wrong

Bad memory retrieval = wrong context for future reflections. Moderate blast radius but recoverable: memories can be re-scored, links can be rebuilt. Activation scoring errors self-correct over time through access patterns.

---

## Phase 5: Learning Fundamentals

**Risk: MODERATE-HIGH** — First feedback-dependent behavior. If learning goes wrong, it compounds. Incorrect lesson extraction poisons future behavior.

### What to Build

- **Post-interaction outcome classification**:
  - `approach_failure` → change behavior next time
  - `capability_gap` → log for future capability, don't learn "I'm bad at this"
  - `external_blocker` → classify as: user-rectifiable / future feasibility (with `revisit_after`) / permanent constraint
  - `success` → reinforce the approach
- **Engagement signal extraction** per-channel heuristics:
  - Reply speed, reply length, emoji/reaction usage, follow-up questions, explicit feedback
  - Channel-specific: WhatsApp reactions, email opens, web UI session duration
- **Basic procedural memory**:
  - Store procedures with confidence scores
  - Retrieve top-match for similar contexts
  - Confidence decay without reinforcement
  - Version tracking (procedures evolve)
- **Null hypothesis with maturity calibration**:
  - Default: assume current behavior is correct until evidence says otherwise
  - Maturity milestones by DATA VOLUME, not time:
    - `<50 procedures` = early (extract aggressively, high false-positive tolerance)
    - `50-200 procedures` = growing (moderate thresholds)
    - `200+ procedures` = mature (conservative, only extract novel patterns)
  - Apply different thresholds per maturity level

### Dependencies

- Phase 3 (reflection outputs to classify)
- Phase 4 (memory storage for lessons and procedures)

### Verification

- [ ] Outcome classification matches human judgment on a test set of interaction outcomes
- [ ] Engagement signals correctly detect positive vs. negative engagement (test with known examples)
- [ ] Procedures decay in confidence when not invoked over time
- [ ] Maturity calibration switches thresholds at correct data volume milestones
- [ ] Capability gaps are NOT learned as approach failures (critical correctness test)

### What Breaks if This Is Wrong

**This is the highest-leverage failure point.** Bad classification → bad lessons → systematic drift. Mitigation: null hypothesis means the system is conservative by default. Maturity calibration means it extracts aggressively early (when most things ARE novel) and gets pickier as the corpus grows. Monitor the capability_gap vs. approach_failure ratio — if it's heavily skewed, classification is probably wrong.

---

## Phase 6: Surplus Infrastructure

**Risk: LOW-MODERATE** — Scheduling and staging infrastructure. The surplus TASKS are low-risk because they only run on free compute and outputs go to staging, not production.

### What to Build

- **Surplus task queue** with priority model:
  - Priority considers: drive weights, recency of last audit, user activity patterns, time since last outreach candidate
  - Task types: self-improvement, user-value-ideation, system-optimization
- **Idle cycle detection**: Detect when no user interaction is active and compute is available
- **Cost-frequency enforcement**:
  - Free compute (local, Gemini free tier) = always run surplus tasks
  - Cheapest tier = run surplus most often
  - Above threshold = NEVER run for surplus
- **Surplus output staging area**: All surplus outputs go to staging, never directly to production
  - Outputs await promotion by next Light/Deep reflection review, or user approval
- **Local machine uptime pattern tracking** (start with config, learn refinements later)

### Dependencies

- Phase 2 (compute routing, cost tracking)
- Phase 3 (reflection engine to review staged outputs)
- Phase 4 (memory storage for promoted insights)
- Phase 5 (procedural memory for self-audit tasks)

### Verification

- [ ] Surplus tasks only execute on free/cheap compute
- [ ] Staging area correctly stores outputs without promoting to production
- [ ] Cost-frequency rule prevents surplus tasks from spending above threshold
- [ ] Priority model produces reasonable task ordering
- [ ] Idle detection correctly identifies available compute windows

### What Breaks if This Is Wrong

Worst case: wasted free compute or surplus outputs that never get reviewed. Very recoverable. The staging area prevents any surplus output from affecting the system without review.

---

## Phase 7: Deep Cognition

**Risk: HIGH** — Complex LLM orchestration. Multiple models in sequence. Meta-prompting quality directly affects everything downstream. If the meta-prompter asks bad questions, bad observations propagate through the entire system.

### What to Build

- **Meta-prompting protocol** (3-step):
  1. Cheap model (20-30B / Gemini) generates reflection questions based on available signals, recent observations, and current context
  2. Capable model (Sonnet) answers focused questions with depth
  3. Synthesis pass (Sonnet or Opus) integrates answers, catches cross-cutting patterns
  - The meta-prompter is the most critical call — if it asks the wrong questions, everything downstream is noise
- **Deep reflection**: Triggered by high urgency or accumulated light observations
  - Uses meta-prompting protocol
  - Produces structural insights, not surface patterns
  - Can propose system configuration changes (surfaced, not auto-applied)
- **Strategic reflection**: Triggered weekly or by significant events
  - Full meta-prompt → deep analysis → synthesis → proposal generation
  - Reviews capability gaps, drive weight trends, autonomy evidence
  - Proposes identity evolution candidates
- **Fresh-eyes review** on high-stakes outputs:
  - Cross-model review using a different model than the primary
  - Applied to: identity proposals, strategic config changes, outreach drafts, quality gates
  - NOT applied to: micro/light reflection, routine memory operations
- **Speculative hypothesis tracking**:
  - Hypotheses tagged `speculative: true` with expiry
  - Quarantined from future context until confirmed by 3+ independent evidence points
  - Expired hypotheses with no evidence → archived, not deleted
- **Verification budget per depth level**:
  - Micro = 0 review passes
  - Light = 0-1 review passes
  - Deep = 1 (meta-prompt + synthesis)
  - Strategic = 2 (meta-prompt + synthesis + fresh-eyes on proposals)
  - Hard cap: if a loop hits its budget, it ships what it has

### Dependencies

- Phase 2 (compute routing for multi-model orchestration)
- Phase 3 (micro/light as input signals)
- Phase 4 (memory for retrieving context and storing observations)
- Phase 5 (learning loop for outcome tracking on deep/strategic outputs)

### Verification

- [ ] Meta-prompting questions are measurably different from static prompt templates (not just reformulations)
- [ ] Deep reflection produces observations that are subsequently retrieved and used (track utility)
- [ ] Fresh-eyes review catches errors the primary model misses (test with known-bad outputs)
- [ ] Speculative claims are correctly quarantined from non-speculative context
- [ ] Verification budget caps are enforced (no infinite review loops)
- [ ] Strategic reflection proposals are coherent and evidence-based

### What Breaks if This Is Wrong

**Meta-prompting failure** is the critical risk. If the meta-prompter asks bad questions, every deep/strategic reflection downstream produces low-quality observations, which feed back into learning, which adjusts behavior based on noise. Mitigation: measure observation utility (Open Question #12), audit meta-prompt quality periodically (Open Question #15). If deep reflections consistently produce unused observations, the meta-prompter needs recalibration.

---

## Phase 8: Outreach

**Risk: HIGHEST** — User-facing. Trust damage from bad outreach is hard to reverse. One too many irrelevant proactive messages and the user disables the system.

### What to Build

- **Outreach pipeline**: staging → governance check → channel selection → timing → delivery → engagement tracking
- **Governance gate before every outreach**:
  - Is this within autonomy permissions?
  - Does it pass salience threshold?
  - Is the timing appropriate (not 3AM, not during known busy periods)?
  - Has similar outreach been sent recently? (dedup)
  - Budget check for paid channels
- **Proactive outreach ramp**:
  - Bootstrap: exactly 1 surplus-driven proactive outreach per day from day 1
  - Each outreach is labeled as surplus-generated
  - Growth: as engagement data accumulates and self-rating calibration improves, frequency increases
  - Autonomous level: system decides when and how often, based on demonstrated accuracy
- **Engagement tracking per outreach**:
  - Track: opened? replied to? reply sentiment? action taken? ignored?
  - Feed engagement signals back to Self-Learning Loop (Phase 5)
  - Per-category engagement rates (finding, insight, opportunity, digest)
- **Channel learning**:
  - Track which channel gets fastest/most-positive engagement per outreach type
  - Gravitate toward preferred channels
  - Respect explicit user preferences ("alerts always WhatsApp, digests Telegram")
- **Outreach categories** per design doc: Blocker, Alert, Finding, Insight, Opportunity, Digest

### Dependencies

- Phase 5 (learning loop for engagement signal processing)
- Phase 6 (surplus staging for surplus-driven outreach candidates)
- Phase 7 (deep cognition for salience evaluation and social simulation)
- Phase 4 (memory for user model, outreach history)

### Verification

- [ ] Governance gate blocks outreach that exceeds autonomy permissions
- [ ] Exactly 1/day surplus outreach during bootstrap phase (not 0, not 2+)
- [ ] Surplus-generated outreach is clearly labeled as such
- [ ] Engagement tracking correctly attributes user responses to the triggering outreach
- [ ] Channel learning produces measurably different channel selections over time
- [ ] Alert/blocker outreach bypasses normal pipeline and delivers immediately

### What Breaks if This Is Wrong

Trust erosion. Bad outreach → user disables proactive features → system can't grow → value proposition collapses. This is why outreach is Phase 8, not Phase 3. By the time outreach goes live, the reflection engine, learning loop, and memory system are all validated, so outreach decisions are made with functioning infrastructure. But even then: start conservative (exactly 1/day), label everything, track everything.

---

## Phase 9: Autonomy System

**Risk: HIGH** — Permission errors = trust damage. But by this phase, the system has sufficient infrastructure to make informed autonomy decisions.

### What to Build

- **Autonomy hierarchy** (L1-L7):
  - L1: Simple tool use → fully autonomous
  - L2: Known-pattern tasks → mostly autonomous
  - L3: Novel tasks → propose + execute with checkpoint
  - L4: Proactive outreach → threshold-gated
  - L5: System config → propose only, user approves
  - L6: Learning system modification → propose only, always user review
  - L7: Identity evolution → draft only, user decides
- **Evidence-based progression**:
  - Track: N successful executions without correction, consecutive successes at each level
  - Require: explicit user acknowledgment for level-up (silence ≠ approval)
  - Check-in: "I've been handling X autonomously with Y% success rate. Continue?"
- **Autonomy regression**:
  - 2 consecutive corrections → drop one level, re-earn
  - 1 user-reported harmful action → drop to default, full re-earn
  - Self-detected systematic error → self-propose regression
  - Regression is announced, not silent
- **Context-dependent trust ceiling**:
  - Direct session: earned level (no cap)
  - Background cognitive: L3 max
  - Sub-agent: L2 for irreversible, earned for reversible
  - Outreach: L2 until engagement data proves calibration
  - Later contexts restrict but never expand effective autonomy
- **CLAUDE.md handshake protocol**: Per-task session isolation for writing CLAUDE.md context. Sub-agents DO NOT share a single CLAUDE.md write path.

### Dependencies

- Phase 5 (learning loop for tracking success/correction data)
- Phase 8 (outreach for surfacing autonomy proposals)
- Phase 7 (deep cognition for evidence assessment)

### Verification

- [ ] L1 executes autonomously, L4+ requires governance gate
- [ ] Regression triggers correctly on consecutive corrections
- [ ] Context ceiling caps autonomy in background/sub-agent contexts
- [ ] Explicit user acknowledgment is required for level progression (not just absence of correction)
- [ ] CLAUDE.md writes are isolated per task (no concurrent writes to same file)

### What Breaks if This Is Wrong

Over-granting autonomy = the system does things the user didn't approve. Under-granting = the system is annoyingly cautious and never grows. Both are bad. The regression mechanism is the safety net: even if progression is too aggressive, regression snaps back on the first sign of trouble.

---

## Phase 10: Calibration & Evolution

**Risk: MODERATE** but requires a running system with real data. Cannot be meaningfully tested in isolation.

### What to Build

- **Drive weight adaptation**: Engagement data → adjust drive sensitivity multipliers. Bounds: no drive below 0.10 or above 0.50.
- **Signal weight adaptation**: Compare urgency predictions to actual outcomes → adjust signal source weights. Ceiling prevents thrashing.
- **Salience threshold self-adjustment**: If too many observations are ignored → lower threshold. If too many low-value observations clutter → raise threshold. Bounded ±20% without user approval.
- **Identity evolution**: Strategic reflection proposes SOUL.md changes. Always user-approved at L7.
- **Meta-learning**: Track whether reflections produce useful observations (utility metric). If a reflection depth consistently produces unused outputs, adjust the trigger or the prompt.
- **Capability expansion tracking**: Aggregate capability gaps, assess feasibility periodically, notify when previously-blocked capabilities become available (new model releases, new tools, user grants permission).
- **User model deepening**: Continuous refinement of user preferences, patterns, goals, blind spots. Periodic human-readable summary generation.

### Dependencies

- All previous phases (this layer tunes everything else)
- Sufficient real interaction data to calibrate against

### Verification

- [ ] After N interactions, drive weights have moved in directions consistent with engagement signals
- [ ] Signal weights converge toward useful urgency assessments (fewer false alarms, fewer missed urgencies)
- [ ] Salience thresholds self-adjust within bounds without oscillating
- [ ] Identity evolution proposals are coherent, evidence-based, and surfaced for user approval
- [ ] Meta-learning correctly identifies low-utility reflection patterns

### What Breaks if This Is Wrong

Slow drift. Unlike Phase 5 (learning fundamentals) where bad classification causes immediate harm, calibration errors here are gradual. Drive weights that drift slightly wrong produce subtly worse prioritization. The safety net: all weights have bounds, all changes are auditable, fundamental changes require user approval (L6/L7).

---

## Cross-Cutting Concerns (Apply to Every Phase)

### Testing Strategy

Each phase has its own verification criteria (listed above). But cross-phase testing is also needed:

- **Integration tests**: Does Phase N correctly use Phase N-1's output? (e.g., does the awareness loop correctly trigger reflection at the right depth?)
- **Regression tests**: Does adding Phase N break any Phase N-k behavior?
- **Load tests**: Can the system handle concurrent signals without dropping or duplicating?

### Observability

Every phase should produce structured logs that answer:
- What happened? (action taken)
- Why? (signal that triggered it, score that classified it)
- What model handled it? (for cost/quality tracking)
- What was the outcome? (success/failure/deferred)

### Rollback Plan

Each phase should be independently disableable. If Phase 7 (deep cognition) starts producing garbage, you should be able to disable it and fall back to Phase 3 (micro/light only) without breaking anything. Feature flags or config-driven enablement for each phase.

---

## What This Document Does NOT Cover

- **Container/infrastructure setup** — Covered in `genesis-v3-dual-engine-plan.md`
- **Framework selection and migration** — Covered in `genesis-v3-dual-engine-plan.md`
- **Detailed architectural rationale** — Covered in `genesis-v3-autonomous-behavior-design.md`
- **Open design questions** — Listed in `genesis-v3-autonomous-behavior-design.md` §Open Design Questions
- **Identity philosophy** — Covered in `genesis-v3-vision.md`

This document is the build plan. For "why does it work this way?" read the master design doc. For "who is Genesis?" read the vision doc.
