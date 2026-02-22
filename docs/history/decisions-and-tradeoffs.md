# Architectural Decisions & Tradeoffs

> Every design choice has a cost. This document records what we chose, what we gave up, and why.

---

## Decision 1: Integrate vs. Proxy

| | Proxy (original plan) | Integration (what we built) |
|---|---|---|
| **Architecture** | FastAPI at :5001, nanobot stock | Copilot modules inside nanobot package |
| **Latency** | +50-100ms per request (extra hop) | Zero added latency |
| **Deployment** | 2 services (nanobot + proxy) | 1 service |
| **Upgradability** | Can upgrade nanobot independently | Must merge upstream changes carefully |
| **Coupling** | Loose (OpenAI-compatible API boundary) | Tight (Python imports, shared types) |

**Chose**: Integration. The latency and operational simplicity won. The tradeoff — harder upstream merges — is acceptable because nanobot's core is small (~3.6K lines) and we only touch ~200 lines of it.

---

## Decision 2: Heuristic Routing vs. LLM Classification — [IMPLEMENTED → SUPERSEDED]

| | Heuristic | LLM Classification |
|---|---|---|
| **Latency** | <1ms | 200-2000ms |
| **Cost** | Free | $0.001-0.01 per classification |
| **Accuracy** | ~90% (compensated by self-escalation) | ~95% |
| **Complexity** | 50 lines of if/else | Prompt engineering, output parsing |

**Chose**: Heuristic + self-escalation. The 5% accuracy gap is covered by letting the local model escalate itself. Net result: same quality, zero cost, zero latency.

**V2 update**: Heuristic routing is superseded by Decision #30 (V2.1 Architecture Amendment #2) — default model + self-escalation, no heuristic classifier. The heuristic approach caused bugs (wrong compaction window, silent cost drift, dead classification rules).

**V2 final**: Fully replaced by Decision #31 (Router V2 plan-based routing). The `classify()` function has been deleted from the codebase.

---

## Decision 3: Multi-Provider vs. Single Provider

| | Single (OpenRouter) | Multi-provider |
|---|---|---|
| **Reliability** | One provider's uptime | Union of all providers' uptime |
| **Cost** | OpenRouter markup on all calls | Direct API pricing when possible |
| **Complexity** | Simple config | ProviderRegistry (400 lines), FailoverChain |
| **Key management** | 1 API key | 5-10 API keys |

**Chose**: Multi-provider. A personal assistant that's offline when OpenRouter is down isn't acceptable. The complexity cost is contained in two modules (registry + failover) and never leaks into the rest of the system.

---

## Decision 4: Session Storage — JSONL vs. Redis vs. SQLite

| | JSONL (current) | Redis | SQLite |
|---|---|---|---|
| **Setup** | Zero (file-based) | Requires Redis server | Already available |
| **Performance** | File I/O per read/write | In-memory, sub-ms | Disk I/O, but cached |
| **Crash recovery** | Full history on disk | AOF persistence (configurable) | ACID transactions |
| **Scalability** | Single user = fine | Overkill for single user | Single user = fine |

**Chose**: JSONL for now. Single-user system, file-based is simplest. Redis module is scaffolded for when/if we need sub-millisecond session lookups (unlikely for WhatsApp-speed interactions). This is the easiest decision to revisit.

---

## Decision 5: Onboarding — State Machine vs. Prompt Injection

| | State Machine | Prompt Injection |
|---|---|---|
| **Control** | Exact question ordering, validation, branching | LLM decides flow |
| **Naturalness** | Robotic unless heavily engineered | Conversational by default |
| **Code** | ~300 lines of flow logic | ~30 lines (flag + prompt) |
| **Flexibility** | Rigid, every change = code change | LLM adapts naturally |

**Chose**: Prompt injection. The LLM is better at conducting conversations than any state machine we'd write. The tradeoff is less control — we can't guarantee exact question ordering — but the result is a more natural interview that the user actually enjoys completing.

---

## Decision 6: Token Budget Strategy

| | Load everything | Tiered + budget |
|---|---|---|
| **Context quality** | Maximum information | Surgical, relevant only |
| **Token cost** | ~3000-5000 tokens/call in system prompt | ~500-1500 tokens/call |
| **Model compatibility** | Exceeds local model limits | Fits all models |

**Chose**: Tiered + budget. At scale (50+ messages/day, mix of local and cloud), the token savings are substantial. The tradeoff is that sometimes relevant context gets excluded — mitigated by the background extraction system preserving the most important facts.

---

## Decision 7: Approval Scope — Conservative vs. Permissive → REMOVED

~~**Original decision**: Permissive approval — only `exec` and `message` require approval. Lesson system learns from denials.~~

**Status**: The approval system was removed entirely (see Lessons Learned). It created a second decision-maker that overrode the LLM's judgment, added latency, and confused users with redundant confirmation prompts. Safety is now handled through:
- `ExecTool` deny patterns (destructive commands, sensitive files)
- `POLICY.md` guardrails (LLM-level judgment, not programmatic gates)
- Workspace restriction for file operations
- The principle: LLM is the pilot, code handles structural safety (timeouts, deny patterns), not decision-making.

---

## Decision 8: Scaffolding Everything vs. Building Incrementally

| | Build on demand | Scaffold all phases |
|---|---|---|
| **Immediate value** | Only working code in repo | Dead code exists |
| **Future velocity** | Must architect when needed | Wire-and-go |
| **Code clarity** | Clean — only what works | Some modules exist but don't run |

**Chose**: Scaffold everything. For a personal project with a clear roadmap, having the structure ready means we can wire features in hours instead of days. V1 completion proved this: ~2000 lines of memory and dream cycle code were production-ready, and wiring them required only ~50 lines of changes (dependency declarations, a supervisor bug fix, and a cron scheduler). The remaining scaffolded modules (domain tools: git, browser, AWS, n8n, documents) are deferred to V2.

---

## Decision 9: WhatsApp Bridge — Baileys vs. Business API

| | Baileys (personal) | Business API |
|---|---|---|
| **Cost** | Free | $0.005-0.08 per message |
| **Setup** | QR scan, Node.js bridge | Meta developer account, webhook server |
| **Reliability** | Can break with WhatsApp updates | Officially supported |
| **Features** | Full access (groups, media, reactions) | Limited to templates + sessions |
| **Risk** | Account ban possible | No ban risk |

**Chose**: Baileys. Free, full-featured, and the ban risk is low for personal use (one account, one user, no spam). The tradeoff is fragility — Baileys breaks when WhatsApp updates their protocol — mitigated by auto-start, reconnection handling, and the jidDecode polyfill.

---

## Decision 10: Privacy Mode Implementation

| | Separate local-only mode | Route flag on existing router |
|---|---|---|
| **Isolation** | Complete (different code path) | Logical (same code, different routing) |
| **Complexity** | Duplicate logic | Single flag check |
| **Guarantees** | Strongest | Depends on router honoring flag |

**Chose**: Route flag. `session_metadata["private_mode"] = True` → router always picks local. Self-escalation disabled. Same code path, one branch point. The tradeoff is that a bug in the router could leak to cloud — mitigated by logging every routing decision to SQLite (auditable).

---

## Decision 11: Lesson Confidence Decay

**Problem**: Lessons that were once useful can become stale or wrong.

**Approach**: Confidence starts at 0.5. Reinforced (+0.05) when helpful. Penalized (-0.10) when unhelpful. Deactivated when confidence < 0.30 AND applied >= 5 times.

**Asymmetry is intentional**: Penalization is 2x reinforcement. A lesson that's wrong should die faster than a lesson that's right should grow. The tradeoff is that genuinely useful but occasionally wrong lessons might get deactivated — but they can be recreated if the pattern recurs.

---

## Decision 12: Background Extraction — Always-On vs. On-Demand

| | Always-on (after every exchange) | On-demand (when context is full) |
|---|---|---|
| **Freshness** | Extractions always current | Stale until needed |
| **Cost** | ~$0.001 per exchange (Haiku fallback) | Zero until triggered |
| **Continuation quality** | Seamless (extractions ready) | Jarring (must extract on the fly) |

**Chose**: Always-on. The cost is negligible ($0.001 × 50 messages/day = $0.05/day). The benefit is that when a model switch or context continuation happens, the extractions are already there — no delay, no quality loss. The tradeoff is wasted extraction on short conversations that never need continuation.

---

### Decision #31: Plan-based routing replaces heuristic classification

**Date:** 2026-02-20
**Status:** IMPLEMENTED

**Context:** 11-rule heuristic classifier caused 20+ incidents — silent model switches, cascading failures, wrong context windows, memory pollution. Config default phi-4-mini-reasoning caused 27-provider cascade on every message.

**Decision:** Replace with LLM-generated routing plans. The LLM reads router.md (provider health, costs, constraints), proposes a plan, validates via API probes, user approves. Mandatory safety net always appended by code.

**Tradeoffs:**
- (+) Routing is now transparent and user-controllable
- (+) LLM has full context (costs, health, constraints) for routing decisions
- (+) No more silent model switches mid-conversation
- (-) Requires initial plan setup (but defaults work without one)
- (-) Recovery probing adds background task (but stops when recovered)

---

### Decision #33: CopilotHeartbeatService — subclass, not fork

**Date:** 2026-02-20
**Status:** IMPLEMENTED (Sentience Plan)

**Context:** Sentience Plan needed to add cognitive context (dream observations, pending tasks, autonomy permissions) to the heartbeat LLM prompt, but `HeartbeatService` is upstream nanobot code.

**Decision:** Create `CopilotHeartbeatService` as a subclass of `HeartbeatService`, override `_tick()` there. The upstream file stays untouched. `commands.py` instantiates `CopilotHeartbeatService` when copilot mode is enabled, `HeartbeatService` otherwise.

**Tradeoffs:**
- (+) Upstream merges don't overwrite our changes
- (+) Matches existing patterns (RouterProvider wraps LiteLLMProvider, ExtendedContextBuilder wraps ContextBuilder)
- (-) Slight coupling to `_tick()` signature — if upstream renames it, subclass breaks
- (-) Two heartbeat classes to understand (mitigated by clear naming)

---

### Decision #34: JSON observations over tool-based writing

**Date:** 2026-02-20
**Status:** IMPLEMENTED (Sentience Plan)

**Context:** Dream cycle, cognitive heartbeat, weekly review, and task retrospectives all need to write structured data to `dream_observations`. Options were: (a) LLM calls observation-write tool inline, (b) LLM outputs JSON at end of response which code parses and writes.

**Decision:** JSON at end of response, parsed by `_parse_llm_json()` with 4-level fallback. Code writes to DB. LLM doesn't need a special tool.

**Tradeoffs:**
- (+) Simpler — no tool registration, no mid-response DB write
- (+) Works in fire-and-forget contexts (dream cycle, heartbeat) where tool calls are one-way
- (+) Fallback chain (direct parse → fence extract → regex → trailing comma fix) handles Gemini's quirks
- (-) JSON parsing is fragile — mitigated by the fallback chain storing parse failures as `observation_type='parse_failure'`

---

### Decision #35: Autonomy permissions are per-category, not global

**Date:** 2026-02-20
**Status:** IMPLEMENTED (Sentience Plan)

**Context:** System needs a way to grant autonomy for specific action types (task management, identity evolution, memory management, etc.) without unlocking everything at once.

**Decision:** `autonomy_permissions` table with one row per category, modes `notify/autonomous/disabled`. User grants via `set_preference(key="autonomy:category", value="autonomous")`. All start as `notify`.

**Categories:** `task_management`, `identity_evolution`, `config_changes`, `proactive_notifications`, `memory_management`, `scheduling`

**Tradeoffs:**
- (+) Granular — user can trust identity evolution but not config changes, etc.
- (+) Persisted in SQLite — survives restarts, visible in heartbeat context
- (+) No 30-day shadow period — user grants when they decide, not on a timer
- (-) More categories to understand; mitigated by defaulting all to `notify` (safe)

---

### Decision #36: Velocity limits on system suggestions only

**Date:** 2026-02-20
**Status:** IMPLEMENTED (Sentience Plan)

**Context:** Identity evolution (Job 11) could theoretically rewrite identity files every dream cycle. Need a governor.

**Decision:** Max 1 file change per dream cycle for system-initiated evolution. User-directed changes (explicit request to the LLM) bypass this limit entirely. Also: safety check verifies no user activity in last 30 minutes before applying autonomous identity changes (dream cycle runs at 7 AM when user is unlikely active).

**Tradeoffs:**
- (+) Prevents runaway identity drift from daily automated modifications
- (+) User retains full control — their requests always honored immediately
- (-) Could slow convergence on needed identity updates; weekly review compensates by surfacing accumulated proposals

---

### Decision #32: Memory system — degradation, dedup, and protection tiers

**Date:** 2026-02-20
**Status:** TABLED — design as a coherent project, not piecemeal fixes

**Context:** Multiple memory subsystem gaps identified during workflow review. Each is individually fixable but they interact — solving them independently risks inconsistency. This decision captures all tabled concerns so they're designed together.

**Open issues:**

1. **Memory degradation/pruning** — Not implemented. Episodic memories (Qdrant + FTS5) accumulate indefinitely. The only decay mechanism is lesson confidence decay (Decision #11: start 0.5, reinforce +0.05, penalize -0.10, deactivate <0.30). No general pruning exists for conversation exchanges or transient context.

2. **Protection tiers** — Any future degradation system MUST protect: lessons, core facts, user preferences, self-reflection outputs. Only transient context (conversation exchanges, temporary notes, low-importance observations) should be candidates for pruning. This is a hard constraint, not a tuning knob.

3. **FTS5 deduplication** — `fulltext.py` `store()` is a plain INSERT with zero write-time dedup. Same text stored N times = N rows. Qdrant has session-scoped dedup via `uuid5(session_key:role:text[:500])` but identical facts across sessions produce separate vectors. Both need fixing.

4. **Lessons table utilization** — Full infrastructure exists (`LessonManager` with create/reinforce/penalize/decay/inject) but is nearly empty. Dream cycle only decays existing lessons, never creates new ones from self-reflection. Weekly/monthly reviews should populate lessons from what the system actually learned — not just satisfaction detection.

**Design constraint:** These four items must be designed together. Memory degradation without protection tiers is dangerous. Dedup without understanding what "same memory" means across sessions is fragile. Lessons without degradation-immunity guarantees will lose hard-won knowledge.
