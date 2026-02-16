# Phase 1 Setup Complete — WhatsApp Integration

## ✅ What's Been Configured

1. **Nanobot config** (`~/.nanobot/config.json`)
   - vllm provider pointing to LM Studio at `http://192.168.50.100:1234/v1`
   - Default model: `microsoft/phi-4-mini-reasoning` (works with tools)
   - WhatsApp channel enabled
   - Max tool iterations: 10 (reduced from default 20)
   - Max tokens: 2048 (appropriate for local 3-4B models)

2. **Environment variables** (`.env`)
   - LOCAL_LLM_BASE_URL, LOCAL_LLM_MODEL, LOCAL_LLM_TIMEOUT
   - QDRANT_URL, REDIS_URL, DATABASE_URL
   - EMBEDDING_MODEL (nomic-embed-text-v1.5)
   - Placeholders for cloud API keys (OPENROUTER, VENICE, MINIMAX)

3. **Custom skills** (`~/.nanobot/workspace/skills/`)
   - `sentry-router` (Phase 2 stub)
   - `memory-manager` (Phase 4 stub)
   - `status` (Phase 6 stub)

4. **Verified working**
   - QDrant running on port 6333
   - Redis running on port 6379
   - LM Studio accessible at 192.168.50.100:1234
   - Nanobot agent CLI responds with phi-4-mini-reasoning

## 🚀 Next Steps: WhatsApp Setup

### Step 1: Start the WhatsApp Bridge

In a terminal/tmux session:

```bash
cd ~/executive-copilot/nanobot
source ~/executive-copilot/.venv/bin/activate
nanobot channels login
```

**What this does:**
1. Copies Baileys bridge to `~/.nanobot/bridge/`
2. Runs `npm install` and `npm run build` automatically
3. Starts the bridge and displays a QR code
4. Waits for you to scan

**Scan the QR code:**
- Open WhatsApp on your phone
- Tap Menu (⋮) → Linked Devices
- Tap "Link a Device"
- Scan the QR code shown in terminal

**Once linked:**
- The session is saved at `~/.nanobot/bridge/auth_info/`
- Press Ctrl+C to stop (the session persists)

### Step 2: Start the Gateway

In a **separate** terminal/tmux session:

```bash
cd ~/executive-copilot/nanobot
source ~/executive-copilot/.venv/bin/activate
nanobot gateway
```

**What this starts:**
- Agent loop (processes messages)
- WhatsApp channel (connects to Baileys bridge)
- Cron service (scheduled tasks)
- Heartbeat service (30-minute background prompts)

**Keep this running.** Use tmux to detach: `Ctrl+B` then `D`

### Step 3: Test End-to-End

1. Send a WhatsApp message to the number you linked
2. You should get a response from phi-4-mini-reasoning via LM Studio
3. Check the gateway terminal for logs

### Step 4: Restrict Access (Recommended)

After verifying it works, update `~/.nanobot/config.json` to restrict to your phone number:

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

**To find your phone number format:**
- Check the gateway logs when you send a message
- Look for the sender ID format (e.g., `1234567890` or `+1234567890@s.whatsapp.net`)
- Use just the numeric part without `@s.whatsapp.net`

Then restart the gateway (Ctrl+C and run `nanobot gateway` again).

## 📊 Verification Checklist

After setup, verify:

- [ ] `nanobot status` — shows vllm provider configured
- [ ] `nanobot agent -m "Hello"` — gets response from LM Studio (phi-4)
- [ ] `nanobot channels status` — shows WhatsApp enabled + connected
- [ ] Send WhatsApp message → receive reply
- [ ] `curl http://localhost:6333/healthz` — QDrant healthy
- [ ] `redis-cli ping` — PONG
- [ ] `sqlite3 ~/executive-copilot/nanobot/data/sqlite/copilot.db ".tables"` — shows tables

## 🔧 Troubleshooting

### WhatsApp QR code not appearing
- Check Node.js version: `node --version` (must be ≥17)
- Check bridge logs in `~/.nanobot/bridge/` directory
- Make sure port 3001 is not in use: `netstat -tulpn | grep 3001`

### Gateway fails to start
- Check config is valid JSON: `python -c "import json; json.load(open('/home/ubuntu/.nanobot/config.json'))"`
- Verify LM Studio is running: `curl http://192.168.50.100:1234/v1/models`

### No response to WhatsApp messages
- Check gateway logs for errors
- Verify bridge is running: `ps aux | grep node`
- Check WebSocket connection: `netstat -tulpn | grep 3001`

### LM Studio timeout
- Windows PC might be asleep or off
- Check firewall on Windows allows port 1234
- Test direct connection: `curl http://192.168.50.100:1234/v1/models`

## 📝 Model Selection Notes

**phi-4-mini-reasoning vs llama-3.2-3b-instruct:**

- **phi-4** is the general agent model (Phase 1+)
  - Works with nanobot's tool-calling system
  - ~3.8B parameters, good reasoning capability
  - Use for general WhatsApp conversations

- **llama-3.2-3b** is for Sentry Router only (Phase 2)
  - Configured in LM Studio with structured output preset
  - Cannot handle tools + structured output simultaneously
  - Will be called directly (without tools) for routing decisions
  - Returns JSON: `{confidence, route, reason, estimated_complexity}`

Other available models for future use:
- `mistral-small-3.2-24b-instruct` (24B, for complex local queries)
- `huihui-qwen3-30b-a3b-instruct` (30B MoE, efficient larger model)
- `text-embedding-nomic-embed-text-v1.5` (for QDrant embeddings in Phase 4)

## 🎯 What Phase 1 Does NOT Do (Deferred to Later Phases)

- **Sentry Router** (Phase 2): Intelligent routing, structured JSON, confidence scoring — ✅ Done
- **Task queue** (Phase 3): SQLite-backed persistent queue with worker loop — ✅ Done
- **Memory layer** (Phase 4): QDrant + Redis + SQLite tiered memory — ✅ Done
- **Cloud LLM failover** (Phase 2+): OpenRouter/Venice/MiniMax — ✅ Done
- **Tool layer / MCP** (Phase 5): AWS, Playwright, Git, Proxmox tools — Deferred to V2
- **Approval system** (Phase 7): Built, encountered deadlocks, removed. Replaced with POLICY.md guardrails.
- **Dream cycle** (Phase 8): Nightly maintenance, cost analytics, backup — ✅ Done

Phase 1 establishes the foundation: nanobot ↔ LM Studio ↔ WhatsApp works end-to-end.

## 🔄 Using tmux for Persistent Sessions

Recommended tmux workflow:

```bash
# Create WhatsApp bridge session
tmux new -s whatsapp
# (You're now in the session)
cd ~/executive-copilot/nanobot
source ~/executive-copilot/.venv/bin/activate
nanobot channels login
# Scan QR code, wait for "Connected"
# Detach: Ctrl+B then D

# Create gateway session
tmux new -s gateway
cd ~/executive-copilot/nanobot
source ~/executive-copilot/.venv/bin/activate
nanobot gateway
# Detach: Ctrl+B then D

# Reattach to either session
tmux attach -t whatsapp
tmux attach -t gateway

# List sessions
tmux ls

# Kill a session
tmux kill-session -t whatsapp
```

Both sessions will persist even if you disconnect from SSH.

---

**Phase 1 is complete.** You now have a working foundation for the Executive Co-Pilot project.
