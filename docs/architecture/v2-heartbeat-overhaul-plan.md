# V2 Heartbeat Overhaul — Planning Document

> **Status**: Planning. Phase 0 prerequisite landed (commit 5e56baf on `feat/navigator-duo-heartbeat-fix`).
> **Prerequisite**: ~~Phase 0 of the Navigator Duo plan must land first~~ DONE — gating bug fixed, daily sessions added.
> **Depends on**: Observing heartbeat behavior with real data now that Phase 0 has landed.

---

## Current State (2026-02-21)

### What exists
- `CopilotHeartbeatService` (subclass of upstream `HeartbeatService`) — `nanobot/copilot/dream/cognitive_heartbeat.py`
- Ticks every 2 hours via `process_direct()` with `skip_enrichment=True`
- Gathers: HEARTBEAT.md tasks, dream_observations, pending tasks, autonomy permissions, active lessons, morning brief
- Outputs to: `dream_observations` table (observations), `heartbeat_events` table (user_flag items, checklist logs)
- Model: `gemini-3-flash-preview` (Google AI free tier, $0.00/call)

### What's broken
- **Gating bug** (line 66-68): heartbeat never fires LLM when no observations/tasks exist → LLM has NEVER executed
- **No user visibility**: heartbeat output goes only to DB tables. No equivalent of dream cycle's `deliver_fn`
- **Stateless**: single `heartbeat` session key means no continuity between ticks (fixed in Phase 0 with daily sessions)
- **No proactive nanobot interaction**: heartbeat events exist in `heartbeat_events` table and get injected into nanobot's system prompt via `ExtendedContextBuilder` — but this only works when heartbeat actually produces events (which it never does due to the gating bug)

### What works (once the bug is fixed)
- `heartbeat_events` → nanobot system prompt injection (line 768+ of loop.py): events appear as system context, not user messages. Nanobot can naturally surface them in conversation
- `dream_observations` → dream cycle picks up observations for nightly reflection
- `_process_response()` parses structured JSON from LLM response correctly
- Morning brief injection (first tick after dream cycle gets reflection context)
- FM4 skip-if-busy (skips tick when dream cycle is running)

---

## Design Questions (to answer after observing heartbeat data)

### 1. What does the heartbeat actually produce on ambient ticks?
With no observations, no tasks, and just the base cognitive prompt — what does Gemini Flash generate? Is it useful or noise? This determines whether the prompt needs redesign or just the gating fix.

### 2. Is system prompt injection sufficient for proactive nanobot interaction?
Current flow: heartbeat → `heartbeat_events` → `ExtendedContextBuilder` injects into nanobot's system prompt → nanobot naturally surfaces in next user conversation.

**Pros**: No contamination (system context, not user message), nanobot uses LLM judgment on whether to surface.
**Cons**: Only fires on next user message. If user doesn't text for hours, the flag sits unseen.

**Alternative**: `deliver_fn` for urgent flags → WhatsApp/CLI delivery (like dream cycle). But this is the "proactive outbound messaging" that Amendment #2 Decision #43 explicitly deferred to V2.2.

### 3. Should heartbeat have its own tools?
Currently uses `process_direct()` which gives it the full agent tool suite. But with `skip_enrichment=True`, it doesn't get episodic memory or lessons injection. Should it have a restricted tool set? Or should it have DIFFERENT tools (e.g., read-only system health tools, changelog reader)?

### 4. How to prevent nanobot from parroting heartbeat context?
The risk: heartbeat writes "system health good" to `heartbeat_events`, nanobot gets it injected, user messages "hey", nanobot says "By the way, system health is good!" — which is useless noise.

**Potential mitigations**:
- Severity-based injection: only inject `medium` and `high` severity events into nanobot context. `info` stays in DB only.
- LLM guidance in AGENTS.md: "Heartbeat events are background context. Only mention them if they're relevant to the user's current topic or if something needs attention."
- Acknowledgment decay: events become `acknowledged` after N user turns (existing `acknowledged_turns` pattern in `task_context` design)

### 5. Stream of consciousness: how much continuity?
Daily session reset means the heartbeat loses context overnight. But some patterns span days ("LM Studio has been flaky for 3 days"). Should the morning brief carry forward multi-day patterns? Or should the dream cycle consolidate multi-day heartbeat patterns into observations that persist?

---

## Action Items (from initial discussion)

- [ ] **Phase 0 lands**: Fix gating bug, daily sessions, debug logging — observe behavior
- [ ] **Collect 1 week of data**: What does the heartbeat produce? What's useful vs noise?
- [ ] **Design deliver_fn**: Decide urgency routing (system prompt injection vs direct delivery vs both)
- [ ] **Design proactive nanobot interaction**: How heartbeat spurs nanobot action without contamination
- [ ] **Evaluate model choice**: Is Gemini Flash sufficient for cognitive heartbeat, or does it need a thinking model?
- [ ] **Design heartbeat prompt v2**: Based on observed behavior, redesign the cognitive prompt for better ambient awareness
- [ ] **Multi-day pattern handling**: How overnight context loss is handled (morning brief? dream observations? both?)
- [ ] **Tool restriction**: Should heartbeat have a restricted/specialized tool set?

---

---

## Copilot Web Dashboard — Foundation Requirements

> This section captures the broader dashboard requirement that emerged from heartbeat visibility needs. The dashboard is not heartbeat-specific — it's the master control panel for the entire copilot system.

### The Problem

Too many moving parts, too many things that break, too many things that need visibility, too many things to customize — and the only interface is WhatsApp chat + CLI + grepping systemd logs. The system has outgrown its interface.

### What Needs to Be Visible (Read)

| Category | What | Source |
|----------|------|--------|
| **Heartbeat** | Stream of consciousness, observations, flags, tick history | `heartbeat_events`, session files, `dream_observations` |
| **Dream Cycle** | Nightly reports, job checklists, reflection output, evolution proposals | `dream_cycle_log`, `dream_observations` |
| **Tasks** | Active/queued/completed/failed, step progress, retrospectives, duo metrics | `tasks`, `task_steps`, `task_retrospectives` |
| **Costs** | Per-model, per-task, per-service, daily/weekly/monthly trends | `cost_log`, `routing_log` |
| **System Health** | Service status, alert history, provider health, circuit breaker state | `alerts`, `heartbeat_events`, health check data |
| **Memory** | Identity files, lessons, core facts, episodic memory stats | Workspace files, `lessons`, Qdrant stats |
| **Autonomy** | Permission levels per category, pending observations awaiting approval | `autonomy_permissions`, `dream_observations` |
| **Navigator Duo** | Performance stats, disagreement themes, sycophancy risk, per-task metrics | `task_retrospectives.duo_metrics_json` |
| **Models** | Current routing plan, model pool, free tier status, provider status | `routing_log`, config, `free_tier_status` (future) |
| **Sessions** | Active sessions, sizes, background agent sessions | Session files |

### What Needs to Be Configurable (Write)

| Category | What | Currently Set Via |
|----------|------|-------------------|
| **Models** | Conversation model, escalation model, heartbeat model, navigator model, task model | `secrets.json` copilot config (requires restart) |
| **Autonomy** | Per-category permission levels (notify/autonomous/disabled) | Direct DB edits or `/autonomy` command |
| **Dream Observations** | Approve/reject/defer evolution proposals | `/dream` command |
| **Tasks** | Cancel, park, resume, approve deliverables | `/task`, `/cancel`, WhatsApp |
| **Lessons** | Activate/deactivate, adjust confidence | No UI currently |
| **Identity Files** | SOUL.md, AGENTS.md, navigator.md, etc. | Direct file edits |
| **Navigator** | Enable/disable, max rounds, max cycles | `secrets.json` copilot config (requires restart) |
| **Heartbeat** | Interval, model, HEARTBEAT.md tasks | Config + file edits |

### Technical Foundation

The dashboard should be:
- **A lightweight web app** served by the nanobot gateway (FastAPI already runs the gateway — add routes)
- **Read-only first** — visibility is the immediate need. Write operations come second.
- **SQLite-backed** — all data already lives in SQLite. The dashboard is a query layer + simple UI.
- **No auth initially** — runs on localhost or behind the existing server. Auth comes with remote access.
- **Real-time where it matters** — heartbeat ticks, task progress, alerts should update live (SSE or WebSocket)

### Phased Approach

**V1 (Visibility)**: Read-only dashboard. All the "What Needs to Be Visible" items above. Single-page app with tabs/sections. Data from SQLite queries. This alone eliminates the need for CLI debugging.

**V2 (Control)**: Write operations. Model switching, autonomy permissions, observation approval, task management. Replaces the scattered `/commands` and config file edits.

**V3 (Intelligence)**: Dashboard becomes interactive — ask questions about system behavior, get AI-generated insights, drill into anomalies. The dashboard itself uses an LLM to explain what's happening.

### Action Items

- [ ] Design dashboard API routes (FastAPI endpoints for each data category)
- [ ] Choose frontend approach (simple server-rendered HTML+HTMX vs React SPA vs something else)
- [ ] Implement V1 read-only dashboard after Navigator Duo plan lands
- [ ] Design heartbeat live view (replaces `journalctl | grep` debugging)
- [ ] Design task progress live view
- [ ] Design cost analytics view

---

## Related Documents

- Navigator Duo plan: `/home/ubuntu/.claude/plans/expressive-meandering-dove.md` (Phase 0)
- Brain Architecture: `2026-02-16-v2.1-brain-architecture-plan.md`
- Amendment #2 Decision #43: Heartbeat Foundation — build data model, defer proactive messaging
- Amendment #2 Decision #37: Heartbeat model upgrade to 20B local + cloud fallback
- Periodic Services table in CLAUDE.md
