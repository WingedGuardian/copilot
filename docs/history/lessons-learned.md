# Lessons Learned

> Hard-won insights from building the Executive Co-Pilot on top of nanobot.

---

## 1. Don't Build a Separate Proxy — Integrate

**Original plan**: FastAPI proxy at `localhost:5001` sitting between nanobot and all LLMs. Nanobot stays "stock, unmodified."

**What happened**: We built the proxy. Then realized it meant maintaining a separate service, handling its own lifecycle, duplicating error handling, and adding latency to every request. The "clean separation" created more problems than it solved.

**What we did instead**: Integrated copilot modules directly into the nanobot package. Thin hooks in 5 existing files (~200 lines total), fat modules in `nanobot/copilot/`. RouterProvider drops in as a replacement for LiteLLMProvider — the agent loop never knows the difference.

**Lesson**: "Keep it stock" sounds good in theory, but when you're extending something, integration beats interposition. A drop-in replacement is cleaner than a man-in-the-middle.

---

## 2. Heuristic Routing Beats LLM Classification

**[SUPERSEDED by Decision #30]** — The heuristic approach was too rigid (11 rules, silent model switches, cascading failures). Router V2 replaces it with LLM-generated routing plans validated via API probes. The LLM IS the best routing heuristic when given proper context (router.md with provider health, costs, constraints).

**Original plan**: Considered using an LLM call to classify each message and decide routing.

**What we built**: Pure heuristic classification — keyword detection, message length, image presence, token count. First match wins. Zero latency added.

**Why it works**: 90%+ of routing decisions are obvious. "hello" → local. Image attached → vision model. Code block → big model. The edge cases where heuristics get it wrong are handled by self-escalation (the local model can say "I can't handle this" and the system retries with a bigger model).

**Lesson**: Don't use an LLM to decide which LLM to use. Heuristics + self-escalation covers everything without the cost or latency of a classification call.

---

## 3. Self-Escalation is the Safety Net That Makes Cheap Routing Safe

**The pattern**: When routing to the local model, inject an instruction: "If this is beyond your capabilities, start your response with `[ESCALATE]`." If the local model does this, the router automatically retries with the big model.

**Why it matters**: This is what makes aggressive local-first routing safe. You can route 80% of traffic to the free local model knowing that the 20% it can't handle will automatically escalate. The user never sees a bad response — they just see a slightly slower one when escalation happens.

**Lesson**: Build escape hatches, not perfect classifiers.

---

## 4. Token-Conscious Storage is Non-Negotiable

**The problem**: Everything in USER.md and MEMORY.md gets loaded into every single LLM call. If you dump a 2000-token user profile into the system prompt, you're burning 2000 tokens on every message — at cloud prices, that adds up fast.

**The solution**:
- USER.md: ~10 lines max (name, timezone, style, autonomy rules)
- MEMORY.md: ~400 token hard budget, behavioral core only (autonomy rules, communication style, prime directive). Goals, action plan, and life context moved to Qdrant episodic memory — retrieved on-demand via `recall_messages`. Dream cycle enforces the budget nightly.
- Extractions: stored in session metadata, formatted on demand within budget
- Identity docs: cached 60s to avoid re-reading

**Lesson**: Every token in the system prompt is a recurring cost. Be surgical about what gets injected. If it doesn't change the LLM's behavior for *this specific message*, it doesn't belong in the prompt.

---

## 5. Let the LLM Conduct the Interview

**First approach**: Build a structured state machine for onboarding — predefined questions, branching logic, validation.

**What the user said**: "It all goes through the system anyway. We really just need the questions and to inform nanobot in natural language of my answers, and it should make all the necessary changes on its own."

**What we built**: `/onboard` sets a flag in session metadata. When active, the system prompt gets an interview script injected (~500 tokens). Nanobot's own LLM conducts the interview naturally — asks follow-ups, decides what's important, uses its existing `write_file` tool to save the profile.

**Lesson**: If you have an LLM in the loop, let it do what LLMs are good at — conversation, judgment, synthesis. Don't build a state machine when a prompt injection does the job better.

---

## 6. Failover Chains Need Multiple Cloud Providers

**The problem**: OpenRouter goes down. Now what? Single-provider fallback means single point of failure.

**What we built**: FailoverChain with provider tiers. Each tier (local, fast, big) tries multiple cloud providers in sequence: OpenRouter → Venice → Nvidia NIM → Groq → Anthropic direct. If one is down, the next picks up seamlessly.

**The key insight**: Different providers have different failure modes. OpenRouter has rate limits. Venice has model availability issues. Nvidia NIM has cold starts. Having 3-4 providers means at least one is always up.

**Lesson**: Multi-cloud isn't just for enterprises. For a personal assistant that you rely on, provider diversity is reliability.

---

## 7. Natural Language Approvals > Structured Formats

**Original plan**: Y/N approval buttons or forced format responses.

**What we built**: Natural language parsing. "yeah go for it" → approve. "no too risky" → deny. "change the subject line" → modify. Quick cancel: "skip", "nevermind" → immediate abort.

**Why**: When approvals come via WhatsApp (often on a phone, sometimes via voice), forcing structured responses creates friction. The whole point of the system is reducing friction.

**Lesson**: Match your interaction model to your interface. WhatsApp is a conversation — let approvals be conversational.

---

## 8. Background Extraction is the Key to Model Switching

**The insight**: When you switch from a local model to a cloud model mid-conversation, the cloud model has no context. Passing the full conversation history is expensive and often exceeds the local model's context window anyway.

**The solution**: Background SLM runs after every exchange, extracting facts, decisions, constraints, and entities as structured JSON. When the context needs to be rebuilt (model switch, continuation trigger), these extractions serve as a compressed briefing. The new model gets the essential context in ~200 tokens instead of needing the full 5000-token conversation.

**Lesson**: Extraction is compression. Structured extraction is the bridge that makes multi-model conversations seamless.

---

## 9. The WhatsApp Bridge is Fragile — Invest in Resilience

**Issues encountered**:
- `jidDecode` function missing in newer Baileys versions → messages failed silently
- Bridge process crashes and doesn't restart → user thinks system is down
- QR code scanning flow breaks if bridge restarts during auth

**What we did**: Auto-start bridge from gateway, jidDecode polyfill, connection state logging, graceful reconnection handling.

**Lesson**: The channel layer is your user-facing surface. It can be the simplest code in the stack, but it needs the most resilience. A brilliant routing system means nothing if WhatsApp messages don't arrive.

---

## 10. Scaffold Everything, Wire Later — and Then Actually Wire It

**What we did**: Built code for all 8 phases — memory, tasks, tools, dream cycle, monitoring, status — while focusing the hot path on core features (routing, context, extraction, approval, metacognition).

**Why it worked**: When V1 completion time came, the memory system (~660 lines), dream cycle (359 lines), supervisor (128 lines), and monitor (138 lines) were all production-ready code. The "wiring" to make them run required ~50 lines of changes across 3 files: declaring missing pip dependencies, fixing a supervisor bug, and adding a cron scheduler.

**The trap we fell into**: The scaffolded modules silently degraded to no-ops because `qdrant-client` and `redis` weren't declared in `pyproject.toml`. ImportError was caught, logged once, and the system continued without memory. This looked like "it works" when it was actually "it's gracefully doing nothing." The ProcessSupervisor had a similar issue — fire-and-forget services returned immediately from `start()`, the supervisor interpreted this as a crash, and gave up after 5 restarts.

**Lesson**: Scaffolding is an investment — but graceful degradation can mask the fact that your investment isn't paying off. If a module can silently become a no-op, add a health check that tells you it's actually working.

---

## 11. Private Mode is a Trust Feature

**The feature**: `/private` routes everything through the local model only. No cloud calls, no data leaving the machine. 30-minute auto-timeout as a safety net.

**Why it matters**: Not every conversation should go through cloud APIs. Sensitive topics, personal matters, financial details — the user needs to trust that they can have a private conversation. Without this feature, the user self-censors, and the system can't be truly helpful.

**Lesson**: Privacy isn't just compliance — it's a feature that changes how users interact with the system. Build it early.

---

## 12. Don't Over-Engineer the Config

**Original plan**: Separate `.env` file, environment variables, config.json, Pydantic schemas with validation.

**Reality**: `~/.nanobot/config.json` does everything. One file, JSON, easy to edit. Provider keys, channel settings, copilot toggles — all in one place. Pydantic validates on load.

**Lesson**: For a single-user system, simple config beats "proper" config. You're the only user. You don't need YAML templating or environment variable overrides. You need one file you can edit with a text editor.

---

## 13. Check for Existing Infrastructure Before Creating New

**The situation**: Gateway wouldn't stay up after a restart. SIGTERM killed it ~3 seconds after every startup. Extensive debugging — signal tracing, debug logging, asyncio task inspection — all pointed to an external SIGTERM source with no obvious sender.

**Root cause**: A `nanobot-gateway.service` systemd user service already existed. During troubleshooting, we created a second `nanobot.service` for the same process. Both were enabled, both started on boot, and each one's startup killed the other's process via `_kill_existing_gateway()`, creating an infinite restart loop.

**Lesson**: Before creating new process managers (systemd services, cron entries, supervisor configs), always check what already exists: `systemctl --user list-units --type=service --all | grep <name>`. The duplicate was invisible because `systemctl status nanobot` only showed our new service — the original had a different name.

---

## 14. Provider Ordering Matters in Failover Chains

**The problem**: `/status` showed `openai:` as the provider for all cloud tiers, but OpenRouter was the actual primary. Every request first tried OpenAI (which can't route Anthropic models), failed, then fell back to OpenRouter. Wasted latency on every single call.

**Root cause**: `cloud_providers` dict was built by iterating Pydantic model fields in declaration order. `openai` was declared before `openrouter` in `ProvidersConfig`, so it was first in the dict and first in the failover chain.

**Fix**: Sort cloud providers so gateways (OpenRouter, AiHubMix — can route any model) come before direct providers (OpenAI, Anthropic — only handle their own models).

**Lesson**: Dict iteration order is implicit API. When a dict's order determines priority (failover chains, middleware stacks), make the ordering explicit and intentional rather than relying on declaration order.

---

## 15. Three Periodic Services, Three Distinct Roles

**The confusion**: Multiple services with "heartbeat" in their history, with roles that were inverted in early docs.

**Current architecture (as of Sentience Plan)**:
- **CopilotHeartbeatService** (`cognitive_heartbeat.py`): LLM-powered cognitive awareness. Runs every **2h**. Subclasses upstream HeartbeatService. Injects dream observations, pending tasks, autonomy permissions, and morning brief. Skips when dream cycle is running (`DreamCycle.is_running` flag).
- **HealthCheckService** (`health_check.py`): Programmatic health monitoring — **NO LLM calls**. Runs every **30min**. Qdrant ping, changelog diff, alert resolution, stuck job detection.
- **HeartbeatService** (`nanobot/heartbeat/service.py`): Upstream base class only. CopilotHeartbeatService always replaces it when copilot is enabled. Never modify upstream.

**The naming chain**: Original `CopilotHeartbeatService` was programmatic → renamed `HealthMonitorService` (2026-02-19) → renamed `HealthCheckService` (Router V2, moved to `health_check.py`). A NEW `CopilotHeartbeatService` was then created for the LLM heartbeat (Sentience Plan). Early docs including this lesson had them inverted.

**Lesson**: Match timer frequency to cost. Health checks are cheap and time-sensitive → 30min. LLM cognitive calls are expensive and latency-tolerant → 2h. If HealthCheckService needs intelligence, escalate to the dream cycle — never add an LLM call to it.

---

## 16. Every Provider Needs Its Own Default Model

**Situation**: `/use minimax` sent `anthropic/claude-opus-4.6` to MiniMax's API. The router used its global `_big_model` for all providers, which is always an Anthropic model. Non-gateway providers can't serve models from other providers.

**Lesson**: Providers and models are not independent axes. When you switch providers, you must also switch models. Each provider config now has a `default_model` field (`~/.nanobot/config.json` → `providers.<name>.defaultModel`). Gateways (OpenRouter, AiHubMix) don't need this because they route any model.

---

## 17. Unknown Model Metadata Costs Real Money

**Situation**: MiniMax-M2.5 wasn't in the context window table. Default was 8K. Session hit 76% of 8K → router triggered overflow escalation → routed through opus at $0.32. User didn't request it, didn't know it happened, and got charged for it.

**Original mistake**: Default context window was 8,192 tokens — appropriate for old small models but dangerously low for modern models. Any unknown model would trigger false overflow escalation.

**Lesson**: Default to 128K for unknown models. False overflow escalation (unexpected $$$, wrong model, confused user) is far worse than slightly overestimating context. When adding a provider, always add: (1) `default_model` in config, (2) context window in `budget.py`, (3) pricing in `cost/logger.py`. All three are required — missing any one causes silent failures.

---

## 18. Verify Table Names Against Actual Schema

**Situation**: Status aggregator queried `route_log` table. Actual table name was `routing_log`. The query silently failed (caught exception), returning no data. The fallback logic then showed stale/wrong information.

**Lesson**: Always verify table names with `sqlite3 ... ".tables"` before writing queries. Silent exception handling around DB queries can mask schema mismatches for a long time.

---

## 19. Every Background Service Needs a Cloud Fallback

**Situation**: Extraction had no cloud fallback. When LM Studio went down, every extraction fell through to a regex heuristic that produced near-zero useful data. Structured memory items stayed at 0 permanently. Meanwhile, embeddings had a cloud fallback (Jina → OpenAI) and kept working fine.

**The tell**: SLM queue showed 15 pending + 5 completed — all embeddings, zero extractions. Extraction jobs were never even queued because the error happened before the queue code was reached.

**Lesson**: Any background service that depends on LM Studio MUST have a cloud fallback. The pattern: local (free) → cloud (cheap) → queue for deferred → heuristic. Both embeddings and extractions now follow this pattern with dedicated API keys in secrets.json (`cloudEmbeddingApiKey`, `cloudExtractionApiKey`). Extraction uses Haiku via OpenRouter (~$0.001/call).

---

## 20. Providers and Models Are Not Independent Axes

**Situation**: `/use minimax` sent `anthropic/claude-opus-4.6` to MiniMax's API. The router treated provider selection and model selection as separate concerns, always falling back to the global `_big_model`. Non-gateway providers can't serve other providers' models.

**The cascade**: Wrong context window (8K default for unknown MiniMax model) → false overflow detection at 76% → silent escalation to opus via openrouter ($0.32) → user confused about costs and which model they're actually talking to.

**Lesson**: When adding a non-gateway provider, you must configure THREE things or the provider is broken: (1) `defaultModel` in config, (2) context window in `budget.py`, (3) pricing in `cost/logger.py`. Missing any one causes cascading silent failures. The 128K default context window is a deliberate safety net — false overflow ($$$) is worse than slightly overestimating context.

---

## 21. Always Add Observability When Adding a Feature

**Situation**: After fixing extraction cloud fallback, there was no way to verify it was actually working from `/status`. The fix was invisible to the user — "structured items: 0" would remain until someone checked the logs.

**Lesson**: Every feature that runs in the background needs a line in `/status`. If you can't see it, you can't trust it. Added: extraction source (local/cloud/heuristic), extractions today count, embedding source, and SLM queue breakdown by work type.

---

## 22. Backfill Tools Pay for Themselves

**Situation**: Cloud extraction fallback was added, but 6+ exchanges of chat history had zero extractions. Those conversations contained critical identity/preference setup that the memory system would never learn from.

**Lesson**: When fixing a broken pipeline, always ask: "what about the data that was missed?" Build a backfill tool (`nanobot backfill-extractions`) so historical data isn't permanently lost. Session JSONL files are the source of truth for past exchanges.

---

## 23. Python `.format()` and JSON Templates Don't Mix

**Situation**: `_EXTRACTION_PROMPT` contained a JSON schema example with braces: `{"facts": [...]}`. Python's `.format()` treated `{"facts"` as a format variable, throwing `KeyError: '\n  "facts"'`. Extraction was broken from day one — the error happened before any LLM was ever called.

**The tell**: The error message `KeyError: '\n  "facts"'` looked like a JSON parsing error, which sent us looking at LLM responses. In reality, the `.format()` call at line 118 crashed before the LLM was even contacted.

**Lesson**: When a prompt template contains literal braces (JSON examples, code snippets), double them: `{` → `{{`, `}` → `}}`. Or use `string.Template` / f-strings with pre-built variables instead of `.format()`. Always test prompt templates in isolation before assuming the LLM is the problem.

---

## 24. LLMs Never Return Bare JSON — Parse Defensively

**Situation**: Cloud extraction via Haiku 4.5 returned JSON wrapped in preamble: "Here is the extraction:\n{...}". `_parse_json()` stripped markdown fences but assumed the remaining text was pure JSON. `json.loads()` failed on every cloud extraction — 5 items all stuck at "unparseable JSON."

**The cascade**: No completed extractions → no duplicate key matches in `memory_items` → no confidence boosts past 0.5 → display threshold (0.6) hid all 36 existing items → "Structured items: 0" looked like extraction was broken when it was actually a display + parsing issue.

**Lesson**: When parsing JSON from LLM output, always fall back to finding the first `{` to last `}`. LLMs almost never return bare JSON — they add "Sure!", "Here's the result:", or other wrapper text. The markdown fence strip is necessary but not sufficient.

---

## 25. Always Restart Nanobot Via systemd — Never Manual nohup

**Pattern**: When asked to restart nanobot, the instinct is `kill <pid> && nohup python -m nanobot gateway &`. This creates an orphan process outside systemd's control. Systemd's `Restart=always` then tries to start its own instance, which can't bind the port, crash-loops, and you end up debugging a "gateway won't start" problem that you caused.

**The vicious cycle**: Kill orphan → systemd restarts → new orphan conflicts → kill again → systemd restarts again. Each iteration looks like a new problem.

**The fix**: Always use `systemctl --user restart nanobot-gateway`. One command, no orphans, no conflicts. If systemd is crash-looping, check for orphan processes first (`ps aux | grep nanobot`), kill them, THEN restart via systemd.

**Lesson**: The gateway has a process manager (systemd). Use it. Never bypass it with manual process launches. This has bitten us at least twice (see GATEWAY-SYSTEMD-003, GATEWAY-DUPLICATE-002).

---

## 26. Display Thresholds Must Match Data Reality

**Situation**: 36 memory items existed at confidence 0.5 (the default). Display threshold was 0.6, which required items to appear twice with the same `category+key[:100]`. With varied extraction wording, no two items matched — all 36 were invisible.

**Lesson**: When adding a display threshold, check the actual data distribution. A threshold that filters out 100% of your data is worse than no threshold. Lowered from 0.6 to 0.4 — items now visible on first appearance, still filtered from random noise.

---

## 27. Error Responses Must Be Guarded From Memory Pipeline

**Situation**: When an LLM call failed (provider down, timeout, malformed response), the error message was passed through the normal extraction and memory pipeline. `schedule_extraction()` and `remember_exchange()` treated error strings as legitimate assistant responses, extracting "facts" like "connection refused" and "API returned 503" and storing them as user preferences or conversation context.

**The cascade**: Error messages polluted Qdrant episodic memory and SQLite structured items. Subsequent recall queries would surface error artifacts as relevant context, confusing future LLM calls and degrading response quality.

**Lesson**: Guard every memory pipeline entry point with `not is_error`. If the response is an error, it has no business entering the memory system. This is a structural concern (code guardrail), not a judgment call — errors are never valid memory content.

---

## 28. The LLM Is the Best Routing Heuristic When Given Proper Context

**Situation**: 11-rule heuristic classifier caused 20+ incidents — silent model switches, cascading failures, wrong context windows, memory pollution from error responses. The rules were brittle, opaque, and impossible to debug without reading source code.

**What replaced it**: Router V2 gives the LLM a ground-truth document (`router.md`) containing provider health, costs, free tier limits, context windows, and constraints. The LLM proposes a routing plan, validates it via API probes, and the user approves. Code only enforces a mandatory safety net (last-known-working + LM Studio + emergency fallback).

**Lesson**: The original Lesson #2 ("Don't use an LLM to decide which LLM to use") was wrong in the general case. It was right for per-message classification (too slow, too expensive). But for plan-level routing — deciding which providers/models to use for a session — the LLM with proper context (router.md) makes better decisions than any heuristic. The key insight: routing plans are infrequent, high-context decisions. Per-message classification is frequent and low-context. Use the right tool for each.

---

## 29. Silent Failures Are the Most Expensive Bugs

**Situation**: An audit of the codebase found 11 silent swallows across memory and routing — `try/except` blocks that caught exceptions and only logged them (or worse, bare `pass`), never surfacing the failure in `/status` or AlertBus. Extraction FTS writes had bare `pass` with no log at all. The SLM queue silently dropped items at capacity. MonitorService detected state transitions but bypassed AlertBus entirely. ProcessSupervisor's `get_status()` existed but was never called from `/status`.

**The cascade**: Memory extraction could fail at three layers (Qdrant, FTS5, SQLite structured items) — each with its own silent swallow. A user would see "Structured items: 0" and think extraction was broken, when in reality it was a display threshold + parsing + storage failure compound. The 34% fix-commit rate in the last 50 commits was largely driven by discovering these silent failures after deployment.

**What we did**: Added AlertBus calls to all 11 silent swallows. Wired ProcessSupervisor into `/status` (Services section). Added HealthCheckService `last_tick_at` to Last Operations. Added `total_dropped` counter to SLM queue stats. Wired MonitorService to AlertBus alongside its direct delivery. Added CLAUDE.md rules for loud-failure-by-default.

**Lesson**: `try/except → logger.warning` is a code smell in background services. If an exception is worth catching, it's worth either handling properly or alerting on. The cost of a false alert is one dismissed notification. The cost of a silent failure is hours of debugging the wrong thing. Default to loud.

---

## 31. Subclass Upstream Code — Don't Fork It

**Situation (Sentience Plan):** Needed to add cognitive context to the heartbeat LLM prompt. `HeartbeatService` is upstream code in `nanobot/heartbeat/service.py`. The instinct was to modify it directly.

**What could go wrong:** Future upstream merges overwrite the modifications. Changes get lost silently — nothing fails at startup, the cognitive context just disappears.

**What we did:** Created `CopilotHeartbeatService(HeartbeatService)` in `nanobot/copilot/dream/cognitive_heartbeat.py`. Override `_tick()` there. Upstream stays pristine. Pattern matches `RouterProvider` wrapping `LiteLLMProvider` and `ExtendedContextBuilder` wrapping `ContextBuilder`.

**Lesson:** When extending upstream code, subclass don't modify. The upstream file is a contract you don't own — treat it like a library import. Your changes belong in a derivative class in `nanobot/copilot/`, not in the original file.

---

## 32. LLMs Never Return Bare JSON — Build a Four-Level Fallback

**Situation (Sentience Plan):** Dream cycle, heartbeat, weekly review, and task retrospectives all request JSON output from LLMs (observations, diagnoses, roadmap proposals). Gemini Flash (the dream model) regularly wraps JSON in markdown fences, adds preamble text, and sometimes produces trailing commas.

**What could go wrong:** A single `json.loads()` call fails. The entire observation pipeline silently breaks — no observations written, no retrospectives stored, no evolution proposals. WhatsApp summary still works (fallback to raw text) but the feedback loops don't close.

**What we built:** `_parse_llm_json(text, fallback_type)` with 4 levels:
1. `json.loads(text)` direct
2. Extract from ` ```json ``` ` fence
3. Regex find outermost `{...}` or `[...]`
4. Strip trailing commas (Gemini quirk), retry

If all fail: store raw text as `observation_type='parse_failure'` and fire AlertBus. Never silently discard.

**Lesson:** Don't add JSON parsing without the fallback chain. One `json.loads()` in production LLM code is a latent bug. The fallback chain is a 30-line function that saves the entire observation pipeline.

---

## 33. Open Feedback Loops Produce Prose, Not Progress

**Situation (Sentience Plan):** Dream cycle had a `_self_reflect()` method that produced a free-form text summary. The summary was delivered to WhatsApp and stored in a text column, but nothing downstream consumed it. The LLM identified capability gaps and patterns every night — and then they evaporated.

**Root cause:** The loop was structurally open. Input (24h activity) → LLM reflection → text output → end. No structured output, no downstream consumer, no feedback mechanism.

**What we built:** Structured JSON output → `dream_observations` table → cognitive heartbeat queries unacted observations → weekly review synthesizes patterns → evolution proposals → identity evolution → `evolution_log`. Each step has a consumer. The loop closes.

**Lesson:** If you build a system that generates insights but has no structured output format and no downstream consumer, you haven't closed a loop — you've built a log printer. Every analysis-producing component needs: (1) structured output (JSON schema), (2) a table to write to, (3) a downstream consumer that queries that table.

---

## 30. ALTER TABLE Column Ordering Breaks Positional Index Reads

**Situation**: Added `total_dropped` column to `slm_queue_stats` table. Schema definition had it at position 4 (between `total_failed` and `queue_size_limit`). `stats()` read by positional index: `row[4]` as `total_dropped`. But `ALTER TABLE ADD COLUMN` appends to the end — in existing databases the column was at position 6. Result: `/status` showed "Dropped: 500" when the real value was 0 — it was reading `queue_size_limit` (500) from position 4.

**Lesson**: Never read SQLite rows by positional index when the schema can change via ALTER TABLE. Use explicit column names in SELECT: `SELECT total_queued, total_processed, ... FROM table`. The column order in CREATE TABLE is only guaranteed for fresh databases — ALTER TABLE always appends.

---

## 31. Cron Reminders Need Delivery Framing

**Situation**: User asked Data to set two reminders. The 60-min reminder fired on time but the LLM interpreted "check in with Data" as a task (ran `/status` and sent a health check table instead of the reminder). The 70-min reminder was never created — the LLM hallucinated a successful tool call without actually calling the cron tool (no tool call in logs, 6-second response).

**Root causes**: (1) `on_cron_job` fed `job.payload.message` directly to `process_direct` with no framing — the LLM had no way to distinguish "relay this message" from "execute this task." (2) The LLM can confidently claim it set a reminder without the tool call actually happening, especially when routing is degraded (circuit breaker open).

**Fixes**: (1) Prefix cron payloads with `[SCHEDULED REMINDER — deliver as-is]` framing. (2) Instruct Data in AGENTS.md to always include the job ID from the tool result in confirmations (no ID = hallucinated).

**Lesson**: When an LLM fires into a cold session with just a bare string, assume it will interpret that string as a task, not a message to relay. Always frame the intent explicitly. Also: LLMs will confidently confirm actions they didn't take — require tool-result evidence (like a job ID) in confirmations to make hallucinations detectable.

---

## 32. Identity File Staleness Creates Capability Blindness

**Situation**: Data told its user "I have basic tools" and "I need you to guide each step." In reality, Data has 20+ tools including browser automation, git, task system with autonomous decomposition, spawn for background work, and AWS. The identity files (AGENTS.md, sentry-router SKILL.md, memory-manager SKILL.md) were stale — still describing Redis (removed), V1 heuristic routing (replaced), and missing entire tool categories.

**Root cause**: Identity files weren't updated during the Router V2 and Redis removal refactors. Each refactor focused on code changes and forgot to update the workspace docs that shape Data's self-model.

**Lesson**: When refactoring a subsystem, the workspace identity files (AGENTS.md, relevant SKILL.md) are part of the blast radius. An LLM's capabilities are bounded by what it believes it can do — stale docs create artificial limitations. Add "update workspace docs" as a mandatory step in refactor checklists.

---

## 33. Background Services Must Not Share the User Context Pipeline

**Situation**: The heartbeat "continued a philosophical discussion" instead of executing tasks. The dream cycle, weekly/monthly reviews, cron jobs, and task retrospectives all exhibited the same vulnerability — calling `process_direct()` which ran the full user-facing context enrichment pipeline.

**Root cause**: `_process_message()` unconditionally ran proactive episodic recall, lesson injection, event consumption, and memory storage for every caller. Background service prompts about "thinking" and "awareness" semantically matched philosophical user conversations, causing cross-session memory contamination. Additionally, `get_unacknowledged_events()` destructively marked events as acknowledged, and `remember_exchange()` stored background conversations back into episodic memory (reverse contamination).

**Lesson**: When a shared function (`process_direct`) is used by both interactive and autonomous callers, the interactive-specific enrichment must be opt-in or opt-out. Background services build their own targeted prompts — dumping recalled user memories on top defeats the prompt engineering. **Rule: any new enrichment added to `_process_message()` must be guarded by `skip_enrichment`.**

---

## 34. Background Service Reports Need Per-Step Accountability

**Situation**: Dream cycle report showed "Quiet night. All systems healthy." when all aggregate counters were zero. But this was ambiguous — did all 13 jobs run cleanly and produce nothing, or did half of them silently skip? Jobs 8-13 had no success signal at all. The heartbeat, weekly, and monthly reviews had similar gaps.

**Root cause**: The dream cycle's `run()` used 13 manual try/except blocks that only recorded errors. Jobs that silently returned (missing dependency, no work to do) were indistinguishable from jobs that succeeded. The `to_summary()` only showed nonzero counters, so a clean run and a broken run could produce identical output.

**Lesson**: Every autonomous background service must produce a per-step checklist showing what ran, what was skipped (and why), and what failed. Silence is ambiguous in autonomous systems. **Rule: wrap every discrete job/step in a helper that records status, timing, and skip reason. The delivered report must include this checklist.**

---

## 35. Native Provider Preference in Failover Chains

**Rule**: When building a failover chain for a model, always put the model's native provider first. Gateways (OpenRouter, Venice) should be fallbacks, not primary. Use `registry.find_by_model()` to identify the native provider.

**Why**: Venice accepts `MiniMax-M2.5` but routes it through `openai/MiniMax-M2.5` to their own API — the user gets responses from an unknown model, not actual MiniMax.

---

## 36. LLM vs Infrastructure Concerns

**Rule**: Provider outages (circuit breaker alerts) are infrastructure concerns. Never feed them to LLMs via heartbeat_events. The LLM should never reason about which APIs are up/down.

**Why**: OpenRouter being disabled generated 13 medium alerts/day that the cognitive heartbeat and dream cycle would comment on uselessly. Provider health belongs in /status Active Alerts, not in LLM context.

---

## 37. Per-Provider Alert Dedup

**Rule**: Use `provider_failed:{name}` as alert dedup keys, not a shared `provider_failed`. Each provider needs its own alert lifecycle so recovery can be tracked independently.

**Why**: With shared key, OpenRouter's disabled state masked alerts from other providers, and recovery of one provider couldn't auto-resolve its specific alert.

---

## 38. Asyncio Timer Tasks Die Silently — Always Re-arm in Finally

**Situation**: A 10-minute cron timer silently stopped firing. No alert, no log, just gone. The `_on_timer()` method called `_save_store()` then `_arm_timer()` sequentially — if `_save_store()` threw, `_arm_timer()` never executed and the timer was permanently dead.

**Root cause**: The asyncio task running the timer tick had no exception handling. Any unhandled exception kills the task silently — asyncio doesn't propagate task exceptions to the event loop by default.

**Lesson**: Any async callback that re-arms a timer MUST use `try/finally` with the re-arm in `finally`. This applies to all periodic asyncio patterns, not just cron. Also: HealthCheckService should monitor cron timer liveness alongside Qdrant and stuck jobs.

---

## 39. Agent Iteration Exhaustion Should Force Completion, Not Discard Work

**Situation**: The bot hit "Reached 10 iterations without completion" while investigating a cron issue. All intermediate tool results and reasoning were discarded — the user got a useless error message despite the agent having done real work.

**Root cause**: When `max_iterations` was reached, the loop exited without giving the LLM a chance to summarize. The "Summarize your findings" nudge at `max_iterations - 3` still offered tools, so the LLM burned through 3 more tool-calling iterations without landing.

**Lesson**: On the final iteration, call the LLM without tools. This forces a text-only completion — the LLM must produce a summary of what it found. The nudge at N-3 is good progressive pressure, but the toolless final call is the safety net that guarantees output.

---

## 40. Provider-Agnostic Test Fixtures Beat Hardcoded Assertions

**Situation**: Routing tests hardcoded `assert len(cloud_default) == 4` and `cloud_succeed={"openrouter": False, "openai": False, "gemini": False, "minimax": False}`. When we added native provider preference (putting minimax first), two tests broke because they assumed `providers[0]` (openrouter) would be tried first. Adding a 5th provider would break every "all fail" test.

**What we built**: `tests/copilot/routing/helpers.py` with three shared utilities: `make_router(cloud_names=...)` (configurable provider count), `all_cloud_fail(router)` (fails all providers regardless of count), `patch_native(name)` (mocks `find_by_model()` to control chain order). Tests now assert behavior (failover worked, circuit breaker fired) not implementation details (specific provider count/order).

**Lesson**: When tests depend on external mutable state (provider registry, config), extract that into fixtures that query current state instead of hardcoding assumptions. `len(router._cloud)` survives adding a provider; `== 4` doesn't.

---

## 41. Tests Belong in Version Control

**Situation**: `tests/` was in `.gitignore` alongside `__pycache__` and `.pytest_cache`. Test changes couldn't be reviewed in PRs, test history was invisible, and tests drifted silently from the codebase. When the native provider preference change broke two tests, the fix couldn't be committed because tests were gitignored.

**Lesson**: Version control ALL non-generated files — code, tests, docs, config. Only gitignore generated directories (`__pycache__`, `.pytest_cache`, `build/`, `dist/`). Tests are source, not artifacts. If test changes can't be reviewed alongside code changes, bugs hide in the gap.

---

## 42. Run Ruff Before Committing, Not After

**Situation**: Built a 12-file feature (navigator duo), all tests passing, then hit 6 ruff errors on commit (pre-commit hook). Issues: `checklist` variable referenced but never defined in weekly review method (copy-paste from a method that had it), unused import, mid-file import, unused variable assignment, import sorting. Each fix required re-staging and re-attempting the commit.

**Lesson**: Run `ruff check` on changed files before attempting `git commit`, not after. Pre-commit hooks are a safety net, not the primary check. Catching lint errors before staging saves the re-stage → re-commit → re-check cycle. Rule: `ruff check <changed-files>` before `git add`.

---

## 43. Interleaved CoT Reflection Must Not Fire on Every Tool Call

**Situation**: After every tool execution, the agent loop injected `"Reflect on the results and decide next steps"` as a user message. For simple 1-tool requests like "set a reminder," this caused the LLM to generate a verbose essay instead of confirming the action. User asked to set a reminder; bot gave a 5-paragraph "Reflection on this conversation" summary.

**Lesson**: Unconditional reflection injection turns the LLM into an essay generator. Only inject steering messages when they serve a purpose — the "Summarize your findings" nudge in the last 3 iterations is good progressive pressure; blanket reflection after every tool call is actively harmful. The LLM knows how to chain tool calls without being told to reflect.

---

## 44. Cron `at` Parameter Must Respect Timezone

**Situation**: User set a reminder for 5:12 PM EST. The `at` parameter received a naive ISO string (`2026-02-20T17:12:00`). Python's `datetime.fromisoformat()` created a naive datetime, and `.timestamp()` interpreted it as the server's timezone (UTC), causing a 5-hour offset. The `tz` parameter was explicitly blocked for `at` (only allowed with `cron_expr`), preventing the obvious fix.

**Lesson**: Never interpret naive datetimes as UTC on a UTC server when the user is in a different timezone. Apply `ZoneInfo(tz)` when provided, fall back to `datetime.now().astimezone().tzinfo` for the system's local timezone. And don't restrict timezone parameters to one scheduling mode when the underlying problem (naive datetime interpretation) affects all modes.

---

## 45. Cross-Session Message Delivery Needs Breadcrumbs

**Situation**: Cron reminder fired in session `cron:{job_id}`, delivered to user's WhatsApp chat. User replied. Bot had zero context about the reminder because the reply loaded session `whatsapp:{chat_id}`, which had no record of the reminder being delivered.

**Lesson**: When a background service delivers a message to a user's chat, inject a breadcrumb into the user's active session (e.g., `[Scheduled reminder delivered: ...]`). This bridges the session boundary so the user's next reply has context. The cost is one `session.add_message()` call; the alternative is a confused bot that doesn't know what the user is talking about.

---

## 46. Uncommitted Changes Are Not Changes

**Situation**: Previous session implemented 4 code changes (cron timer resilience, health check monitoring, agent loop graceful degradation, alert on exhaustion), ran all tests, verified in production — but never committed. Next session found all changes gone, likely overwritten by a branch merge or checkout. All work had to be reimplemented from scratch.

**Lesson**: If you implemented it but didn't commit it, it doesn't exist. Always commit before ending a session. Uncommitted work is one `git checkout` away from vanishing. The commit is the unit of durability, not the file edit.
