# Plan v1 (REVISED) — Foundation Setup: Nanobot Config, LM Studio Link & WhatsApp Bridge

## Revision Notes
This replaces the original Plan v1 which had several incorrect assumptions:
- ~~SSH tunnel~~ → Direct LAN connection (container reaches LM Studio at 192.168.50.100:1234 natively)
- ~~Custom WhatsApp bridge~~ → Nanobot's built-in WhatsApp channel via Baileys
- ~~Generate on Windows, SCP to VM~~ → We are inside the Incus container, write files directly
- ~~Custom LM Studio client~~ → Nanobot's vllm provider (OpenAI-compatible) for general LLM calls
- Removed prompt injection from external planning tool

## Observations

Nanobot (HKUDS/nanobot v0.1.3) already provides the key infrastructure we need:
- **Provider system**: LiteLLM-based, supports vLLM (any OpenAI-compatible server) via `providers.vllm` config
- **WhatsApp channel**: Built-in Baileys bridge, auto-builds Node.js bridge at `~/.nanobot/bridge/`
- **Skills system**: SKILL.md convention with YAML frontmatter, progressive loading, workspace override
- **Agent loop**: Async tool-calling loop with up to 20 iterations per message
- **Session management**: JSONL persistence at `~/.nanobot/sessions/`, keyed by `channel:chat_id`
- **Message bus**: Decoupled async queues between channels and agent

Phase 1 goal: Get nanobot talking to LM Studio and responding on WhatsApp — the minimum viable loop.

## Infrastructure Status (Verified 2026-02-11)

| Service | Status | Endpoint |
|---------|--------|----------|
| QDrant | Running (systemd) | http://localhost:6333 |
| Redis | Running (systemd) | redis://localhost:6379 |
| LM Studio | Running (Windows PC) | http://192.168.50.100:1234/v1 |
| SQLite | Ready | data/sqlite/copilot.db |

## Implementation Steps

### Step 1: Create/Update nanobot config.json

**File: `~/.nanobot/config.json`**

Configure nanobot to use LM Studio as its LLM provider via the built-in `vllm` provider type (which connects to any OpenAI-compatible server).

```json
{
  "providers": {
    "vllm": {
      "apiKey": "lm-studio",
      "apiBase": "http://192.168.50.100:1234/v1"
    }
  },
  "agents": {
    "defaults": {
      "model": "llama-3.2-3b-instruct",
      "maxTokens": 2048,
      "temperature": 0.7,
      "maxToolIterations": 10
    }
  },
  "channels": {
    "whatsapp": {
      "enabled": true,
      "allowFrom": []
    }
  }
}
```

**Notes:**
- `apiKey` must be non-empty (LiteLLM requires it) but value doesn't matter for LM Studio
- `apiBase` points directly to LM Studio on the Windows PC over LAN — no tunnel
- `model` must match the model ID as served by LM Studio: `llama-3.2-3b-instruct`
- `allowFrom` empty = accept all senders initially (restrict to user's phone number after testing)
- The vllm provider in nanobot's registry will prefix the model as `hosted_vllm/llama-3.2-3b-instruct` for LiteLLM routing

### Step 2: Create .env file with correct variable names

**File: `/home/ubuntu/executive-copilot/nanobot/.env`**

```bash
# LM Studio (Windows PC, direct LAN access)
LOCAL_LLM_BASE_URL=http://192.168.50.100:1234/v1
LOCAL_LLM_MODEL=llama-3.2-3b-instruct
LOCAL_LLM_TIMEOUT=5

# Infrastructure (all localhost inside container)
QDRANT_URL=http://localhost:6333
REDIS_URL=redis://localhost:6379/0
DATABASE_URL=sqlite:///data/sqlite/copilot.db

# Cloud LLM providers (fill in when ready)
OPENROUTER_API_KEY=
VENICE_API_KEY=
MINIMAX_API_KEY=

# Embedding model (local via LM Studio)
EMBEDDING_MODEL=text-embedding-nomic-embed-text-v1.5
EMBEDDING_BASE_URL=http://192.168.50.100:1234/v1

# Cost tracking
DAILY_COST_ALERT_THRESHOLD=50.00
```

**Notes:**
- These env vars are for our custom skills (Sentry Router, memory manager, etc. in later phases)
- Nanobot's own config is driven by `~/.nanobot/config.json`, not .env
- The .env file serves our custom code that will extend nanobot

### Step 3: Test nanobot agent with LM Studio

Verify the LM Studio connection works via nanobot's CLI:

```bash
cd ~/executive-copilot/nanobot
source ~/executive-copilot/.venv/bin/activate
nanobot agent -m "Hello, what model are you?"
```

**Expected**: Response from llama-3.2-3b-instruct via LM Studio.

**If this fails**, check:
1. LM Studio is serving and model is loaded: `curl http://192.168.50.100:1234/v1/models`
2. Config is valid JSON: `python -c "import json; json.load(open('/home/ubuntu/.nanobot/config.json'))"`
3. Provider resolution: nanobot should detect `vllm` provider and prefix model as `hosted_vllm/llama-3.2-3b-instruct`

### Step 4: Set up WhatsApp channel

Use nanobot's built-in WhatsApp bridge:

```bash
# This builds the Node.js Baileys bridge at ~/.nanobot/bridge/ and shows a QR code
nanobot channels login
```

**Process:**
1. Nanobot copies the bundled Baileys bridge to `~/.nanobot/bridge/`
2. Runs `npm install` and `npm run build` automatically
3. Starts the bridge and displays a QR code in terminal
4. Scan QR code with WhatsApp mobile app → Settings → Linked Devices → Link a Device
5. Once linked, the session is persisted at `~/.nanobot/bridge/auth_info/`

**Note:** The WhatsApp bridge connects via WebSocket to the Node.js Baileys server on `ws://localhost:3001` (default). This is all internal to the container.

### Step 5: Start the gateway

In a separate terminal (or tmux session):

```bash
cd ~/executive-copilot/nanobot
source ~/executive-copilot/.venv/bin/activate
nanobot gateway
```

**This starts:**
- Agent loop (listens on message bus)
- WhatsApp channel (connects to Baileys bridge)
- Cron service (job scheduler)
- Heartbeat service (30-minute background prompts)

**Test:** Send a WhatsApp message from your phone → should get a response from llama-3.2-3b-instruct.

### Step 6: Restrict WhatsApp to your phone number

After verifying it works, update `~/.nanobot/config.json` to restrict access:

```json
{
  "channels": {
    "whatsapp": {
      "enabled": true,
      "allowFrom": ["YOUR_PHONE_NUMBER"]
    }
  }
}
```

Phone number format: Check nanobot gateway logs to see how your number appears (e.g., `1234567890` or `+1234567890` or a LID).

### Step 7: Create workspace skill stubs for future phases

Create custom skill directories at `~/.nanobot/workspace/skills/` for the Executive Co-Pilot components that will be built in Phases 2-8:

**File: `~/.nanobot/workspace/skills/sentry-router/SKILL.md`**
```markdown
---
name: sentry-router
description: "Intelligent local/cloud routing with overflow protection and confidence scoring."
metadata: {"nanobot": {"emoji": "🛡️"}}
---
# Sentry Router
Phase 2 — Not yet implemented.
```

**File: `~/.nanobot/workspace/skills/memory-manager/SKILL.md`**
```markdown
---
name: memory-manager
description: "Tiered memory: Redis (working) + QDrant (episodic) + SQLite (procedural)."
metadata: {"nanobot": {"emoji": "🧠"}}
---
# Memory Manager
Phase 4 — Not yet implemented.
```

**File: `~/.nanobot/workspace/skills/status/SKILL.md`**
```markdown
---
name: status
description: "System status dashboard: LM Studio health, queue size, memory usage, costs."
metadata: {"nanobot": {"emoji": "📊"}}
---
# Status
Phase 6 — Not yet implemented.
```

These stubs make the skills visible in nanobot's skill list, establishing the structure for later phases to fill in.

### Step 8: Verify end-to-end

Run the following checklist:

- [ ] `nanobot status` — shows vllm provider configured
- [ ] `nanobot agent -m "Say hello"` — gets response from LM Studio
- [ ] `nanobot channels status` — shows WhatsApp enabled + connected
- [ ] Send WhatsApp message → receive reply within reasonable time
- [ ] `curl http://localhost:6333/healthz` — QDrant healthy (ready for Phase 4)
- [ ] `redis-cli ping` — PONG (ready for Phase 4)
- [ ] `sqlite3 ~/executive-copilot/nanobot/data/sqlite/copilot.db ".tables"` — shows tables (ready for Phase 3)

## What This Phase Does NOT Do

These are explicitly deferred to later phases:
- **Sentry Router** (Phase 2): Intelligent routing with structured JSON, confidence scoring, overflow protection
- **Task queue** (Phase 3): SQLite-backed persistent task queue with worker loop
- **Memory layer** (Phase 4): QDrant + Redis + SQLite tiered memory
- **Cloud LLM failover** (Phase 2+): OpenRouter/Venice/MiniMax integration (needs API keys)
- **Tool layer / MCP** (Phase 5): AWS, Playwright, Git, Proxmox API tools
- **Approval system** (Phase 7): Dynamic rules, spend thresholds
- **Dream cycle** (Phase 8): Nightly maintenance, cost analytics, backup

## Files Created/Modified Summary

| File | Action | Purpose |
|------|--------|---------|
| `~/.nanobot/config.json` | Create/Update | Nanobot config with vllm provider + WhatsApp |
| `~/executive-copilot/nanobot/.env` | Update | Env vars for custom skills (later phases) |
| `~/.nanobot/workspace/skills/sentry-router/SKILL.md` | Create | Stub for Phase 2 |
| `~/.nanobot/workspace/skills/memory-manager/SKILL.md` | Create | Stub for Phase 4 |
| `~/.nanobot/workspace/skills/status/SKILL.md` | Create | Stub for Phase 6 |

## Architecture After Phase 1

```
WhatsApp (Phone)
    ↓ Baileys protocol
Baileys Bridge (Node.js, ws://localhost:3001)
    ↓ WebSocket
Nanobot WhatsApp Channel
    ↓ InboundMessage
Message Bus (async queue)
    ↓
Agent Loop
    ↓ OpenAI-compatible API call
LM Studio (http://192.168.50.100:1234/v1)
    ↓ llama-3.2-3b-instruct response
Agent Loop
    ↓ OutboundMessage
Message Bus → WhatsApp Channel → Baileys → Phone
```

## Known Limitations After Phase 1

1. **All messages go to llama-3.2-3b** — no routing intelligence yet (Phase 2)
2. **No memory persistence** — sessions stored as JSONL but no vector/semantic memory (Phase 4)
3. **No cloud fallback** — if LM Studio/Windows PC is off, messages will fail (Phase 2)
4. **4K context limit** — llama-3.2-3b has a 4096 token context window; long conversations will degrade (Phase 2 overflow protection)
5. **No cost tracking** — all inference is local/free for now (Phase 3+)
