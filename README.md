<div align="center">
  <h1>Copilot</h1>
  <p><strong>Executive AI copilot extensions for the nanobot framework.</strong></p>
  <p>
    <img src="https://img.shields.io/badge/python-≥3.11-blue" alt="Python">
    <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
    <a href="https://github.com/HKUDS/nanobot"><img src="https://img.shields.io/badge/upstream-nanobot_v0.1.4-orange" alt="Upstream: nanobot"></a>
  </p>
</div>

A fork of [nanobot](https://github.com/HKUDS/nanobot) that adds autonomous cognitive capabilities: hybrid memory (Qdrant + SQLite FTS5), intelligent model routing with failover, a nightly dream cycle for self-maintenance, task management with peer review, cost tracking, and more.

---

## Quick Start

```bash
# Clone
git clone https://github.com/WingedGuardian/copilot.git
cd copilot

# Run setup (creates ~/.nanobot/, copies templates, installs deps)
bash scripts/setup.sh

# Add your API keys
nano ~/.nanobot/secrets.json

# Configure providers and channels
nano ~/.nanobot/config.json

# Start
nanobot
```

The web UI will be available at `http://localhost:18790`.

**Prerequisites:** Python 3.11+, at least one LLM provider API key. Qdrant required for memory features (copilot mode).

---

## What This Adds

### Hybrid Memory System

Qdrant vector search + SQLite FTS5 full-text search, fused via Reciprocal Rank Fusion with multi-factor scoring (recency, relevance, importance, access frequency). The agent remembers conversations, extracts structured facts, and proactively recalls relevant context.

### Intelligent Model Routing

RouterProvider V2 with circuit breaker pattern, self-escalation (agent retries with a more capable model when it recognizes its limits), and multi-provider failover chains. Supports local models (LM Studio), cloud providers, and automatic degradation.

### Dream Cycle

13-job nightly maintenance cycle: memory consolidation, cost reporting, lesson review, database backup, health monitoring, vector cleanup, routing preference pruning, budget checks, metacognitive reflection, identity evolution, observation management, and codebase indexing.

### Cognitive Heartbeat

Proactive 2-hour wake cycle with observation-driven task execution, autonomy permissions, and morning briefings.

### Task Management

LLM-powered task decomposition (2-8 steps), navigator duo peer review (plan review + execution review), and post-task retrospectives stored in memory for future learning.

### Cost Tracking & Alerting

Per-model token tracking, configurable budget enforcement, and a severity-aware AlertBus with deduplication and cooldown.

### Additional Systems

| System | Description |
|--------|-------------|
| **Metacognition** | Confidence-based lesson manager with decay and reinforcement |
| **Structured Extraction** | Background fact extraction with SLM-to-cloud fallback cascade |
| **SLM Work Queue** | SQLite-backed durable async queue with dedup and priority |
| **Health Monitoring** | Programmatic HTTP pings, DB queries, and self-heal escalation |
| **Status Dashboard** | Unified system health aggregator accessible via `/status` |
| **Web UI** | Task management, file browser, cost dashboard, secrets management |

---

## Configuration

All runtime config lives in `~/.nanobot/` (not in the repo):

| File | Purpose |
|------|---------|
| `config.json` | Providers, channels, copilot settings, gateway config |
| `secrets.json` | API keys, tokens, passwords (mode 600) |

Templates are in the repo root: `config.json.template` and `secrets.json.template`. The setup script copies these automatically.

The config loader merges `secrets.json` on top of `config.json` at startup. API keys in config.json are extracted to secrets.json on save.

### Minimal config (one provider)

**config.json:**
```json
{
  "agents": { "defaults": { "model": "gpt-4o" } },
  "providers": { "openai": { "defaultModel": "gpt-4o" } }
}
```

**secrets.json:**
```json
{
  "providers": { "openai": { "apiKey": "sk-..." } }
}
```

### Copilot mode

Set `copilot.enabled: true` in config.json for cognitive features:
- Episodic memory (requires [Qdrant](https://qdrant.tech/documentation/quick-start/))
- Dream cycle (nightly memory consolidation)
- Health checks and monitoring
- Multi-model routing with automatic failover
- Weekly/monthly strategic reviews

See `config.json.template` for all copilot settings.

---

## Channels

Enable channels in `config.json`, add tokens in `secrets.json`:

| Channel | Config key | Requires |
|---------|-----------|----------|
| WhatsApp | `channels.whatsapp` | WhatsApp bridge (`bridge/`) |
| Telegram | `channels.telegram` | Bot token from @BotFather |
| Discord | `channels.discord` | Bot token + gateway intents |
| Slack | `channels.slack` | Bot + app tokens |
| Email | `channels.email` | IMAP/SMTP credentials |

---

## Architecture

```
nanobot/
  agent/           # Core agent loop, tools, MCP, safety (upstream)
  channels/        # Chat integrations: Telegram, Discord, WhatsApp... (upstream)
  copilot/         # -- COPILOT EXTENSIONS (this fork) --
    alerting/      #   Severity-aware alert bus
    context/       #   Extended context builder
    cost/          #   Token tracking, budget enforcement
    dream/         #   Dream cycle, heartbeat, health check, monitor
    extraction/    #   Structured fact extraction
    memory/        #   Qdrant + FTS5 hybrid memory
    metacognition/ #   Lesson manager
    routing/       #   RouterProvider V2
    slm_queue/     #   Durable async work queue
    status/        #   System health dashboard
    tasks/         #   Task management
    tools/         #   Extended tool definitions
  providers/       # LLM provider integrations (upstream)
  web/             # Web UI routes and templates
data/copilot/      # Runtime identity files
workspace/         # Runtime workspace (SOUL.md, MEMORY.md, etc.)
bridge/            # WhatsApp bridge (Node.js)
scripts/           # Setup and utility scripts
```

## Identity Files

The agent's behavior is configured through markdown identity files in `data/copilot/`:

| File | Purpose |
|------|---------|
| `heartbeat.md` | Cognitive heartbeat task instructions |
| `dream.md` | Dream cycle job definitions |
| `weekly.md` | Weekly review — MANAGER role |
| `monthly.md` | Monthly review — DIRECTOR role |
| `recon.md` | AI landscape reconnaissance |
| `router.md` | Model routing logic |
| `navigator.md` | Navigator duo peer review |
| `models.md` | Available model registry |

Runtime workspace files (`SOUL.md`, `USER.md`, `MEMORY.md`, etc.) are created in `~/.nanobot/workspace/` on first run.

---

## Upstream

This is a fork of [HKUDS/nanobot](https://github.com/HKUDS/nanobot). All upstream features (multi-platform chat, CLI, MCP support, skills system) are preserved. The copilot extensions are additive — they hook into the agent loop without modifying upstream code.

---

<p align="center"><sub>MIT License — same as upstream nanobot.</sub></p>
