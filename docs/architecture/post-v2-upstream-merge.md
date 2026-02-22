# Upstream Merge — Complete Inventory of Skipped v0.1.4 Features

> **Updated 2026-02-20** — Comprehensive analysis of 63 discrete upstream changes we lack across 6 files, with sequenced merge plan tied to V2.1 implementation phases.

## Setup

```
upstream → HKUDS/nanobot (base framework)
```

To check upstream for new changes: `git fetch upstream && git log upstream/main..HEAD --oneline`

---

## Merge Sequencing Plan

### BEFORE V2.1 — Pre-V2 Bug Fixes (`fix/upstream-sync` branch)

Cherry-pick specific upstream fixes into our existing files. These are live bugs in current production — waiting for V2.1 means living with broken behavior during the entire build. "Stabilize before extending."

| File | Items to Take | Items to Skip | Why Now |
|------|--------------|---------------|---------|
| `session/manager.py` | #55 (tool metadata), #58 (last_consolidated), #60 (invalidate), #61 (clear resets) | #56-57 (workspace sessions), #59 (default 500), #62 (error filtering), #63 (keep atomic writes) | #55 is a live bug — multi-turn tool conversations break on session reload |
| `context.py` | #36 (empty content fix) | #37-39 (structural divergences), #40 (keep document extraction) | 3-line fix for API crashes on backends that reject empty text blocks |
| `schema.py` | #42 (provider matching) | #41 (MCPServerConfig — park for post-V2), #43-46 (park for post-V2) | OAuth providers misroute without normalized prefix matching |

### DURING V2.1 Phase 2-3 — Start from Upstream Base

For `loop.py` and `commands.py`, **start from upstream's v0.1.4 files as the base and re-apply copilot hooks**. This is cleaner than cherry-picking 19+ individual features into our heavily modified versions. V2.1 rewrites the same code paths anyway — merging upstream independently would be wasted work immediately overwritten.

| File | V2.1 Phase | Items Gained (free) | Copilot Hooks to Re-apply |
|------|-----------|--------------------|----|
| `loop.py` | Phase 2 (Task 2.2 Orchestrator), Phase 0 (P0.2 race fix, P0.7 classify/chat split) | All 19: progress streaming, `_strip_think()`, empty content, temperature/max_tokens, MCP lifecycle, consolidation fixes, `_tool_hint()`, json_repair | Copilot hooks, routing, cost logging, slash commands (~1046L diff — but most is routing logic being rewritten for V2 anyway) |
| `commands.py` | Phase 3 (Task 3.2 Commands wiring) | All 16: temperature/MCP passthrough, CustomProvider/Codex wiring, OAuth handling, CLI progress, `close_mcp()` | Copilot init, provider setup, dream scheduler (~1084L diff — but provider setup is being restructured for V2 anyway) |

**Sequence**: Pull upstream file → apply Phase 0 fixes (P0.2, P0.7) → re-apply copilot hooks → build V2.1 features on clean foundation.

**Rationale**: V2.1 fundamentally reworks routing (plan-based via PlanRoutingTool), adds an orchestrator with DAG-based task management, and introduces multi-agent sessions. Starting fresh from upstream gives us progress streaming, MCP wiring, temperature config, and consolidation fixes for free.

### AFTER V2.1 — Config Cleanup (`chore/config-cleanup` or `feat/mcp-wiring` branch)

Low-priority items and coherent feature bundles that aren't blocking V2.1. Do after V2.1 ships and stabilizes.

| File | Items to Take | Items to Skip | Notes |
|------|--------------|---------------|-------|
| `schema.py` | #41 (MCPServerConfig), #43 (Base alias model), #44-46 (provider/Slack config fields) | #47-49 (keep venice/nvidia, default_model, llm_timeout) | MCP wiring should be a single coherent branch: schema + loop + commands together |
| `loader.py` | #50 (by_alias save), #52 (remove convert_keys), #54 (simplified validate) | #51 (keep secrets separation), #53 (keep get_secrets_path) | Only adopt with #43 (Base alias model) — they're a package deal |

---

## Critical Gaps (reference — see sequencing above for timing)

### 1. MCP Pipeline Unwired (5 related items) → **DURING V2.1** (loop.py/commands.py rebase) + **AFTER V2.1** (schema.py MCPServerConfig)
We merged `nanobot/agent/tools/mcp.py` but have **zero integration**:
- No `MCPServerConfig` in `schema.py` (config has no way to define MCP servers)
- No `mcp_servers` param in `AgentLoop.__init__`
- No `_connect_mcp()` / `close_mcp()` lifecycle in `loop.py`
- No `mcp_servers=config.tools.mcp_servers` in `commands.py` gateway/agent setup
- **Files**: `schema.py`, `loop.py`, `commands.py`

### ~~2. `get_history()` Strips Tool Metadata~~ → **DONE** (fix/upstream-sync, 2026-02-20)
~~Our `get_history()` returns only `{role, content}`, losing `tool_calls`, `tool_call_id`, and `name`.~~
**Fixed**: `get_history()` now preserves `tool_calls`, `tool_call_id`, `name` fields. Also handles `None` content safely.
- **File**: `session/manager.py`

### 3. `_strip_think()` Missing → **DURING V2.1** (loop.py rebase)
No stripping of `<think>...</think>` blocks from models like DeepSeek R1. These leak into user-facing responses whenever thinking models are used (even via routing).
- **File**: `loop.py`

---

## Complete Inventory by File

### `nanobot/agent/loop.py` (19 items)

**HIGH**
| # | Feature | Description |
|---|---------|-------------|
| 1 | Progress streaming (`on_progress` callback) | Pushes intermediate tool-use content to user during multi-step execution. Real-time UX feedback. |
| 2 | `_strip_think()` static method | Strips `<think>...</think>` blocks from DeepSeek R1 etc. Applied to progress and final output. |
| 3 | Empty assistant content fix | Omits `content` key when empty/None, preventing crashes on backends that reject empty text blocks. |
| 4 | `temperature` and `max_tokens` as constructor params | Passes these through to `provider.chat()`. Our loop has neither. |
| 5 | MCP server connection (`_connect_mcp`, `close_mcp`) | Lazy MCP via `AsyncExitStack`, connecting at first `run()`. We have mcp.py merged but no wiring. |
| 6 | `mcp_servers` constructor param | Accepts `mcp_servers: dict | None` to configure MCP connections. |

**MEDIUM**
| # | Feature | Description |
|---|---------|-------------|
| 7 | `_tool_hint()` static method | Formats tool calls as concise hints like `web_search("query...")` for progress display. |
| 8 | `json_repair` for consolidation | Uses `json_repair.loads()` instead of `json.loads()` for memory consolidation. More robust. |
| 9 | `memory_update` in consolidation | Consolidation prompt asks for `memory_update` (updated MEMORY.md content) in addition to `history_entry`. |
| 10 | `last_consolidated` tracking | Tracks `session.last_consolidated` to avoid re-processing already-consolidated messages. |
| 11 | Non-destructive consolidation | Does NOT trim `session.messages` during partial consolidation. Our code trims to `keep_count`, destroying context. |
| 12 | `/new` race condition fix | Copies `session.messages` before clearing, then consolidates the copy in background. |
| 13 | Removal of interleaved CoT injection | Removes "Reflect on results" user messages injected between tool calls. Ours injects these, wasting tokens. |

**LOW**
| # | Feature | Description |
|---|---------|-------------|
| 14 | `_set_tool_context()` helper | DRY refactor for repeated tool-context-update code. |
| 15 | `_run_agent_loop()` extracted method | Agent iteration loop used by both message types, eliminating ~100L duplication. |
| 16 | `session.invalidate()` after `/new` | Evicts cache entry after clearing for fresh state on next access. |
| 17 | `get_history(max_messages=)` | Passes `memory_window` to `session.get_history()`. Ours always uses default 50. |
| 18 | `stop()` is synchronous | Simpler shutdown semantics. |
| 19 | Improved empty response guard | Simpler fallback message when no content after loop. |

---

### `nanobot/cli/commands.py` (16 items)

**HIGH**
| # | Feature | Description |
|---|---------|-------------|
| 20 | `temperature` + `max_tokens` passed to AgentLoop | Passes `config.agents.defaults.temperature/max_tokens` in gateway() and agent(). |
| 21 | `mcp_servers` passed to AgentLoop | Passes `config.tools.mcp_servers` in gateway() and agent(). |

**MEDIUM**
| # | Feature | Description |
|---|---------|-------------|
| 22 | `CustomProvider` wiring | Detects `provider_name == "custom"` and returns `CustomProvider`. File exists, never instantiated. |
| 23 | `OpenAICodexProvider` wiring | Detects `openai_codex` provider or prefix and returns `OpenAICodexProvider`. |
| 24 | OAuth provider login commands | `nanobot provider login <name>` for openai_codex (oauth_cli_kit) and github_copilot (litellm device flow). |
| 25 | `is_oauth` handling in key validation | Skips "No API key" error for `is_oauth=True` providers. Our code rejects them. |
| 26 | CronService in CLI agent command | Creates CronService so cron tools work in interactive CLI mode. |
| 27 | CLI progress callback (`_cli_progress`) | Prints intermediate tool progress as dim text in CLI mode. |
| 28 | `close_mcp()` in CLI shutdown | Calls `agent_loop.close_mcp()` on exit. |
| 29 | Model-based `_make_provider` routing | Calls `config.get_provider_name(model)` for model-to-provider mapping. |

**LOW**
| # | Feature | Description |
|---|---------|-------------|
| 30 | Config overwrite option in onboard | "Overwrite or refresh?" prompt when config exists. |
| 31 | Workspace existence check in onboard | Checks `if not workspace.exists()` before creating. |
| 32 | Interactive CLI try/finally restructure | Ensures `close_mcp()` runs on exit. |
| 33 | Cron timezone display | Shows timezone in `cron list`, localized next-run. |
| 34 | Cron timezone CLI arg (`--tz`) | IANA timezone for `cron add`. |
| 35 | `is_oauth` in status display | Shows `(OAuth)` indicator for OAuth providers. |

---

### `nanobot/agent/context.py` (5 items)

| # | Importance | Feature | Description |
|---|-----------|---------|-------------|
| 36 | ~~HIGH~~ **DONE** | Empty content handling in `add_assistant_message` | ~~Conditionally omits `content` key when empty. Prevents API errors.~~ **Fixed in `fix/upstream-sync` (2026-02-20)** |
| 37 | LOW | Updated `BOOTSTRAP_FILES` list | `["AGENTS.md", "SOUL.md", "USER.md", "TOOLS.md", "IDENTITY.md"]` — adds TOOLS.md, IDENTITY.md, removes POLICY.md. |
| 38 | LOW | Rewritten system prompt | Fuller self-description vs terse "See SOUL.md". |
| 39 | LOW | `session_metadata` param removed | Structural divergence — we use it for onboarding injection. |
| 40 | N/A | Document extraction removed | Upstream removed PDF/XLSX/CSV handling. We WANT to keep ours. |

---

### `nanobot/config/schema.py` (9 items)

**HIGH**
| # | Feature | Description |
|---|---------|-------------|
| 41 | `MCPServerConfig` schema | New model (command, args, env, url) + `mcp_servers: dict` on ToolsConfig. Required for MCP. |
| 42 | ~~Provider matching improvements~~ **DONE** | ~~Normalized prefix matching, prefix-wins logic, `is_oauth` support. Without this, OAuth providers misroute.~~ **Fixed in `fix/upstream-sync` (2026-02-20)** |

**MEDIUM**
| # | Feature | Description |
|---|---------|-------------|
| 43 | `Base` model with alias generator | `alias_generator=to_camel, populate_by_name=True` on all config models. Both camelCase and snake_case accepted natively. |
| 44 | `siliconflow` provider config field | We have the registry entry (merged) but no config field. |
| 45 | `openai_codex` + `github_copilot` config fields | Registry entries exist, no config fields. |
| 46 | Slack `reply_in_thread` + `react_emoji` config | New Slack channel config options. |

**LOW / N/A (intentional divergence)**
| # | Feature | Description |
|---|---------|-------------|
| 47 | `venice` + `nvidia` removed from ProvidersConfig | Upstream removed these. We keep them (in use). |
| 48 | `default_model` removed from ProviderConfig | We keep it (used by `/use` command). |
| 49 | `llm_timeout` removed from AgentDefaults | We keep it (per-call timeout). |

---

### `nanobot/config/loader.py` (5 items)

All N/A or LOW — we intentionally diverge (secrets separation, atomic writes):

| # | Feature | Description | Keep ours? |
|---|---------|-------------|-----------|
| 50 | `model_dump(by_alias=True)` in save | Native camelCase serialization. | Adopt when we adopt Base alias model |
| 51 | Removal of secrets separation | All config in one file. | YES — keep ours |
| 52 | Removal of `convert_keys`/`camel_to_snake` | Pydantic alias handles it. | Adopt with #43 |
| 53 | Removal of `get_secrets_path()` | Not needed without secrets split. | Keep ours |
| 54 | Simplified `Config.model_validate(data)` | Direct call without conversion. | Adopt with #43 |

---

### `nanobot/session/manager.py` (9 items)

**HIGH**
| # | Feature | Description |
|---|---------|-------------|
| 55 | ~~`get_history()` preserves tool metadata~~ **DONE** | ~~Keeps `tool_calls`, `tool_call_id`, `name` — critical for multi-turn tool conversations.~~ **Fixed in `fix/upstream-sync` (2026-02-20)** |

**MEDIUM**
| # | Feature | Description |
|---|---------|-------------|
| 56 | Workspace-scoped sessions | Sessions in `workspace/sessions/` not `~/.nanobot/sessions/`. |
| 57 | Legacy session migration | Auto-migrates old sessions to workspace on first access. |
| 58 | ~~`last_consolidated` field on Session~~ **DONE** | ~~Persisted in JSONL metadata, used to avoid re-processing.~~ **Fixed in `fix/upstream-sync` (2026-02-20)** |

**LOW**
| # | Feature | Description |
|---|---------|-------------|
| 59 | `get_history()` default raised to 500 | Relies on consolidation not truncation. |
| 60 | ~~`invalidate()` method~~ **DONE** | ~~Evicts session from cache after `/new`.~~ **Fixed in `fix/upstream-sync` (2026-02-20)** |
| 61 | ~~`clear()` resets `last_consolidated`~~ **DONE** | ~~Housekeeping.~~ **Fixed in `fix/upstream-sync` (2026-02-20)** |
| 62 | Error filtering removed from `get_history()` | Upstream keeps all messages. We filter error prefixes. |

**N/A**
| # | Feature | Description | Keep ours? |
|---|---------|-------------|-----------|
| 63 | Simplified save (no atomic write) | Direct write, no tempfile. | YES — keep atomic writes |

---

## Summary

| Importance | Count | Key Items |
|-----------|-------|-----------|
| **HIGH** | ~~10~~ **7 remaining** | MCP wiring (5 items), `_strip_think()`, temperature/max_tokens. ~~tool metadata~~, ~~empty content~~, ~~provider matching~~ **DONE** |
| **MEDIUM** | ~~21~~ **18 remaining** | Consolidation improvements (4), provider wiring (4), progress helpers, CLI features, config fields. ~~last_consolidated~~, ~~invalidate()~~, ~~clear() reset~~ **DONE** |
| **LOW** | 15 | DRY refactors, cron timezone, onboard UX, etc. |
| **N/A** | 7 | Intentional divergences we keep (secrets split, atomic writes, document extraction, etc.) |
| **Total** | **63 (6 done, 57 remaining)** | |

## Post-V2: Project Rename — "Genesis"

The project has been renamed to **Genesis** (GitHub: `WingedGuardian/Genesis`). The following local changes are deferred to post-v2 to avoid disrupting the running system:

| Item | Current | Target | Notes |
|------|---------|--------|-------|
| Local directory | `~/executive-copilot/` | `~/genesis/` | Requires stopping gateway, other sessions |
| Venv | `~/executive-copilot/.venv` | `~/genesis/.venv` | Hardcoded paths in `activate`, `pyvenv.cfg` — recreate venv |
| Systemd service | `~/.config/systemd/user/nanobot-gateway.service` | Update `WorkingDirectory` + `ExecStart` paths | `daemon-reload` + restart |
| Hook scripts (4) | `PROJECT_DIR="/home/ubuntu/executive-copilot/nanobot"` | Update to `/home/ubuntu/genesis/nanobot` | `.claude/hooks/{session,cleanup,branch,file-edit}-guard.sh` |
| `.claude/settings.json` | Hook paths reference `executive-copilot` | Update all 5 hook command paths | |
| `.claude/settings.local.json` | Permission allowlist paths | Update git command paths | |
| `config.py` line 262 | `backup_dir: "/home/ubuntu/executive-copilot/backups"` | `/home/ubuntu/genesis/backups` | |
| `cycle.py` line 89 | Same backup_dir default | Same | |
| `scripts/seed_core_memories.py` | `sys.path` references old path | Update if re-running | Optional |
| Claude projects dir | `~/.claude/projects/-home-ubuntu-executive-copilot-nanobot/` | `~/.claude/projects/-home-ubuntu-genesis-nanobot/` | Rename dir + update internal path refs |

**Execution plan:** Stop gateway → close all Claude sessions → rename directory → fix all paths above → recreate venv → `daemon-reload` → restart gateway → verify.

**What stays unchanged permanently:** Python package name (`nanobot`), runtime data dir (`~/.nanobot/`), upstream remote (`HKUDS/nanobot`).

## What DID Merge Successfully

Provider improvements (json_repair, max_tokens clamp, new provider specs), new provider files (custom_provider.py, openai_codex_provider.py), MCP tool server client (file only), channel improvements (Feishu, Slack, Telegram), cron timezone fixes, docker-compose, and all new upstream tests.

See merge commit `181a2c9` for full details.

## Files We Kept As Ours (6 files)

| File | Our Changes | Their Changes | Merge Strategy |
|------|-------------|---------------|----------------|
| `nanobot/agent/loop.py` | Copilot hooks, routing, cost logging, slash commands (~1046L diff) | Progress streaming, MCP, json_repair, consolidation (~597L diff) | **DURING V2.1** — start from upstream base, re-apply hooks |
| `nanobot/cli/commands.py` | Copilot init, provider setup, dream scheduler (~1084L diff) | Codex OAuth, Custom provider, MCP wiring (~388L diff) | **DURING V2.1** — start from upstream base, re-apply hooks |
| `nanobot/agent/context.py` | Onboarding prompt, session metadata (~222L diff) | Empty content fix, updated bootstrap files (~37L diff) | **BEFORE V2.1** — cherry-pick #36 only |
| `nanobot/config/loader.py` | Secrets separation, deep merge (~203L diff) | Simplified loading with alias generator (~103L diff) | **AFTER V2.1** — adopt with Base alias model (#43) |
| `nanobot/config/schema.py` | CopilotConfig, llm_timeout, venice/nvidia (~48L diff) | MCPServerConfig, Base alias model, OAuth fields (~308L diff) | **BEFORE V2.1** (#42 only) + **AFTER V2.1** (#41, #43-46) |
| `nanobot/session/manager.py` | `/use` override lifecycle (~289L diff) | Workspace sessions, tool metadata, last_consolidated (~205L diff) | **BEFORE V2.1** — cherry-pick #55, #58, #60, #61 |
