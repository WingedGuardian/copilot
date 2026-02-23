# V2 Architecture Interview Transcript — 2026-02-18

> Detailed interview probing the user's vision for V2.1 architecture: technical implementation, UX, concerns, tradeoffs. Every question, option set, and user response captured verbatim.

---

## Q1: Interface Agent ↔ Orchestrator Handoff

**Question**: The brain architecture separates the Interface Agent (existing nanobot loop) from the Orchestrator (ephemeral per-task coroutine). What's the cleanest mental model you have for how these two talk to each other — and where does the handoff actually happen in the code?

| Option | Description |
|--------|-------------|
| Interface agent creates a task record, Orchestrator polls for it | TaskWorker already polls SQLite — Orchestrator wakes on task creation event |
| Interface agent directly spawns an Orchestrator coroutine | asyncio.create_task() inside the agent loop when task detected |
| Not fully designed yet — still fuzzy on this | The handoff mechanism is unclear or has competing ideas |
| Something else entirely | I have a different mental model |

**Answer**: *"I genuinely don't know. I need your input on this. This is too far above my pay grade."*

**Takeaway**: Technical handoff mechanism is deferred to implementation. User trusts the engineering decision here.

---

## Q2: Success UX — What Does a Completed Task Look Like?

**Question**: The proof-of-life task is: 'Research the top 3 VPS providers under $20/month and give me a comparison table.' When the result comes back to WhatsApp, what does success ACTUALLY look like? Be specific — what's in the message?

| Option | Description |
|--------|-------------|
| A clean formatted table with provider name, price, specs, verdict | Structured, scannable, fits in a WhatsApp message |
| A short summary + link to a file or doc with full details | WhatsApp is just the notification; full content lives elsewhere |
| Multiple messages: progress updates during, then final result | User sees the work happening in real time |
| I don't know yet — need to decide this | The delivery format is still open |

**Answer**: *"This actually sounds more like something nanobot could just do itself. I envision an orchestrator being spawned for tasks that involve multiple steps and iterations and involve actual results: not just 'here's what I found on the web'. I think the proof of life doesn't even meet the definition of a task. But if it matters, I would pick #1."*

**Takeaway**: The VPS research proof-of-life is too trivial to warrant an orchestrator. Real tasks produce deliverables, not answers. This redefines the task threshold.

---

## Q3: Feedback UX — How Does the User Respond to Orchestrator Questions?

**Question**: When the orchestrator sends a draft and asks 'Does this look right before I proceed?' — how does the user actually respond? What's the interaction model?

| Option | Description |
|--------|-------------|
| Just reply naturally in WhatsApp — system figures it out | No structure required. 'Looks good' or 'change X' both work |
| Buttons or quick replies in WhatsApp | Approve / Reject / Modify buttons on the confirmation message |
| Still unclear — need to design this | Feedback loop UX is undecided |
| No confirmation step — just go execute, I'll review the result | Skip the draft-review step entirely for speed |

**Answer**: **Just reply naturally in WhatsApp — system figures it out.**

---

## Q4: What Constitutes a Real Task?

**Question**: You said a real task involves 'multiple steps and iterations and actual results.' Give me your clearest example of a V2.1 task that DOES warrant an orchestrator — something you'd actually want to assign right now.

| Option | Description |
|--------|-------------|
| Build me a landing page for [product] and deploy it | Multi-step: design, code, deploy — real deliverable |
| Set up a GitHub repo, scaffold a Python project, push initial commit | Coding + git operations — tangible artifact |
| Draft a business plan for X and format it as a Google Doc | Research + writing + file creation |
| Something else — I have a specific example in mind | Tell me in notes |

**Answer**: *"I'd say 1 and 2 are definites. 3 is something that nanobot could probably do on its own with a Google Doc integration (MCP or skill?)."*

**Takeaway**: Landing pages and code scaffolding = real tasks. Document drafting alone doesn't meet the bar unless it involves multi-iteration quality refinement.

---

## Q5: Where Does 'Complex Chat' End and 'Task' Begin?

**Question**: Here's the threshold question: where does 'complex chat' end and 'task' begin? What's the bright line?

| Option | Description |
|--------|-------------|
| If it requires tools beyond the current session (shell, file write, deploy) | Tool dependency is the signal |
| If completing it will take more than a few minutes of wall-clock time | Duration is the signal |
| If the user expects a deliverable, not just an answer | Output type is the signal |
| If it requires more than one back-and-forth or iteration cycle | Interactivity pattern is the signal |

**Answer**: *"Definitely #3. But #4 could very well be too IF it's not just a conversation with some web searches. Again, probably ties back into 'what would we actually deliver for this' above and beyond a 'write me a paper'. For example, I am working on a cloud architecture RFP response right now. If all I needed was a simple document or for nanobot to give me its ideas or consolidate my thoughts, that's nanobot work. But if I want to upload many documents and have it build out the entire RFP for me, which will require multiple iterations of back-and-forth questions as well as corrections and improvements to make a quality product, that's definitely a task."*

**Takeaway**: The bright line is **deliverable + iteration**. A simple document is chat. A multi-iteration quality product is a task. The RFP example is the canonical real-world task.

---

## Q6: Where Does the Deliverable Live?

**Question**: For the RFP task — 'upload many docs, build out the entire RFP' — where does the final deliverable actually live? Not the progress updates, the THING you hand to the client.

| Option | Description |
|--------|-------------|
| A Google Doc (shared link in WhatsApp) | Native cloud doc, easiest to share externally |
| A file in the repo / workspace (path in WhatsApp) | Local file, I pull it when I need it |
| A structured WhatsApp message or thread | Stays in the interface, no external doc |
| Depends on the task — no single answer | Landing page = deployed URL, RFP = Google Doc, code = GitHub repo |

**Answer**: *"It depends on the task, but let's put code and work that can go on GitHub there, and err on the side of local storage on the VM where possible. Some tasks might involve a finished product in AWS though, so it just depends."*

**Takeaway**: Default to local VM storage and GitHub. No single delivery channel — task type determines where the artifact lives.

---

## Q7: How Long Can a Task Block Waiting for User Input?

**Question**: During the RFP build, the orchestrator has a question — 'Section 3 asks about your on-prem failover policy. I don't see this in your docs. Do you have one, or should I draft a generic policy for review?' You're on a call. How long is it acceptable to block execution waiting for your answer?

| Option | Description |
|--------|-------------|
| Indefinitely — pause and wait until I respond | Don't proceed without my input on ambiguous decisions |
| A few hours — then proceed with best judgment and flag the assumption | Reasonable for async; system makes a call and tells me |
| 24 hours — then proceed or cancel | I set the deadline when I assign the task |
| Never block — always proceed with best judgment, I'll review the output | Don't interrupt me, make the call |

**Answer**: **Indefinitely — pause and wait until I respond.**

**Takeaway**: No auto-proceed. The system respects user authority on ambiguous decisions. Patience over assumptions.

---

## Q8: Bootstrap Plan Confirmation

**Question**: The design doc says 'first 30 days: orchestrator shows plan before executing (bootstrap confirmation).' Your instinct on this — does every task need a plan approval step, or should the orchestrator just start and check in at natural milestones?

| Option | Description |
|--------|-------------|
| Always show plan first — I want to approve before any work starts | Zero risk of wasted effort on the wrong direction |
| Show plan for complex/long tasks; skip for simple ones (LLM decides) | Balance speed vs oversight based on task complexity |
| Just start, update me as it goes, ask if blocked | Move fast; I can redirect if it's going wrong |
| Let me configure per-task — 'plan first' or 'just go' | Opt-in confirmation, not mandatory |

**Answer**: *"Let's go with always plan first — this may change later, but I want to manually make that call. No day 30 cutoff."*

**Takeaway**: Mandatory plan approval before execution. No automatic sunset. User explicitly removes the guard rail when they're ready — not on a timer.

---

## Q9: Concurrency UX — Chat During Task Execution

**Question**: The design doc separates 'Interface Agent' (always on, handles chat) from 'Orchestrator' (spawned per task, ephemeral). Right now nanobot runs as a single agent loop. When you text the running bot WHILE an orchestrator is executing a 3-hour task, what should happen?

| Option | Description |
|--------|-------------|
| Nanobot responds normally to conversation; orchestrator runs in background silently | Clean separation — chat and tasks are fully independent |
| Nanobot prioritizes task-related messages (feedback, cancels); handles other chat too | Task context is foregrounded but chat still works |
| Nanobot tells me 'a task is running, here's status' when I text during execution | Proactive status injection into conversation |
| I haven't thought about this — good question | Need to decide |

**Answer**: *"I'd say #4 — I'm leaning more towards 1, but until we have proof that it's robust and I can trust it to handle long, maybe even multi-day tasks, we probably need something more like 2 for me to keep an eye on it. Can we build in the path to start on 2 and then go to 1 later by telling nanobot directly?"*

**Takeaway**: Start with verbose mode (#2: task-aware, proactive status). Build a configurable path to silent mode (#1) when trust is established. Toggled via nanobot conversation (e.g., `/settings tasks verbose|silent`).

---

## Q10: Worker Tool Whitelist

**Question**: The design gives workers a 'tools whitelist' — each worker only gets the tools it needs. For V2.1 (no coding agent yet), what tools do you actually need workers to have? Pick all that apply.

| Option | Description |
|--------|-------------|
| Web search + web fetch (research) | Browse and retrieve web content |
| Shell / exec (run commands, scripts, git) | Terminal access on the VM |
| File read/write (create documents, edit files) | Local filesystem access |
| WhatsApp send (worker sends messages directly) | Workers can message the user themselves |

**Answer**: **Web search + web fetch, File read/write.** (Shell and WhatsApp send excluded.)

**Takeaway**: V2.1 workers get research + file tools only. No shell access (security concern). No direct WhatsApp (workers communicate through orchestrator, not directly to user).

---

## Q11: Task Parallelism

**Question**: Can multiple tasks run in parallel right now? If you assign two tasks back-to-back, do they execute simultaneously or queue?

| Option | Description |
|--------|-------------|
| Parallel — both run at the same time if resources allow | Max throughput; risk of resource contention |
| Queue — one finishes before next starts | Safe, predictable, lower complexity |
| Configurable — I set a concurrency limit | 'max_parallel_tasks = 2' type setting |
| Not decided yet | Need to think about this |

**Answer**: **Queue — one finishes before next starts.**

**Takeaway**: Sequential execution in V2.1. Simpler, predictable. Parallelism deferred to V2.2+.

---

## Q12: Why No Shell Access for Workers?

**Question**: You didn't pick shell/exec for workers. But tasks like 'scaffold a GitHub repo' or 'deploy a landing page' require shell commands. What's your thinking — security concern, or you're deferring shell access to V2.2 with the coding agent?

| Option | Description |
|--------|-------------|
| Security concern — giving workers raw shell access feels risky | Don't want an LLM running arbitrary commands on the VM |
| Deferring — shell belongs with the coding agent in V2.2 | V2.1 is research + writing; coding comes later |
| Oversight concern — I want to approve shell commands before they run | Shell requires human confirmation, not autonomous |
| I changed my mind — workers should have shell access | It's needed for real tasks |

**Answer**: *"Maybe I should say 4, but my rationale was 1."*

**Takeaway**: Security concern is the driver. Workers need shell, but raw shell access feels dangerous. Resolution: sandboxed workspace directory.

---

## Q13: Queue Tradeoff

**Question**: The queue model means if you assign a 3-hour RFP task and then text 'cancel my 2pm meeting' 30 seconds later, the calendar task waits 3 hours. Does that bother you, or is it fine?

| Option | Description |
|--------|-------------|
| That bothers me — short tasks should not wait behind long ones | Need priority queue or parallel track for quick tasks |
| Fine — I can handle calendar myself; tasks are for substantial work | Trivial requests shouldn't be tasks anyway |
| Fine for now, but we need priority lanes later | Accept the limitation in V2.1; fix in V2.2 |
| Queue is wrong — tasks should run in parallel by default | Rethink the concurrency model |

**Answer**: *"The question is wrong: cancel my 2pm meeting should be an MCP or skill call, not a task. It doesn't meet the bar that I laid out earlier."*

**Takeaway**: The queue tradeoff is a non-issue because trivial requests never become tasks. The task threshold (deliverable + iteration) naturally filters these out.

---

## Q14: What Would Make Shell Access Safe?

**Question**: On shell access: your gut says security risk, your head says you need it. Here's the real question — what would make shell access feel safe enough to give to workers?

| Option | Description |
|--------|-------------|
| A confirmation step — worker proposes commands, I approve before execution | Human-in-the-loop for shell. Slower but safe. |
| Sandboxing — workers only touch a designated workspace directory | Can't rm -rf /, can't touch secrets.json, scoped to /workspace/tasks/ |
| Audit log — every shell command logged and visible via /task <id> | No pre-approval, but full visibility after |
| All three of the above | Confirmation + sandbox + audit |

**Answer**: **Sandboxing — workers only touch a designated workspace directory.**

**Takeaway**: Scoped filesystem access. Workers can execute commands but only within a task workspace. No access to secrets, system files, or other tasks' directories.

---

## Q15: Task Detection — How Does Nanobot Decide?

**Question**: Task detection: how does nanobot decide if your message is a task (spawn orchestrator), a skill/MCP call (handle directly), or plain chat? What's the classification logic?

| Option | Description |
|--------|-------------|
| LLM decides on every message — no heuristics | Single classify() call before the agent loop. Clean but adds latency every message. |
| Heuristics first, LLM for ambiguous cases | Fast path for obvious chat; LLM only when needed |
| Explicit trigger — user prefixes with /task or a specific phrase | No ambiguity; user declares intent explicitly |
| Not sure — this is a hard problem | Need to think more carefully about the classifier |

**Answer**: *"The LLM makes the call on its own. It should ask for confirmation before doing so, and gather an initial interview of the task and its requirements and the desired outcomes."*

**Takeaway**: No heuristics. LLM identifies task potential → confirms with user → conducts intake interview (requirements, desired outcomes) → then creates task and shows plan. The intake interview happens IN the conversation before any orchestrator is spawned.

**Follow-up clarification (added post-interview)**: The intake has TWO phases:
1. **Nanobot-side intake**: LLM detects task, confirms with user, gathers requirements and desired outcomes.
2. **Orchestrator-side intake**: Orchestrator spins up, reviews what nanobot sent, and can **immediately come back with more questions BEFORE starting any work** if it identifies gaps, ambiguities, or assumptions that would be too large. The orchestrator is the domain expert — it may catch things the generalist nanobot missed (e.g., "you said deploy to AWS but didn't specify region" or "this RFP template requires a compliance section — do you have SOC2?").

Only after the orchestrator is satisfied with the information does it proceed to plan presentation and execution.

**Latency vs. thoroughness distinction (added post-interview)**: This two-phase intake exists not just because the orchestrator is a domain expert, but because the two agents operate under fundamentally different time pressures:
- **Nanobot** is latency-sensitive — the user is in a live conversation and doesn't want to wait 1+ minutes for a response. So nanobot's intake will naturally be faster and less thorough, even if it were the same model with the same context.
- **Orchestrator** has zero latency pressure — thoroughness and accuracy are what matter. It can think as long as it needs. More thinking = better outcomes. The orchestrator WILL catch things nanobot misses, not because it's smarter, but because it's not racing to respond.

This means the two-phase intake isn't redundant — it's structurally necessary. Different time constraints produce different quality of analysis even from identical models.

---

## Q16: What Should the System Learn from Completed Tasks?

**Question**: The dream cycle currently runs daily and updates identity files (soul, memory, etc.). When a task completes, what should the system learn from it? What should be different about nanobot AFTER it successfully builds your first landing page?

| Option | Description |
|--------|-------------|
| Add a lesson: 'user prefers X stack, Y deployment pattern' — applied to future tasks | Preferences and patterns extracted from task outcomes |
| Build a task template: 'landing page' task type has known workflow steps | Reusable workflow patterns for similar future tasks |
| Update capability map: 'can now do landing pages autonomously' | Self-knowledge of what the system can and can't do |
| All of the above — and dream cycle synthesizes it nightly | Full learning loop: preferences + templates + capabilities |

**Answer**: *"It (or anything else for that matter) shouldn't touch identity files without either my approval or express instruction. But to your question, I'm not fully sure myself: success might just go to the memory system and/or some other way to reward the system and encourage future results and behavior that follow the same process/recipe for success. But failures present more of a learning opportunity: proposed changes to identity files, system prompts, workflows, skills, tools, or even nanobot/copilot itself."*

**Takeaway**:
- **Successes** → memory system. Record what worked. No identity file changes.
- **Failures** → propose changes to identity files, prompts, workflows, skills, tools, or code. All proposals require user approval.
- **Nothing auto-applies to identity files. Ever.**

---

## Q17: Failure Handling — Worker Hits an Unresolvable Error

**Question**: Failure case: the orchestrator is halfway through the RFP task, it's been running 2 hours, and it hits an error it can't resolve — say, a document it needs is password-protected. What happens?

| Option | Description |
|--------|-------------|
| Stop, message me immediately: '[Task #3] Blocked: cannot open doc.pdf — need password' | Fail fast, alert, wait for human |
| Try alternatives (skip that doc, use others), flag the gap in the final deliverable | Best-effort completion with noted limitations |
| Mark task as blocked, resume automatically when I provide the password | Pause-and-resume on specific blocker resolution |
| Ask me in real time before giving up: 'I can't open doc.pdf. Want me to skip it or wait?' | Clarification request, then follow instructions |

**Answer**: *"I'm thinking something like 3 or 4, where the workers complete what they're currently working on/what they can, and then raise the issue or question to the orchestrator, which then pauses the task after all workers are done with their current assignments, and prompts the user with the question. The user responds to nanobot, and the orchestrator determines if the needs are met. If so, automatically proceed with a brief notification; if not, return with further questions."*

**Takeaway**: Graceful pause model:
1. Workers finish what they can
2. Escalate blocker to orchestrator
3. Orchestrator pauses after all workers complete current work
4. Orchestrator asks user through nanobot
5. User responds naturally
6. Orchestrator evaluates if answer resolves blocker
7. If yes → brief notification + auto-resume
8. If no → follow-up questions

---

## Q18: Crash Recovery

**Question**: The orchestrator is an ephemeral asyncio coroutine — it lives in memory. If nanobot crashes or restarts mid-task (say, a 6-hour coding task), what happens to the task?

| Option | Description |
|--------|-------------|
| Resume from the last completed checkpoint — re-hydrate from SQLite and re-spawn the orchestrator | Full persistence; crash-safe. More complex to implement. |
| Mark as interrupted, notify me, I decide whether to restart | Human decides; no automatic recovery |
| Restart from the beginning — idempotent steps make this safe | Simple; only works if steps are truly idempotent |
| I hadn't thought about this and it matters a lot | Need to design crash recovery explicitly |

**Answer**: *"This should already be accounted for — the crash is supposed to save the info up to where it last got. A restart should automatically restart the orchestrator, make it aware of the crash so it performs a brief health check and error analysis to see what CAUSED the crash and if it needs to adjust course or surface any findings (what if the task work was ITSELF the cause of the crash?) to nanobot, and then proceed automatically if the crash was NOT the task's fault, or halt if it was and raise the issue to the user. If the same task experiences a second crash, automatically halt regardless of the cause and notify the user."*

**Takeaway**: Sophisticated crash recovery:
1. State persisted to SQLite at every checkpoint
2. On restart: auto-spawn orchestrator from checkpoint
3. Orchestrator runs health check + **causal analysis** (was task the cause?)
4. If crash was external → auto-resume with brief notification
5. If crash was task-caused → halt + alert user with findings
6. **Second crash on same task → always halt regardless of cause**

---

## Q19: Cost Management

**Question**: Cost: the orchestrator uses a frontier model (Opus-class) for decomposition and re-planning. A complex 3-hour RFP task could make dozens of planning calls. Do you have a cost budget for tasks, or is 'get the work done' the priority?

| Option | Description |
|--------|-------------|
| No budget — use the best model for the job, report cost after | Quality-first; see costs in the dream cycle report |
| Soft budget — warn me if a task is trending expensive, let me decide | Visibility + control without hard limits |
| Hard budget per task — I set a ceiling when I assign it | Cost-controlled autonomy; fails gracefully if over budget |
| Route orchestrator to Sonnet, not Opus — good enough for planning | Save Opus for workers that need it; orchestrator on Sonnet |

**Answer**: *"Here's how it works: I set the orchestrator model ahead of time. Upon spooling up, it should estimate a price for the task based on the information it has available to it and its best guess for token count, and then update the internal task registry with that info. If it crosses a threshold (say, total $5), prompt the user with the estimate and ask for approval, along with any other questions it may have when it does its initial spin-up prep work."*

**Takeaway**: Front-loaded cost model:
1. User pre-selects orchestrator model
2. Orchestrator estimates total cost at spin-up
3. Updates task registry with estimate
4. If estimate > $5 threshold → prompt user for approval (bundled with planning questions)
5. No mid-task hard stop — approval is upfront

---

## Q20: Cancellation UX

**Question**: You text 'cancel task 3' mid-execution. The orchestrator has 2 workers running. What's the expected behavior in the next 30 seconds?

| Option | Description |
|--------|-------------|
| Immediate stop — workers killed, partial work discarded | Fast and clean. Anything done so far is lost. |
| Graceful stop — workers finish current step, then halt. Partial results saved. | Slightly slower but nothing is wasted. |
| Summary first — workers halt, orchestrator delivers what it completed before stopping | User gets value from work done before cancel |
| Confirm first — 'Cancel task 3? X steps complete, Y in progress. Confirm?' | No action until confirmed. Prevents accidental cancels. |

**Answer**: **Confirm first — 'Cancel task 3? X steps complete, Y in progress. Confirm?'**

**Takeaway**: Confirmation before cancellation. Show current progress so user can make an informed decision. No accidental kills.

---

## Q21: Biggest Risk

**Question**: What's the single biggest thing that could go wrong with V2.1 that would kill your confidence in the whole system?

| Option | Description |
|--------|-------------|
| Orchestrator runs for hours and produces garbage — the output is useless | Quality failure. System 'works' but can't actually do the work. |
| Orchestrator gets stuck in a loop and runs up a huge API bill silently | Cost runaway. No budget guardrail catches it. |
| A task that should be caught and questioned just executes and does something destructive | Safety failure. Shell access goes wrong, overwrites the wrong thing. |
| The task system is so fragile that crashes/bugs mean I can never trust a long task to complete | Reliability failure. Great when it works; unpredictably broken. |

**Answer**: *"I can't decide among those — they're all worst-case scenarios."*

**Takeaway**: All four failure modes are equally critical. The system must defend against all of them simultaneously: quality, cost, safety, and reliability. No single vector can be deprioritized.

---

## Summary of Key Divergences from Design Docs

| Area | Design Docs Say | User Actually Wants |
|------|----------------|---------------------|
| Proof-of-life task | VPS research comparison | Too trivial — real tasks produce deliverables |
| Task detection | Heuristics + LLM fallback | Pure LLM + confirmation + two-phase intake interview (nanobot gathers, then orchestrator can ask more before starting) |
| Plan approval | 30-day bootstrap, then auto | Always manual, no sunset. User removes guard rail explicitly. |
| Shell access | Included in worker tools | Excluded (security). Sandboxed workspace when added. |
| Parallelism | Parallel via asyncio.create_task() | Queue (sequential) for V2.1 |
| Crash recovery | Checkpoint resume | Causal analysis + second-crash auto-halt |
| Cost model | Track and report | Upfront estimate + $5 approval gate |
| Learning from success | Dream cycle updates identity files | Memory only. Identity files never touched without approval. |
| Concurrency UX | Not specified | Start verbose, configurable to silent via nanobot |
| Blocking timeout | Not specified | Indefinite — never auto-proceed on ambiguous decisions |

---

## Failure Mode Analysis & User Responses

Ten failure modes were identified and presented to the user. Their responses, plus Claude's proposals:

### FM1: Multi-phase intake too slow for simple tasks
**User**: Error on the side of caution early on. Self-learning system should identify over time what needs deep intake vs. what the orchestrator already has enough info for (via memory). Judgment calls that require memory + self-evolving system. *"See to it that the systems are/will be in place for this."*

### FM2: Indefinite blocking + queue = silent deadlock
**User**: Referenced that task parking already exists in the design docs (Decision #32 in Amendment #2). User can say "park task 1, do this instead." Parking saves full workflow state (same as crash recovery), terminates, next queued task starts. Resume later via `/resume <id>`.

**Doc review confirmed**: `parked` status exists in design. User prompt: "Task #3 is waiting for your feedback. Want me to auto-approve it and start your new task?" **Gap**: No orchestrator-initiated "I'm stuck, skip to next" — only user-initiated parking.

### FM3: LLM-only task detection has no escape hatch
**User**: Willing to live with the ambiguity. Models are strong enough. Self-learning helps over time. *"See to it that the systems are/will be in place for this."*

### FM4: Sandboxed shell ≠ safe shell
**Claude's proposal** (accepted):
1. **Directory jail**: Workers only read/write under `/workspace/tasks/<task_id>/`
2. **Network allowlist**: No localhost, internal IPs, or metadata endpoint access
3. **No process spawning**: Workers write files but can't execute them directly
4. **Resource limits**: Memory cap + CPU time limit per worker
5. **Secret isolation**: Worker env stripped of secrets; orchestrator injects only what's needed, logged in audit trail
- Start with directory jail + secret isolation (cheap, high impact). Add rest as shell matures in V2.2.

### FM5: Cost estimate will be wrong
**User**: Should be able to learn from actual costs after the fact via memory system and self-learning for better future estimates.

**Claude's proposal** (accepted): For early period, don't estimate — use a **running cost meter with checkpoint**. Track actual spend as it goes. When cumulative cost crosses $5, pause and ask: "This task has cost $X so far with Y steps remaining. Continue?" Sidesteps the estimation problem. Self-learning improves upfront estimates over time; running meter is always the safety net.

### FM6: Causal crash analysis is unreliable
**User**: Simplified to: automatically attempt one restart after a crash. Count crashes per task (counter resets on pause/complete/cancel). If one crash already occurred, do not reattempt — just notify. Let nanobot diagnose the issue with the user.

### FM7: "Workers finish current step" assumes steps are finite
**User**: Add a timeout. Reasonable default. Also: user can "force close" a task. First cancel request = graceful (confirmation + workers finish). Second cancel request = hard stop.

**Claude's proposal**: 5-minute timeout on graceful finish phase. After that, workers are killed.

### FM8: Natural language feedback routing is ambiguous
**User**: Feedback only ever applies to the currently executing task. Queued tasks can only be spoken about to nanobot ("for that next task B, make sure we XYZ"). Nanobot notes it and passes to orchestrator WHEN APPROPRIATE (not while task A's orchestrator is running). LLM should be salient enough to notice ambiguity and clarify. *"Unfortunately, such are natural language limitations!"*

### FM9: Learning asymmetry (failures > successes) creates negativity bias
**Claude's proposal** (accepted): Give successes structured capture too:
- On task completion, orchestrator writes a **retrospective** with "what worked" (workflow pattern, model choices, tools used, iteration count) and "what didn't" (re-plans, user corrections, wasted steps).
- Dream cycle synthesizes retrospectives into **playbooks** — reusable workflow templates stored in memory. ("Last time you built a landing page: Tailwind + Vercel, 3 iterations, user liked dark theme.")
- Playbooks queried during workflow design. Successes build the system's *repertoire* (known-good approaches). Failures propose changes to the system itself. Different mechanisms, both valuable.

**Doc review confirmed**: Retrospective already exists in design (4 structured questions). But no "playbook" extraction from successes — that's new.

### FM10: No definition of "done"
**User**: User must approve. Not complete until they do. No timeout for auto-approval — only for pausing and re-adding to queue. Uncompleted/unapproved tasks stay "incomplete" even if not active.

**Doc review confirmed**: Cross-model review (score >= 4) before delivery + user approval already in design (Decision #33). Iteration loop terminates only on explicit user approval.

---

## Web Research: Lessons from Similar Projects

Research across Devin AI, AutoGPT/BabyAGI, CrewAI, multi-agent failure studies (Galileo AI), LangGraph production deployments, and WhatsApp LLM bot architectures yielded these actionable findings:

### Already in our design (validated):
- **SQLite checkpointing** for crash recovery (LangGraph pattern — we use SQLite+WAL, same concept)
- **DAG-based workflow with programmatic execution** (CrewAI lesson: LLM reasons about *what*, code handles *when*)
- **Human-in-the-loop feedback cycles** (Devin lesson: autonomy without oversight = liability)
- **Tool whitelisting per worker** (security incidents: Google Antigravity deleted a user's Drive, Replit agent deleted a production DB)
- **Cost tracking per node** (AutoGPT wallet drain)
- **Dream cycle learning from outcomes** (MIT study: 95% of GenAI pilots fail because they don't learn)

### NOT in our design — should add:

| Finding | Source | Mitigation |
|---------|--------|------------|
| **Blocker detection with early bailout** | Devin spent days on impossible tasks | Track step-level retry count + elapsed time. Hard ceiling. Orchestrator soul file: "If you've tried 3 approaches and none worked, STOP and ask the user." |
| **Task feasibility check** | Devin attempted things that were structurally impossible | First-class workflow step: orchestrator assesses feasibility before decomposing. Surface uncertainty early. |
| **Webhook deduplication** | WhatsApp retries until 200 response | Store message IDs, reject duplicates. Prevents duplicate task creation. |
| **Prompt caching** | Up to 90% savings on repeated prefixes | Set `cache_control` breakpoints on soul file / policy / capabilities docs. Every orchestrator call uses these. |
| **Context windowing per orchestrator call** | Multi-agent failures: LLMs forget decisions mid-execution | Re-inject original task + current DAG state at each decision point. Don't rely on LLM remembering step 1 at step 15. |
| **Schema-validated worker outputs** | 41-87% failure rates in multi-agent systems | Every worker→orchestrator handoff uses schema-validated JSON. Parse failure → retry with correction prompt. |
| **Progress heartbeats to WhatsApp** | Async UX trust | For tasks > 30 seconds, send acknowledgment. Update at each DAG node completion. |
| **Idempotent worker operations** | LangGraph production pattern | If a worker writes a file or calls an API, wrap so re-execution doesn't duplicate. Use idempotency keys. |
| **Start narrow, expand gradually** | MIT: 95% pilot failure rate | Pick 3-5 task types, nail those, then expand. Don't launch with "do anything." |

### Key statistics from the research:
- **Devin AI**: 15% success rate across 20 tasks (Answer.AI, Jan 2025)
- **Multi-agent systems**: 41-87% failure rate across 1,642 traces (Galileo AI, Mar 2025)
- **GenAI pilots**: 95% fail to deliver ROI (MIT, 2025)
- **Prompt caching**: Up to 90% cost savings on cached tokens
- **Hybrid model routing**: 40-60% fewer API calls
- **Only 11% of organizations** have agentic AI in production (Deloitte, 2025)

---

## Design Amendments from Research & Follow-up Discussion (2026-02-18, later in session)

### Amendment A: Capability Profiles Replace Flat Sandbox (FM4 revision)

Directory jail alone doesn't cover internet-dependent tasks, AWS deployments, or browser-based form-fills. The security model becomes **capability profiles per task type**, assigned by the orchestrator when designing the workflow.

| Task Type | Internet | Filesystem | AWS | Shell | Browser | Security Model |
|-----------|----------|-----------|-----|-------|---------|---------------|
| Research | Allowlisted domains + web search tools | Read-only outside task dir, write inside | None | None | None | Tool whitelist only |
| Code/Repo | GitHub API only | Task workspace + git | None | Sandboxed to workspace | None | Directory jail + git-only network |
| AWS Deploy | AWS APIs only | Task workspace | Scoped IAM role per task | AWS CLI only | None | Temp IAM credentials, least-privilege |
| Web Form-Fill | Target site only | Task workspace for screenshots/logs | None | None | Playwright sandbox | Fresh browser profile per task, no user sessions |
| Content/Writing | Web search for research | Task workspace | None | None | None | Tool whitelist only |

**Key design decisions:**
- Orchestrator decides capability profile when designing workflow DAG. Each node tagged with a profile.
- Worker spawner enforces the profile — extends existing `tools_whitelist` to `capability_profile` (tools + network + filesystem + credentials).
- AWS: Orchestrator creates scoped IAM session with only needed permissions. Never exposes root credentials.
- Browser: Playwright runs in isolated context. Fresh profile per task. Credentials injected per-service by orchestrator.
- This is an LLM-first decision: the orchestrator's soul file guides which profile to assign. Code enforces the boundary.

### Amendment B: Self-Learning Cost Measurement Framework (FM5 revision)

The running cost meter handles the safety net. But the self-learning system needs to know what to measure and what targets to hit.

**Metrics stored per task in SQLite:**
- `estimated_cost_usd` vs `actual_cost_usd` — estimation accuracy
- `estimated_steps` vs `actual_steps` — decomposition accuracy
- `cost_per_step_type` — research step cost vs code step vs AWS step etc.
- `model_cost_efficiency` — same step type done by different models, quality-adjusted
- `iteration_count` — user feedback rounds before approval
- `time_to_first_draft` / `time_to_approval` — wall-clock efficiency
- `user_satisfaction` — implicit (iteration count, approval speed) + explicit (future: rating)

**Targets (seeded initially, refined by data):**
- Cost estimation accuracy: within 30% of actual → improve to 15%
- Steps estimated vs actual: within 1 → improve to exact
- Average iterations to approval: track trend, aim to decrease
- Cost per task type: baseline from first 10 tasks per type, then optimize

**Structured cost_analysis block per task completion:**
```json
{
  "estimated_cost": 2.50,
  "actual_cost": 4.80,
  "estimation_error_pct": 92,
  "cost_by_step_type": {"research": 1.20, "writing": 2.40, "review": 1.20},
  "model_usage": {"opus": 3.10, "sonnet": 1.70},
  "iterations": 2,
  "task_type": "rfp_document"
}
```

**Dream cycle integration:** Job 11 reads cost_analysis blocks from completed tasks. Observes patterns: "RFP tasks consistently cost 2x estimate. Writing steps are the expensive part." Proposes observation: "Increase default cost estimate for document-heavy tasks by 80%." User approves → future estimates improve.

**Estimation prompt context:** After sufficient data, orchestrator's estimation prompt includes: "Based on 12 previous RFP tasks, average cost was $4.20 with 3.2 iterations. This task appears similar in scope."

### Amendment C: Playbook System for Success Pattern Capture (FM9 resolution)

Successes need structured capture, not just narrative retrospectives. Playbooks are reusable workflow templates synthesized from successful task completions.

**Playbook schema (stored in SQLite `task_playbooks` table):**
```json
{
  "id": "playbook-landing-page-v2",
  "task_type": "landing_page",
  "created_from_tasks": ["task-001", "task-005", "task-009"],
  "last_updated": "2026-03-15",
  "workflow_template": {
    "nodes": [
      {"type": "research", "description": "Gather requirements + reference sites", "model_rec": "sonnet"},
      {"type": "code", "description": "Generate HTML/CSS/JS", "model_rec": "opus"},
      {"type": "review", "description": "Cross-model quality review", "model_rec": "sonnet"},
      {"type": "deploy", "description": "Deploy to target platform", "model_rec": "haiku"}
    ],
    "typical_iterations": 3,
    "avg_cost": 3.40,
    "avg_duration_hours": 2.5
  },
  "user_preferences": {
    "style": "dark theme preferred",
    "stack": "Tailwind + vanilla JS",
    "deployment": "Vercel"
  },
  "lessons": [
    "User rejected first drafts that used stock photos — always use placeholder illustrations instead",
    "Including mobile mockup in first draft reduces iteration count by 1"
  ],
  "success_rate": 0.85,
  "times_used": 7
}
```

**Lifecycle:**
1. First task of a type: no playbook exists. Orchestrator designs workflow from scratch.
2. Task completes successfully (user approves). Retrospective written.
3. Dream cycle extracts: workflow pattern, model choices, user preferences, iteration count.
4. After 2-3 successful tasks of similar type: dream cycle proposes a playbook as an observation. User approves.
5. Future tasks: orchestrator queries playbooks by task type. If match found, uses it as starting template (can still customize).
6. Each successful completion refines the playbook (updated avg cost, new lessons, adjusted model recommendations).

**Orchestrator integration:** During workflow design, the orchestrator's prompt includes: "Check for relevant playbooks before designing a new workflow. If one exists, use it as your starting point and explain any deviations."

**Playbooks live in the memory system (not identity files).** They're queryable by task type via semantic search (Qdrant) or exact match (SQLite). Dream cycle maintains them. User can view via `/playbooks` command and approve/reject/edit.

### Amendment D: Web Research Mitigations Integration

The following mitigations from the web research are incorporated into the design. Each is tagged with where it belongs.

**Already in design (validated by research):**
- SQLite checkpointing for crash recovery ✓
- DAG-based workflow with programmatic execution ✓
- Human-in-the-loop feedback cycles ✓
- Tool whitelisting per worker ✓
- Cost tracking per node ✓
- Dream cycle learning from outcomes ✓

**New additions:**

| # | Mitigation | Where It Goes | Implementation |
|---|-----------|---------------|----------------|
| 1 | Blocker detection with early bailout | `orchestrator_soul.md` + code (retry counter per node) | Track step-level retry count. Max 3 retries per node (already in design). Soul file: "If 3 approaches failed on the same step, STOP and ask the user. Never spiral." |
| 2 | Task feasibility check | `orchestrator.py` — first-class step before DAG design | Orchestrator assesses feasibility given available tools before decomposing. Surfaces uncertainty: "I can attempt X but I'm not confident about Y — should I proceed?" |
| 3 | WhatsApp webhook deduplication | `bridge/whatsapp/` — message processing layer | Store message IDs in SQLite. Reject duplicates. Prevents duplicate task creation from WhatsApp retries. |
| 4 | Prompt caching | `orchestrator.py` + provider config | Set `cache_control` breakpoints on soul/policy/capabilities prefixes. Static context cached across all orchestrator calls. |
| 5 | Context windowing per orchestrator call | `orchestrator.py` — context builder | Before each orchestrator LLM call, prune to: (a) original task, (b) current DAG state, (c) last 2-3 worker results. Don't send full execution history. |
| 6 | Schema-validated worker outputs | `orchestrator.py` — worker result handler | Every worker→orchestrator handoff uses schema-validated JSON. Parse failure → retry with correction prompt (max 2 retries). |
| 7 | Progress heartbeats to WhatsApp | `orchestrator.py` — node completion handler | For tasks > 30 seconds, send acknowledgment. Update at each DAG node completion. Uses existing `deliver_fn` pattern. |
| 8 | Idempotent worker operations | `worker_principles.md` + code (idempotency key system) | Workers use idempotency keys for external calls (API, file writes). Re-execution of a step doesn't duplicate side effects. |
| 9 | Start narrow, expand gradually | `orchestrator_soul.md` + V2.1 scope | V2.1 supports 3-5 task types only: research-heavy documents, code scaffolding, file-based deliverables. Expand in V2.2+. |
| 10 | Prompt injection defense | `orchestrator.py` — context injection | User input from WhatsApp isolated in clearly delimited blocks. Never concatenated into system prompt instructions. |

### Sources:
- [Thoughts On A Month With Devin — Answer.AI](https://www.answer.ai/posts/2025-01-08-devin.html)
- [Why Do Multi-Agent LLM Systems Fail? — Galileo AI](https://galileo.ai/blog/multi-agent-llm-systems-fail)
- [Why CrewAI's Manager-Worker Architecture Fails — TDS](https://towardsdatascience.com/why-crewais-manager-worker-architecture-fails-and-how-to-fix-it/)
- [Durable Execution — LangGraph Docs](https://docs.langchain.com/oss/python/langgraph/durable-execution)
- [AI Agents in Production 2025 — Cleanlab](https://cleanlab.ai/ai-agents-in-production-2025/)
- [Security for Production AI Agents 2026 — Iain Harper](https://iain.so/security-for-production-ai-agents-in-2026)
- [The Agentic Reality Check — Deloitte](https://www.deloitte.com/us/en/insights/topics/technology-management/tech-trends/2026/agentic-ai-strategy.html)
- [Building an LLM Chat & Task Bot with Durable Execution — Restate](https://www.restate.dev/blog/building-an-llm-chat-task-bot-with-restate)
- [Token-Budget-Aware LLM Reasoning — ACL](https://aclanthology.org/2025.findings-acl.1274/)
- [Human-in-the-Loop for AI Agents — Permit.io](https://www.permit.io/blog/human-in-the-loop-for-ai-agents-best-practices-frameworks-use-cases-and-demo)

---

## Open Technical Question

**How do the Interface Agent and Orchestrator communicate at the code level?** User deferred this to engineering. Needs a concrete proposal covering:
- Task creation handoff
- Orchestrator → user question routing (through nanobot)
- User response → orchestrator routing
- Status injection into nanobot conversation
- Cancellation signal propagation
