# MCP Activation, YouTube Tool, Escalation Fix

**Date:** 2026-02-22
**Branch:** `feat/mcp-youtube-escalation`
**Status:** Implementation complete, tests passing

## What Changed

### 1. MCP Infrastructure Activated (`config.py`, `commands.py`)
- Added `mcp_servers: dict[str, dict]` to CopilotConfig
- Wired `McpManager` (from `nanobot/agent/mcp/`) into gateway startup
- MCP connection happens inside the async `run()` function (not synchronous bootstrap) so subprocess handles remain valid for the gateway's lifetime
- Health loop starts after connection, disconnect happens during shutdown
- Note: There are TWO MCP implementations — custom (`agent/mcp/`) and upstream SDK (`agent/tools/mcp.py`). We use the custom one because it has AlertBus integration, auto-reconnect, and health loops.

### 2. YouTube Transcription Tool (`agent/tools/youtube.py`, `agent/loop.py`)
- New native tool `youtube_transcript` registered in `_register_default_tools()`
- Two-tier fallback: TranscriptAPI (API key from `secrets.json` at `providers.transcriptapi.apiKey`) -> yt-dlp subprocess
- Resolves shortened URLs (search.app, youtu.be) via httpx redirect following
- VTT parsing with deduplication for yt-dlp output
- Uses `asyncio.create_subprocess_exec` (not shell) for yt-dlp — safe arg passing

### 3. Escalation System Overhauled (`routing/router.py`)
- **Injection scope fixed:** `_inject_escalation` now fires for `local`, `default`, and `plan` targets (was `local` only)
- **Two-tier escalation:** Default model -> escalation model -> strongest model (if configured)
- **New config field:** `strongest_model: str = ""` — empty means no tier-2
- **Improved prompt:** `_ESCALATION_INSTRUCTION` now has concrete behavioral signals (tool failures, multi-step tasks, confidence checks) instead of vague "complex reasoning"
- **Safety net for escalation chains:** Removed early `return` in `_build_chain()` for escalation/strongest targets — these chains now get the mandatory safety net (last-known-working, LM Studio, emergency)
- **Strongest model in `set_model()`:** Added "strongest" to the tier mapping for runtime hot-swap

### 4. AGENTS.md Updated (`workspace/AGENTS.md`)
- Added `youtube_transcript` to Tools Available section
- Added Self-Escalation subsection under Routing System with behavioral guidance

### 5. Test Updates (`tests/copilot/routing/`)
- Updated `test_escalation_chain_uses_escalation_model` and `test_escalation_chain_is_separate` to account for safety net being appended to escalation chains
- All 108 affected tests pass (11 MCP + 97 routing integration + 10 chain)

## Config Example

```json
{
  "copilot": {
    "mcp_servers": {
      "playwright": {
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@playwright/mcp@latest"]
      }
    },
    "strongest_model": "anthropic/claude-opus-4-6"
  }
}
```

## Files Modified

| File | Lines Changed | What |
|------|--------------|------|
| `nanobot/copilot/config.py` | +5 | `mcp_servers` + `strongest_model` fields |
| `nanobot/cli/commands.py` | +22 | MCP startup/shutdown, `strongest_model` passthrough |
| `nanobot/agent/tools/youtube.py` | +175 (new) | YouTube transcription tool |
| `nanobot/agent/loop.py` | +3 | Import + register YouTube tool |
| `nanobot/copilot/routing/router.py` | ~60 changed | Two-tier escalation, injection scope, improved prompt, safety net |
| `workspace/AGENTS.md` | +8 | YouTube tool + escalation guidance |
| `tests/copilot/routing/test_chain.py` | +5 | Updated escalation chain test |
| `tests/copilot/routing/test_routing_integration.py` | +7 | Updated escalation chain test |

## Decisions Made

1. **Used custom McpManager over upstream SDK** — better lifecycle management for long-running gateway
2. **MCP connection in async context** — subprocess handles must live in same event loop as gateway
3. **TranscriptAPI key in secrets.json** — follows existing pattern for external service keys
4. **Escalation instruction for ALL non-private targets** — MiniMax (default) was the whole reason for this fix
5. **Safety net on escalation chains** — the early `return` was a bug that left escalation calls without fallbacks
