# Changelog

All notable changes to the Executive Co-Pilot project.

---

## [Post-V1 Enhancements] — 2026-02-16

### Fixed — Memory Leak Fixes (Critical)
Three unbounded data structure growth patterns eliminated:

1. **SessionManager cache eviction**: `_cache` now uses `OrderedDict` with LRU eviction at `_max_cache_size=256`. Eviction happens in both `get_or_create()` and `save()` to prevent unbounded growth with many unique sessions. Previously, the dict grew indefinitely with one entry per unique session ID.
   - File: `nanobot/session/manager.py`

2. **Extractions list cap**: Session metadata extractions list now capped at last 1000 entries via `session.metadata["extractions"] = extractions[-1000:]` in message processing loop. Prevents long-lived sessions from accumulating one entry per message indefinitely.
   - File: `nanobot/cli/commands.py:544`

3. **AlertBus deduplication pruning**: Every 100 alerts, `_last_sent` dict prunes expired dedup keys (entries older than cooldown window). Prevents unbounded growth from unique `(subsystem, error_key)` pairs over long runtimes.
   - File: `nanobot/copilot/alerting/bus.py`

### Changed — CoT Reflection Decay
- Last 3 reflection iterations now use "Summarize" prompt instead of "Reflect" to prevent infinite tool loops
- Prevents recursive self-analysis when reflection tools trigger additional reflections
- File: `nanobot/agent/loop.py`

### Changed — Graceful Shutdown
- `AgentLoop.stop()` now async, awaits cancellation of tracked background tasks
- Ensures clean shutdown without orphaned tasks or partial writes
- File: `nanobot/agent/loop.py`

### Changed — WhatsApp Reconnection Backoff
- Exponential backoff with jitter: `5 * 2^n` seconds, capped at 120s
- Prevents aggressive reconnection storms when bridge or network is unstable
- File: `bridge/src/whatsapp.ts`

### Changed — MEMORY.md Slim-Down (Token Budget Enforcement)
- Trimmed MEMORY.md from ~1200 tokens to ~311 tokens — behavioral core only
- Moved goals, action plan, life situation, and development principles to Qdrant episodic memory (4 entries, `session_key="system:core_memory"`, `role="preference"`)
- Added "Deep Context" reference line telling the LLM to use `recall_messages` for detailed context
- Added dream cycle Job 9: `_check_memory_budget()` — reads MEMORY.md, estimates tokens, logs `heartbeat_events` warning if over 400 token budget
- Saves ~800-900 tokens per message across all conversations
- Files changed: `~/.nanobot/workspace/memory/MEMORY.md`, `nanobot/copilot/dream/cycle.py`

### Added — V2 Success Criteria
- Added "What Successful Implementation Looks Like" section to V2 Architecture doc
- 6 concrete success criteria: retrieval gap (V2.3), bad memory correction (V2.2+V2.3), prioritization framework (V2.1), autonomy calibration (V2.3), memory budget enforcement (ongoing), model tier metacognition observation

---

## [Post-V1 Enhancements] — 2026-02-15

### Fixed — /use Override Never Reverting (Bug)
- `touch_activity()` was called before the timeout check, resetting elapsed time to ~0 every message
- Moved timeout check before `touch_activity()` for both `/use` and private mode
- Changed default timeout from 30min to 60min
- Conversation continuity already works: when override expires, routing preferences auto-restore the provider for same-topic follow-ups

### Fixed — Context Continuity Bugs
- Proactive recall: wrapped in `asyncio.wait_for(timeout=2.0)` to prevent hangs when Qdrant/embedder is slow
- Orientation hint: changed `len(real_history) < 6` to `0 < len(real_history) < 6` — no longer fires on brand-new conversations
- Proactive recall budget: reduced from 800 to 200 tokens — appropriate for a nudge, tool handles detailed retrieval

### Fixed — Cost Tracking Accuracy
- Added missing model aliases to `_PRICING` dict (claude-haiku-4.5, claude-opus-4.6, claude-sonnet-4.5, qwen2.5-14b-instruct)
- Added litellm `cost_per_token()` fallback for models not in local pricing table
- Backfilled 126 historical zero-cost rows ($11.34 total was invisible)

### Added — Error Visibility in /status
- `/status` now shows "Alerts (24h)" section with timestamped errors/warnings, deduplicated by error_key with occurrence counts
- Shows "No errors or warnings" when clean
- Wired 5 agent loop error sites to AlertBus: message processing errors, background task failures, turn timeouts, LLM timeouts
- Wired 2 channel manager crash sites to AlertBus: channel crashes, max restart exceeded

### Added — Session & Token Context in /status
- Shows current session token usage as percentage of context window (e.g., "12,450 / 200,000 tokens (6%)")
- Shows active sessions (last 1h) and total session count
- SLM Queue: shows "Not connected" when not wired, "Empty (local SLM handling extractions directly)" when connected but idle
- Uses existing `TokenBudget` class for on-demand computation (cheap, cached tiktoken)

### Changed — Extraction: Local SLM Only (No Haiku Fallback)
- Removed Haiku cloud fallback from background extraction — extraction is non-urgent background work
- Flow is now: local SLM → queue for deferred processing → heuristic regex (immediate low-quality results)
- SLM queue drainer processes deferred items when LM Studio comes back online
- Saves ~$0.001/extraction (84 Haiku calls were visible in cost_log from background extraction alone)

---

## [Post-V1 Enhancements] — 2026-02-14

### Added — `/use` Overhaul + Runtime Preferences
- `/model` command (alias for `/use`) with tier and explicit model support
  - `/use openrouter fast` → routes to fast_model via OpenRouter
  - `/use venice gpt-4o` → routes to specific model via Venice
  - `/use auto` → return to automatic routing
- 30-minute auto-expiry for `/use` overrides (configurable via `use_override_timeout`)
- Routing preferences: keyword-based conversation continuity after `/use` timeout
  - Stores top 10 keywords from recent messages, auto-restores override when resuming topic
  - Max 20 preferences per session, 7-day expiry, SQLite-backed
- `SetPreferenceTool` — natural language config changes via LLM
  - "set my fast model to gpt-4o-mini" → immediate effect + persistence
  - "run the dream cycle at 5am" → reschedules cron on the fly
  - Supports: model tiers, dream cron, heartbeat interval, cost alerts, context budget, lesson params

### Added — Secrets Separation
- Split `~/.nanobot/config.json` into config.json (preferences) + secrets.json (API keys)
- `secrets.json` created with mode 0o600 (owner read/write only)
- Auto-migration on first load: extracts API keys from legacy config.json
- Deep merge on load: secrets override empty config values
- Cloud models and tools can no longer read API keys from config file

### Added — Dream Cycle Always Delivers
- Dream cycle now ALWAYS sends a message to user after completion
- "Quiet night" message when nothing notable to report
- New self-reflection job: LLM reviews 24h activity and suggests improvements
- Reflection summary included in dream report

### Fixed — Catch-22 Patterns
- Negative satisfaction now penalizes active lessons (was creating lessons but never penalizing)
- `lesson_injection_count` and `lesson_min_confidence` config fields now consumed (were hardcoded)
- Startup warnings when `monitor_chat_id` or `approval_chat_id` are empty (alerts were failing silently)

### Changed
- `nanobot/config/loader.py` — secrets split (~60 lines)
- `nanobot/session/manager.py` — +use override helpers (~20 lines)
- `nanobot/copilot/routing/router.py` — +timeout, +tier routing, +set_model, +routing preference check (~70 lines)
- `nanobot/agent/loop.py` — /use+/model handler, timeout, preferences, config passthrough (~75 lines)
- `nanobot/copilot/config.py` — +use_override_timeout field (~2 lines)
- `nanobot/copilot/tools/preferences.py` — NEW: SetPreferenceTool (~130 lines)
- `nanobot/cli/commands.py` — tool registration, migration, reschedule wiring, warnings (~40 lines)
- `nanobot/copilot/metacognition/detector.py` — +negative penalization (~5 lines)
- `nanobot/copilot/cost/db.py` — +routing_preferences table (~20 lines)
- `nanobot/copilot/dream/cycle.py` — +always deliver, +self-reflect, +preference cleanup (~50 lines)

**Total: ~470 lines changed/added across 10 files (1 new)**

---

## [V1 Complete] — 2026-02-14

### Fixed — V1 Completion (Memory, Dream Cycle, Supervisor)
- Declared missing runtime dependencies (`qdrant-client`, `redis`, `openai`, `aiosqlite`) in `pyproject.toml` — these were causing silent memory degradation via ImportError → graceful fallback → no memory
- Fixed ProcessSupervisor false crash detection: fire-and-forget `start()` methods returned immediately, supervisor interpreted this as a crash and restarted 5 times before giving up. Added `get_task_fn` parameter to await internal long-running tasks.
- Eliminated double-start of supervised services (explicit `await start()` + supervisor `_run_service()` both calling `start()`)
- Added dream cycle scheduler via `croniter` consuming `dream_cron_expr` config (default `"0 3 * * *"`)
- Added memory initialization retry (3 attempts, 2s delay) for transient QDrant/Redis startup delays
- ~50 lines changed across 3 files. No new files. No new features — just making existing code run.

### Added — Onboarding Interview System
- `/onboard` command triggers structured getting-to-know-you interview
- `/profile` command shows current user profile
- Interview conducted by nanobot's own LLM via prompt injection (~500 tokens)
- Token-conscious storage: lean USER.md (~10 lines) + detailed MEMORY.md
- Updated `/help` text with new commands

### Added — Multi-Cloud Failover
- Venice AI provider support (privacy-focused, uncensored models)
- Nvidia NIM provider support (GPU-optimized inference)
- FailoverChain: each routing tier tries multiple providers before escalating
- `/use <provider>` command for manual provider override

### Fixed — WhatsApp Bridge
- jidDecode polyfill for newer Baileys versions (messages were failing silently)
- Auto-start bridge process from gateway
- Improved connection state logging

### Changed — Provider Registry
- Extended from ~15 to 30+ supported providers
- Auto-prefixing for cross-provider model name translation

---

## [0.1.3.post7] — 2026-02-13

### Added — Security Hardening
- MRO chain sandbox escape blocked (`agent/safety/sanitizer.py`)
- Private mode activation wired into routing

### Added — MCP Integration
- Model Context Protocol client for external tool servers
- MCP bridge for tool discovery and routing
- Optional dependency: `mcp>=1.0.0`

---

## [Phase 3] — 2026-02-12

### Added — Approval System
- `ApprovalInterceptor` orchestrates full approval flow
- `NLApprovalParser` — regex + SLM for natural language approval parsing
- `RulesEngine` — default patterns + dynamic user-created rules
- `ApprovalQueue` — asyncio.Event-based blocking with crash recovery
- Only `exec` and `message` tools require approval by default
- Quick cancel: "skip", "nevermind" → immediate abort

### Added — Metacognition
- `SatisfactionDetector` — regex positive/negative signal detection
- `LessonManager` — CRUD with confidence scoring, reinforcement, decay
- Lessons injected into system prompts (top 3 by relevance)
- Automatic deactivation of unhelpful lessons

### Added — Cost Alerting
- `CostAlerter` — per-call and daily threshold alerts via WhatsApp
- `CostLogger` — per-call cost calculation and routing decision logging

---

## [Phase 2] — 2026-02-11

### Added — Copilot Core
- `RouterProvider` — drop-in LLMProvider with heuristic routing
- `ExtendedContextBuilder` — tiered context assembly (3 tiers)
- `TokenBudget` — context budget management and continuation detection
- `BackgroundExtractor` — async fact/decision/constraint extraction
- `ThreadTracker` — topic-based conversation thread detection
- `VoiceTranscriber` — faster-whisper + API fallback
- Self-escalation: local model can trigger retry with bigger model
- Private mode: local-only routing with 30-min auto-timeout

### Added — Memory, Dream Cycle & Infrastructure Modules
- `copilot/memory/` — QDrant episodic (multi-factor scoring, hybrid search), Redis working (auto-reconnect), full-text search (FTS5 + BM25)
- `copilot/dream/` — nightly cycle (7 jobs orchestrated), heartbeat (proactive tasks, active hours guard), monitor (state-transition alerting, morning nag), supervisor (auto-restart, exponential backoff)
- `copilot/tasks/` — task manager, worker, tool interface
- `copilot/tools/` — git, browser, documents, AWS, n8n (V2 — not yet registered as agent tools)
- `copilot/status/` — health dashboard aggregation

---

## [Phase 1] — 2026-02-10

### Added — Foundation
- nanobot cloned and configured
- LM Studio connected (Windows 5070ti, 192.168.50.100:1234)
- WhatsApp channel via Baileys bridge (Node.js)
- QDrant (localhost:6333) and Redis (localhost:6379) infrastructure
- SQLite database for structured data
- `~/.nanobot/config.json` with provider configuration
- Skill stubs: sentry-router, memory-manager, status
- End-to-end WhatsApp message flow verified
