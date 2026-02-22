# nanobot-copilot

**Executive AI copilot extensions for the [nanobot](https://github.com/HKUDS/nanobot) framework.**

A fork of nanobot that adds autonomous cognitive capabilities: hybrid memory (Qdrant + SQLite FTS5), intelligent model routing with failover, a nightly dream cycle for self-maintenance, task management with peer review, cost tracking, and more.

---

## What This Adds to Nanobot

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
- **Metacognition** — Confidence-based lesson manager with decay and reinforcement
- **Structured Extraction** — Background fact extraction with SLM-to-cloud fallback cascade
- **SLM Work Queue** — SQLite-backed durable async queue with dedup and priority
- **Health Monitoring** — Programmatic HTTP pings, DB queries, and self-heal escalation
- **Status Dashboard** — Unified system health aggregator accessible via `/status`
- **Web UI** — Task management, file browser, cost dashboard, secrets management

---

## Installation

```bash
# Clone this repo
git clone https://github.com/WingedGuardian/copilot.git
cd copilot

# Create virtual environment
python -m venv .venv && source .venv/bin/activate

# Install
pip install -e .
```

### Prerequisites
- Python 3.11+
- [Qdrant](https://qdrant.tech/) running locally (for memory system)
- At least one LLM provider API key

### Configuration

1. Copy the secrets template:
```bash
cp secrets.json.template ~/.nanobot/secrets.json
```

2. Edit `~/.nanobot/secrets.json` with your API keys:
```json
{
  "providers": {
    "openrouter": { "apiKey": "sk-or-..." },
    "anthropic": { "apiKey": "sk-ant-..." }
  }
}
```

3. Start nanobot:
```bash
nanobot
```

---

## Architecture

```
nanobot/
  agent/          # Core agent loop, tools, MCP, safety (upstream)
  channels/       # Chat integrations: Telegram, Discord, WhatsApp, etc. (upstream)
  copilot/        # === COPILOT EXTENSIONS (this fork) ===
    alerting/     #   Severity-aware alert bus
    context/      #   Extended context builder
    cost/         #   Token tracking, budget enforcement
    dream/        #   Dream cycle, heartbeat, health check, monitor
    extraction/   #   Structured fact extraction
    memory/       #   Qdrant + FTS5 hybrid memory
    metacognition/#   Lesson manager
    routing/      #   RouterProvider V2
    slm_queue/    #   Durable async work queue
    status/       #   System health dashboard
    tasks/        #   Task management + navigator duo
    tools/        #   Extended tool definitions
  providers/      # LLM provider integrations (upstream)
  web/            # Web UI routes and templates
```

### Identity Files

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

This is a fork of [HKUDS/nanobot](https://github.com/HKUDS/nanobot). All upstream nanobot features (multi-platform chat, CLI, MCP support, skills system) are preserved. The copilot extensions are additive — they hook into the agent loop without modifying upstream code.

---

## License

MIT — same as upstream nanobot.
