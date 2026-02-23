# V2 Brainstorming Session — 2026-02-16

> **Note**: This session produced the initial V2.1 Task Lifecycle plan, which was later superseded by the Brain Architecture plan (`2026-02-16-v2.1-brain-architecture-plan.md`). The approach (Enhanced Nanobot/Approach C) carried forward, but specific components (regex task detector, heuristic feedback handler) were dropped in the later redesign.

> Summary of the design conversation that produced the V2.1 Task Lifecycle Engine plan and revised V2 Architecture.

---

## Starting Point

After completing V1 and the pre-V2 cleanup (doc fixes, monitor_chat_id auto-derivation, single commit of 57 files), we stepped back to challenge the existing V2 Architecture doc before building anything.

**The user's challenge**: V1 is nanobot with nice upgrades and a memory system. To get AI that "just works" autonomously — completing tasks, building real projects, proactively doing work — we need to think hard about HOW, not just hope the features add up to value.

---

## Key Questions & Answers

### Q: What concrete thing did you wish V1 had done WITHOUT you asking?
**A**: Done actual work. Not reminders, not summaries — actual work product.

### Q: What kind of work?
**A**: All of it — coding, research, ops/admin, content creation. But more broadly: "Take WHATEVER I have on my to-do list — whether it be something as basic as a car registration renewal, all the way up to building a fully functional online business — and get as much of it that can be done digitally, done."

### Q: Why autonomy? What's wrong with the interactive Claude Code workflow?
**A**: All of the following:
- Not always at a desk (mobile-first, assign work from phone)
- Parallelism (multiple things happening while focused on one)
- Continuity (work continues across sessions without re-explaining)
- Delegation mindset (think at the "what" level, not "how")

### Q: Imagine V2 working perfectly. You text "build me a landing page." What happens?
**A**: "It asks clarifying questions and gets thorough detail. Then goes and works. Comes back, tells me what it was able to do, what it couldn't, and there will be more questions. Then it goes forth and iterates again, until we ultimately have a finished product ready for my review. But simpler tasks wouldn't require that process — more like 'just do it.'"

### Q: What's your role?
**A**: Product owner. "I describe what I want, review deliverables, make decisions. The system does 80%+ of the hands-on work."

### Q: What kinds of projects?
**A**: Not just software. "Whether it be doing something as basic as a car registration renewal, all the way up to building a fully functional online business." The system is a **digital executive assistant**, not a coding agent.

### Q: For coding tasks, should nanobot use its own agent loop or shell out to an external agent?
**A**: Leaning toward shelling out — could be Claude Code or something like OpenCode. Not rebuilding what coding agents already do.

---

## Critical Reframe

**Before**: The V2 Architecture doc described 8 phases of features (proactive scheduler, tiered reviews, deeper lessons, autonomous tools, task persistence, sub-agents, dashboard).

**After**: The user isn't building a chatbot with more features. They're building an **asynchronous task execution engine with a conversational interface**. The product is: "I tell it what needs to get done, it figures out HOW and does it."

This means:
- The task lifecycle (intake → decompose → execute → checkpoint → iterate → complete) is the skeleton everything hangs on
- Model routing isn't "which model answers this chat message" — it's "which model plays which role in which workflow"
- The original V2 features (reviews, lessons, proactive scheduling) are still valuable — they make the task engine smarter. They're not replaced, they're recontextualized.

---

## Model Routing Discussion

The user raised an important point about the model pool: "We need to be able to choose from a broad list of models that will simultaneously allow us to minimize costs, take advantage of free compute, and leverage the latest models and emerging capabilities by having a living pool list of models to choose from."

**Key insight from the user**: Before designing the model pool, we need to design the system that uses it. Before that, we need to be clear on WHAT we're building. The dependency chain is: WHAT → SYSTEM DESIGN → MODEL POOL.

**Architectural shift identified**: V1 has one interface — the main model. V2 needs multiple actors:
- **Thinker** (Opus-class): Decomposition, re-planning — executive reasoning
- **Coordinator** (Sonnet/Gemini-class): Task management, progress reporting
- **Workers**: Specialized per step, assigned by the thinker

The V1 5-tier table remains valid for conversational routing. The role-based system is additive for task execution.

The user has a Gemini conversation with more thoughts on this topic — deferred to the model pool design phase (V2.2).

---

## Architecture Decision: Three Approaches Considered

### Approach A: Smart Dispatcher
Nanobot itself becomes the brain. Coordinator decomposes tasks, dispatches to tools via shell/subagent.
- **Pro**: Everything in one system
- **Con**: Nanobot's agent loop wasn't designed for multi-hour autonomous execution

### Approach B: New Orchestration Layer
Build a new task engine above nanobot. Nanobot handles WhatsApp, engine handles task lifecycle.
- **Pro**: Clean separation, purpose-built
- **Con**: More moving parts, two systems to maintain

### Approach C: Enhanced Nanobot (CHOSEN)
Remove constraints that prevent nanobot from doing this already. Extend TaskWorker, increase limits, wire decomposition.
- **Pro**: Least new code, builds on proven infrastructure
- **Con**: May hit architectural ceilings
- **Escape hatch**: Pivot to Approach B with CrewAI or similar if we hit walls

**Decision**: Approach C — path of least resistance. Also search for open-source projects that could serve as Plan B bolt-ons.

---

## Open Source Landscape Research

Searched for frameworks that could serve as Plan B or bolt-on capabilities:

**Task Orchestration**:
- **CrewAI** — Role-based multi-agent orchestration. Python, production-ready. Closest to Plan B.
- **Claude-Flow** — Multi-agent swarms on Claude Code via MCP. Claude-locked.
- **SuperAGI** — Autonomous agent framework. Heavy, enterprise-oriented.
- **Agent S** — Computer-use agent (GUI). Surpassed human-level on OSWorld. Relevant for browser tasks.
- **MassGen** — Multi-agent parallel execution in terminal.

**Coding Execution**:
- **OpenCode** — Open-source Claude Code alternative. 95K GitHub stars, 75+ models, multi-session. Strong candidate as the coding worker for V2.2.
- **Aider** — Git-aware coding assistant. Lighter-weight option.

---

## V2.1 Scope Decision

**First milestone**: Task lifecycle engine with proof-of-life on a research task.

**In scope**:
- Task detection from WhatsApp messages
- Decomposition using frontier model
- Step execution via subagents + shell
- Progress notifications to WhatsApp
- Feedback loop (natural language)
- `/tasks`, `/task <id>`, `/cancel <id>` commands

**NOT in V2.1** (deferred):
- Coding agent integration (OpenCode) — V2.2
- Model pool redesign — V2.2+
- Browser automation — V2.3
- External to-do integration — V2.3
- Parallel task execution — V2.2
- Priority/urgency system — V2.2

**Proof of life**: Text "Research the top 3 VPS providers under $20/month and give me a comparison table." Get a structured comparison delivered to WhatsApp asynchronously.

---

## Existing Infrastructure (From Code Exploration)

Discovered that V1 has more task infrastructure than expected:

| What | Status | Notes |
|---|---|---|
| TaskManager (SQLite CRUD, steps, deps) | Working | Full persistence layer |
| TaskWorker (polls 60s) | Running | `decompose_fn` = None, needs wiring |
| TaskTool (agent-accessible) | Registered | Create/list/complete actions |
| SubagentManager | Working | 15-iter limit (needs increase) |
| ExecTool (shell) | Working | 60s timeout (needs extension for tasks) |
| Message bus + WhatsApp delivery | Working | Just fixed monitor_chat_id auto-derivation |
| Dream cycle (10 jobs, daily 7 AM) | Running | Was generating reports but silently discarding (monitor_chat_id was empty) |

**Key finding**: Dream cycle was running and generating reports the whole time — just never delivering them because `monitor_chat_id` was empty. Fixed in this session by auto-deriving from `whatsapp.allow_from`.

---

## UX Decisions

- **Task creation**: Natural language via WhatsApp ("build me a portfolio site")
- **Progress updates**: System-initiated WhatsApp messages with checkmarks/status
- **Feedback**: Natural language replies — system resolves which task from context. No structured format required.
- **Task status**: `/tasks` for overview, `/task <id>` for detail, `/cancel <id>` to stop

---

## Documents Produced

1. `2026-02-16-v2.1-task-lifecycle-design.md` — Full implementation plan for V2.1
2. `Executive Co-Pilot V2 Architecture.md` — Revised V2 architecture (task-lifecycle as centerpiece, operational intelligence preserved)
3. This file — Brainstorming session record
