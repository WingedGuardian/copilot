# Changes from Upstream Nanobot

> nanobot is an open-source AI assistant by HKUDS (~3.6K core lines, MIT license). This document tracks all modifications made for the Executive Co-Pilot project.

---

## Philosophy

The original plan was to keep nanobot completely stock and build a separate proxy. We abandoned this in favor of direct integration with minimal hooks. The goal: touch as few existing files as possible, add "copilot" functionality in a separate package (`nanobot/copilot/`), and keep hooks thin enough that upstream merges remain tractable.

---

## Modified Existing Files

### 1. `nanobot/agent/loop.py` (~115 lines added)

**Purpose**: Wire copilot components into the message processing pipeline.

| Hook | What it does |
|---|---|
| Slash commands | `/onboard`, `/profile`, `/use <provider>`, `/model`, `/private` — session metadata flags |
| `/use` overhaul | Multi-form parsing (tier, explicit model), 30-min auto-expiry, routing preferences |
| Routing preferences | Keyword-based conversation continuity after `/use` timeout |
| Approval intercept | Before normal processing, check if incoming message is an approval response |
| Satisfaction check | Regex-based satisfaction signal detection on every user message |
| Lesson fetch | Retrieve relevant lessons with config-driven limit and min confidence |
| Approval gate | Before tool execution, check if tool requires approval |
| Session metadata | Always pass `session.metadata` to context builder |

**Why in loop.py**: These are interception points that must run before/after core processing. There's no way to add them externally without monkey-patching.

### 2. `nanobot/agent/context.py` (~30 lines added)

**Purpose**: Support onboarding interview and session metadata.

| Change | What it does |
|---|---|
| `_ONBOARDING_PROMPT` | Class variable with interview script (~500 tokens) |
| `session_metadata` param | Added to `build_messages()` signature |
| Injection logic | When `onboarding_active` flag is set, append interview prompt to system prompt |

**Why in context.py**: The system prompt is assembled here. Onboarding prompt injection must happen at assembly time.

### 3. `nanobot/cli/commands.py` (~150 lines added)

**Purpose**: Initialize and wire all copilot components on gateway startup.

| Change | What it does |
|---|---|
| Copilot init block | Creates RouterProvider, ExtendedContextBuilder, BackgroundExtractor, CostLogger, ThreadTracker, etc. |
| Phase 3 init | Creates ApprovalInterceptor, LessonManager, SatisfactionDetector, CostAlerter |
| Provider setup | Initializes multi-provider registry with failover chains |
| Supervisor wiring | Registers services with `get_task_fn` for fire-and-forget support |
| Dream scheduler | Croniter-based loop with runtime cron expr reload, cancel event for reschedule |
| Memory retry | 3-attempt init with 2s delay for transient Qdrant startup |
| Preference tool | SetPreferenceTool registration with router + reschedule callbacks |
| Startup warnings | Yellow warnings when monitor_chat_id or approval_chat_id are empty |

**Why in commands.py**: This is the startup orchestrator. Components must be created and wired here.

### 4. `nanobot/providers/registry.py` (~100 lines added)

**Purpose**: Extended provider registry with Venice AI, Nvidia NIM, and enhanced routing.

| Change | What it does |
|---|---|
| New ProviderSpecs | Venice AI, Nvidia NIM entries |
| Auto-prefixing | Model name translation for different provider APIs |
| Fallback logic | Provider selection based on API key availability |

**Why in registry.py**: This is the provider abstraction layer. New providers must be registered here.

### 5. `nanobot/channels/whatsapp.py` (~20 lines changed)

**Purpose**: Fix WhatsApp bridge issues and add resilience.

| Change | What it does |
|---|---|
| jidDecode polyfill | Handles missing function in newer Baileys versions |
| Auto-start | Bridge process started from gateway if not running |
| Connection logging | Better visibility into bridge connection state |

**Why in whatsapp.py**: These are channel-specific fixes that can't live anywhere else.

---

## Modified Existing Files (Post-V1)

### 6. `nanobot/config/loader.py` (~60 lines added)

**Purpose**: Secrets separation and security hardening.

| Change | What it does |
|---|---|
| `get_secrets_path()` | Returns `~/.nanobot/secrets.json` path |
| `_deep_merge()` | Recursively merge secrets into config (10 lines) |
| `_extract_secrets()` | Strip API keys from config before saving |
| `_migrate_secrets()` | Auto-migration: extract secrets from legacy config.json on first load |
| Load logic | Merge secrets.json on top of config.json if exists |
| Save logic | Split secrets before writing, chmod 0o600 on secrets file |

**Why in loader.py**: This is the config I/O boundary. Secrets split must happen at load/save time.

### 7. `nanobot/session/manager.py` (~20 lines added)

**Purpose**: Support `/use` override lifecycle.

| Change | What it does |
|---|---|
| `activate_use_override()` | Set force_provider, force_tier, force_model, timestamp |
| `deactivate_use_override()` | Clear all override metadata fields |

**Why in manager.py**: Session metadata is managed here. Override state is session metadata.

### 8. `nanobot/copilot/routing/router.py` (~70 lines added, V2 rewrite 2026-02-20)

**Purpose**: Plan-based routing via PlanRoutingTool (Router V2). Replaces heuristic classify() with LLM-driven routing plans.

| Change | What it does |
|---|---|
| Router V2 (2026-02-20) | Plan-based routing via `PlanRoutingTool` — LLM decides routing, no heuristic classification |
| `check_use_override_timeout()` | Same pattern as private mode timeout check |
| `check_routing_preference()` | Query SQLite for keyword-matched routing preferences |
| `set_model()` | Hot-swap model at runtime |
| `/use` override | Respect force_provider and force_model fields |

**Why in router.py**: This is the routing decision layer. V2 replaces heuristic tier routing with plan-based LLM routing.

### 9. `nanobot/copilot/config.py` (~2 lines added)

**Purpose**: Add `use_override_timeout` config field.

| Change | What it does |
|---|---|
| `use_override_timeout: int = 1800` | Timeout for `/use` overrides (30 minutes) |

**Why in config.py**: This is the copilot config schema. New config fields go here.

### 10. `nanobot/copilot/metacognition/detector.py` (~5 lines added)

**Purpose**: Fix negative satisfaction catch-22.

| Change | What it does |
|---|---|
| Negative penalization | Call `penalize()` on recently applied lessons when negative signal detected |

**Why in detector.py**: This is where satisfaction signals are processed. Penalization logic belongs here.

### 11. `nanobot/copilot/cost/db.py` (~20 lines added)

**Purpose**: Add routing_preferences table.

| Change | What it does |
|---|---|
| `migrate_routing_preferences()` | Create routing_preferences table with session_key, provider, tier, model, keywords, confidence |

**Why in db.py**: This is the SQLite schema manager. New tables go here.

### 12. `nanobot/copilot/dream/cycle.py` (~50 lines added)

**Purpose**: Always deliver, self-reflection, routing preference cleanup.

| Change | What it does |
|---|---|
| `_self_reflect()` | New dream job: ask LLM "what could be better?" and store actionable insights |
| `_cleanup_routing_preferences()` | Remove preferences older than 7 days |
| Always deliver | Send message even when nothing notable (adds "Quiet night" message) |
| Reflection field | Add to DreamReport and to_summary() |

**Why in cycle.py**: This is the dream cycle orchestrator. New jobs and delivery logic go here.

---

## New Package: `nanobot/copilot/`

**~2970 lines across 14 sub-packages.** This is where all copilot intelligence lives.

```
nanobot/copilot/
├── routing/        # RouterProvider (V2: plan-based via PlanRoutingTool), failover (replaces LiteLLM for routing)
├── context/        # ExtendedContextBuilder, token budget (wraps base ContextBuilder)
├── extraction/     # Background SLM fact/decision/constraint extraction
├── approval/       # Natural language approval system
├── metacognition/  # Satisfaction detection, lesson management
├── cost/           # Cost logging, alerting, database, routing preferences
├── memory/         # Qdrant episodic, SQLite structured + FTS5 keyword search (working)
├── tasks/          # Task queue, worker (working)
├── tools/          # Git, browser, documents, AWS, n8n, preferences (V2)
├── status/         # Health dashboard aggregation (working)
├── dream/          # Nightly cycle, monitoring, supervisor (working)
├── threading/      # Topic thread tracking
├── voice/          # Voice transcription
└── alerting/       # Alert bus and commands
```

---

## New Package: `nanobot/agent/mcp/`

**~250 lines.** Model Context Protocol integration for external tool servers.

```
nanobot/agent/mcp/
├── bridge.py       # Bridges MCP tools into nanobot's tool system
├── client.py       # Connects to external MCP servers
└── manager.py      # Manages tool discovery and routing
```

---

## New Package: `nanobot/agent/safety/`

**~50 lines.** Security hardening.

```
nanobot/agent/safety/
└── sanitizer.py    # Blocks MRO chain sandbox escape attempts
```

---

## Bridge Changes: `bridge/src/whatsapp.ts`

- jidDecode polyfill for newer Baileys compatibility
- Improved error handling on message send failures

---

## Summary of Upstream Impact

| Metric | Value |
|---|---|
| Existing files modified | 12 |
| Lines added to existing files | ~520 |
| New files added | ~48 |
| New lines (copilot + mcp + safety) | ~3200 |
| Ratio (new : modified) | 6:1 |

The 6:1 ratio reflects the "thin hooks, fat modules" philosophy. The vast majority of code lives in new packages that don't touch upstream nanobot at all.

---

## Merge Strategy for Upstream Updates

**Current plan**: Upstream merges are sequenced against V2.1 implementation phases. See `POST-V2-UPSTREAM-MERGE.md` for the full 63-item inventory and timing.

**Summary**:
- **Before V2.1** (`fix/upstream-sync`): Cherry-pick bug fixes into `session/manager.py` (#55 tool metadata), `context.py` (#36 empty content), `schema.py` (#42 provider matching)
- **During V2.1 Phase 2-3**: Start `loop.py` and `commands.py` from upstream base, re-apply copilot hooks, build V2.1 on top
- **After V2.1** (`chore/config-cleanup`): Adopt Base alias model in `schema.py`/`loader.py`, wire MCP in schema

**For future upstream pulls** (beyond v0.1.4):
1. `git fetch upstream && git diff upstream/main -- nanobot/agent/loop.py nanobot/agent/context.py nanobot/cli/commands.py nanobot/providers/registry.py nanobot/channels/whatsapp.py`
2. If upstream changed these 5 files, manual merge required (but changes are localized and well-commented)
3. All other upstream changes merge cleanly — copilot package is additive
4. Run `pytest tests/` after merge to verify nothing broke
