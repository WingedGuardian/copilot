# Executive Co-Pilot: Project Review Summary
## Date: 2026-02-11
## Reviewer: Claude Code (Opus 4.6)
## Purpose: Findings and decisions from initial project review, for phase planning agent

---

## Infrastructure Status (Verified Live)

| Service | Status | Details |
|---------|--------|---------|
| QDrant | RUNNING (fixed) | v1.16.3, systemd service created and enabled, port 6333, storage at ~/storage |
| Redis | RUNNING | Port 6379, localhost only (not exposed externally) |
| LM Studio | RUNNING | http://192.168.50.100:1234/v1 on Windows PC (5070ti GPU) |
| SQLite | READY | data/sqlite/copilot.db with tables: approval_rules, cost_log, tasks |
| Nanobot | CLONED | HKUDS/nanobot at ~/executive-copilot/nanobot, dependencies installed |

## Network Topology (Canonical Source: NETWORKING SUMMARY)

- **Container** (ubuntu@claude-agent): Internal IP on Incus bridge (NOT directly LAN-reachable)
- **VM** (zorror@assistbot): IP 192.168.50.123, acts as port-forward gateway
  - 192.168.50.123:2222 -> Container:22 (SSH)
  - 192.168.50.123:6333 -> Container:6333 (QDrant)
- **Windows PC**: 192.168.50.100, LM Studio on :1234
- **Direction**: Container initiates all outbound connections. Nothing can push inbound without explicit port forwards.
- Redis is localhost-only inside container (not forwarded, not exposed).

## LM Studio Available Models

| Model | Size | Potential Role |
|-------|------|---------------|
| llama-3.2-3b-instruct | 3B | **Primary router (Sentry)** - fast classification, structured JSON |
| text-embedding-nomic-embed-text-v1.5 | ~137M | **Local embeddings** for QDrant - eliminates cloud embedding costs |
| phi-4-mini-reasoning | ~3.8B | Alternative router / reasoning tasks |
| mistral-small-3.2-24b-instruct | 24B | Local "medium" tier for specific use cases |
| huihui-qwen3-30b-a3b (MoE) | 30B (3B active) | Local "medium" tier, efficient MoE |
| dolphin3.0-r1-mistral-24b | 24B | Uncensored local option |
| openai-gpt-oss-20b-heretic | 20B | Alternative local option |

## Key Decisions Made

### 1. Model Routing Strategy
- **llama-3.2-3b-instruct**: Default Sentry router for intent classification (high frequency, low latency)
- **nomic-embed-text**: Use for local QDrant embeddings (cost saving vs cloud embeddings)
- **Larger local models (24B/30B)**: Available for specific use cases only, not default path
- **Cloud LLMs (OpenRouter/Venice/MiniMax)**: Primary destination for most actual work after routing
- **No API keys yet**: Test everything with LM Studio first; add cloud keys when the system is functional

### 2. Local LLM Configuration
- Use **OpenAI-compatible client** (NOT Ollama client) since LM Studio serves the OpenAI API format
- Env var names should follow the project outline: `LOCAL_LLM_BASE_URL`, `LOCAL_LLM_MODEL` (not OLLAMA_*)
- 5-second timeout is appropriate for the 3B router model
- Larger local models would need longer timeouts or a separate routing path if used

### 3. Infrastructure Approach
- **No Docker nesting** - services run directly as binaries/apt packages inside the Incus container
- QDrant: binary at /usr/local/bin/qdrant with systemd service (now fixed and enabled)
- Redis: installed via apt with systemd (already working)
- This is the simplest, most resource-efficient approach for a single-user personal tool

## Issues Requiring Attention in Phase Planning

### Issue 1: SQLite Schema Divergence
The Kimi setup guide created tables with a **different schema** than the project outline specifies:
- **Currently exists**: `approval_rules`, `cost_log`, `tasks` (from Kimi guide)
- **Outline specifies**: `tasks`, `routing_log`, `cost_tracking`, `approval_rules` (different columns and table names)
- **Decision needed**: Migrate to the outline schema during implementation. The `tasks` table columns differ (Kimi version has `checkpoint_tier`, `current_assignee`, `context_json`; outline has `route_attempted`, `thread_id`, `error_log`). Consider merging the best of both.

### Issue 2: .env File Inconsistency
- Current `.env` references `OLLAMA_BASE_URL` and `OLLAMA_MODEL_SENTRY`
- Should be updated to `LOCAL_LLM_BASE_URL=http://192.168.50.100:1234/v1` and `LOCAL_LLM_MODEL=llama-3.2-3b-instruct` per the project outline
- Cloud API keys are empty - this is fine for now, test with LM Studio

### Issue 3: Inbound Connectivity
- Container is behind NAT on Incus bridge - cannot receive inbound connections from LAN without port forwards
- Current forwards: SSH (2222) and QDrant (6333) only
- **Impact**: If any future feature requires webhooks or push notifications from external services, additional port forwards will be needed on the VM
- No action needed now, but the phase plan should account for this if adding webhook-dependent integrations

### Issue 4: QDrant Embedding Dimensions
- The project outline specifies 1024-dim dense vectors for QDrant
- nomic-embed-text-v1.5 produces 768-dim vectors by default (configurable up to 768)
- **Decision needed**: Set QDrant collection dimensions to match the actual embedding model output (768), not the outline's 1024

### Issue 5: Nanobot Already Has Key Infrastructure
The nanobot framework already provides:
- Skills system (loader, registry, SKILL.md convention)
- WhatsApp channel via Baileys bridge (Node.js)
- Multi-provider LLM support (OpenRouter, vLLM/local, and many others)
- Subagent/spawn system for background tasks
- Cron/heartbeat for scheduled work
- Memory system (workspace/memory/MEMORY.md)
- Tool layer (file ops, shell, web search, web fetch, messaging)

**Implication**: Many planned features should be built as **nanobot native skills** extending the existing framework, not as standalone modules. The phase plan should account for nanobot's existing capabilities to avoid reinventing what's already there.

## What the Nanobot Config Will Need

The nanobot config at `~/.nanobot/config.json` should be set up with:
- **vllm provider** pointing to `http://192.168.50.100:1234/v1` for local LM Studio inference
- **openrouter provider** (once API key is available) for cloud routing
- **WhatsApp channel** enabled with allowFrom restriction
- Custom skills registered for: sentry_router, memory_manager, etc.

## File Locations Reference

| Item | Path |
|------|------|
| Project root | ~/executive-copilot/nanobot |
| Python venv | ~/executive-copilot/.venv |
| SQLite DB | ~/executive-copilot/nanobot/data/sqlite/copilot.db |
| QDrant storage | ~/storage |
| QDrant service | /etc/systemd/system/qdrant.service |
| Nanobot config | ~/.nanobot/config.json |
| Project outline | ~/.claude/projects/-home-ubuntu-executive-copilot-nanobot/EXECUTIVE CO-PILOT Project outline.txt |
| Networking doc | ~/.claude/projects/-home-ubuntu-executive-copilot-nanobot/NETWORKING SUMMARY FOR CLAUDE CODE.txt |
