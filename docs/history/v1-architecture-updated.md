# Executive Co-Pilot V1: Architecture (Updated Feb 2026)

> **⚠️ STALE SECTIONS**: Three major systems described below were deleted after this doc was last updated. See CHANGELOG.md for current state.
> - **Approval System** — deleted 2026-02-15 (LLM-first principle: code shouldn't override LLM judgment)
> - **Redis Working Memory** (`memory/working.py`) — deleted 2026-02-19 (Redis dependency removed)
> - **Heuristic routing** (`classify()`, tier-based) — replaced by Router V2 (plan-based routing via `PlanRoutingTool`) 2026-02-20
> - **Dream cycle**: doc says "7 nightly jobs" — actual count is 13 (Sentience Plan added jobs 10-13)
>
> This document reflects the actual state of the system as built, not the original plan.

---

## Overview

A personal autonomous assistant accessible via WhatsApp (and 9 other channels), built by extending nanobot with an integrated copilot layer that handles intelligent routing, tiered context management, memory, self-improvement, approvals, tools, and proactive background tasks.

**Interface**: WhatsApp (primary), Telegram, Discord, Slack, Email, Feishu, DingTalk, QQ, MoChat, CLI
**Foundation**: nanobot (HKUDS, ~3.6K core lines, MIT license) — modified with thin hooks
**Intelligence**: Copilot modules in `nanobot/copilot/` wired into the agent loop
**Philosophy**: Reduce the user's burden, never add to it. Automate the "how." Escalate only when genuinely uncertain or high-stakes.

---

## What Changed from the Original Plan

The original V1 architecture described a **separate FastAPI proxy** at `localhost:5001` sitting between nanobot and LLMs. This was abandoned in favor of **direct integration** — copilot modules live inside the nanobot package and hook into the agent loop via thin injection points. This eliminated an entire service, reduced latency, and simplified deployment.

| Original Plan | What Was Built |
|---|---|
| Separate FastAPI proxy at :5001 | Integrated copilot modules in `nanobot/copilot/` |
| Nanobot kept stock/unmodified | Nanobot modified with ~200 lines of hooks across 5 files |
| LiteLLM → proxy → LLM | RouterProvider replaces LiteLLM directly |
| OpenRouter + Venice + MiniMax | OpenRouter + Venice + Nvidia NIM + 30 providers via registry |
| 7 phases sequential | All phases scaffolded, core features of 1-8 implemented |
| Redis for working memory | Redis connected, async with auto-reconnect |
| QDrant for episodic memory | QDrant connected, multi-factor scoring, hybrid search |

---

## System Architecture (As Built)

```
WhatsApp / Telegram / Discord / Slack / Email / CLI / ...
    ↓ Channel Manager (nanobot/channels/manager.py)
    ↓ InboundMessage via MessageBus
AgentLoop (nanobot/agent/loop.py)
    ↓
┌──────────────────────────────────────────────────────┐
│  COPILOT LAYER (nanobot/copilot/)                    │
│                                                      │
│  ┌──────────────────────────────────────────────┐    │
│  │  MAIN FLOW (every request)                   │    │
│  │  1. Slash command check (/onboard /profile)  │    │
│  │  2. Approval pending? → handle response      │    │
│  │  3. Satisfaction signal check (regex)         │    │
│  │  4. Fetch relevant lessons                   │    │
│  │  5. Build context (tiered + identity docs)   │    │
│  │  6. Route → RouterProvider (heuristics)      │    │
│  │  7. LLM call with failover chain             │    │
│  │  8. Self-escalation check ([ESCALATE])       │    │
│  │  9. Approval gate on tool calls              │    │
│  │ 10. Log routing, cost, outcome               │    │
│  └──────────────────────────────────────────────┘    │
│                                                      │
│  ┌──────────────────────────────────────────────┐    │
│  │  BACKGROUND SLM (async, after each exchange) │    │
│  │  - Extract facts/decisions/constraints (JSON) │    │
│  │  - Sentiment detection                        │    │
│  │  - Token accumulation monitoring              │    │
│  │  - Never blocks main flow                     │    │
│  └──────────────────────────────────────────────┘    │
│                                                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐     │
│  │ Router   │ │ Context  │ │ Approval System  │     │
│  │Provider  │ │ Builder  │ │ (interceptor,    │     │
│  │(heuris-  │ │(extended,│ │  NL parser,      │     │
│  │ tics +   │ │ tiered,  │ │  dynamic rules,  │     │
│  │failover) │ │ identity)│ │  queue)          │     │
│  └────┬─────┘ └────┬─────┘ └────────┬─────────┘     │
│       │            │                │                │
│  ┌────▼────────────▼────────────────▼──────────┐     │
│  │         PROVIDER LAYER                      │     │
│  │  LM Studio ←→ Haiku ←→ Sonnet              │     │
│  │  (local)      (fast)    (big)               │     │
│  │                                             │     │
│  │  Failover: local → fast → big               │     │
│  │  Providers: OpenRouter, Venice, Nvidia NIM,  │     │
│  │            Groq, Anthropic, OpenAI, + 25     │     │
│  └─────────────────────────────────────────────┘     │
│                                                      │
│  ┌─────────────────────────────────────────────┐     │
│  │         METACOGNITION                       │     │
│  │  Satisfaction detection (regex + extraction) │     │
│  │  Lesson creation / reinforcement / decay     │     │
│  │  Lesson injection into system prompts        │     │
│  └─────────────────────────────────────────────┘     │
│                                                      │
│  ┌─────────────────────────────────────────────┐     │
│  │         DREAM CYCLE & MONITORING            │     │
│  │  Heartbeat service (periodic background)     │     │
│  │  Supervisor (process management)             │     │
│  │  Monitor checks (infrastructure health)      │     │
│  │  Nightly cycle (consolidation, review)       │     │
│  └─────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────┘
         │              │              │
    ┌────▼────┐   ┌─────▼─────┐  ┌────▼────┐
    │ SQLite  │   │  QDrant   │  │  Redis  │
    │(logs,   │   │(episodic  │  │(working │
    │ lessons,│   │ memory,   │  │ memory, │
    │ tasks,  │   │ semantic  │  │ entity  │
    │ costs,  │   │ search)   │  │tracking)│
    │ rules)  │   │           │  │         │
    └─────────┘   └───────────┘  └─────────┘
```

---

## Package Structure (As Built)

```
nanobot/
├── agent/                      # Core agent loop and tools
│   ├── loop.py                 # AgentLoop: message processing (37 KB)
│   ├── context.py              # ContextBuilder: system prompt assembly
│   ├── memory.py               # File-based memory (MEMORY.md)
│   ├── skills.py               # Dynamic skill loading
│   ├── subagent.py             # Sub-agent delegation
│   ├── mcp/                    # Model Context Protocol integration
│   │   ├── bridge.py           # MCP bridge
│   │   ├── client.py           # MCP client (9 KB)
│   │   └── manager.py          # MCP resource management (6.5 KB)
│   ├── safety/                 # Security & sanitization
│   │   └── sanitizer.py        # MRO chain sandbox escape blocked
│   └── tools/                  # 12 built-in tools
│       ├── filesystem.py       # read_file, write_file, edit_file, list_dir
│       ├── shell.py            # exec (shell commands)
│       ├── web.py              # web_search (Brave), web_fetch
│       ├── message.py          # Send to channels
│       ├── spawn.py            # Sub-agent spawning
│       ├── cron.py             # Scheduled tasks
│       └── ...
│
├── copilot/                    # Executive copilot extensions
│   ├── config.py               # CopilotConfig schema
│   ├── db.py                   # Database utilities
│   ├── routing/                # Intelligent LLM routing
│   │   ├── router.py           # RouterProvider (drop-in LLMProvider)
│   │   ├── heuristics.py       # Deterministic classification
│   │   └── failover.py         # FailoverChain with provider tiers
│   ├── context/                # Tiered context management
│   │   ├── extended.py         # ExtendedContextBuilder (wraps base)
│   │   └── budget.py           # Token budget & continuation detection
│   ├── extraction/             # Background SLM extraction
│   │   ├── background.py       # Async fact/decision/constraint extraction
│   │   └── schemas.py          # Extraction JSON schemas
│   ├── approval/               # DELETED 2026-02-15 (approval system removed)
│   ├── metacognition/          # Self-improvement
│   │   ├── detector.py         # SatisfactionDetector
│   │   └── lessons.py          # LessonManager (CRUD, lifecycle, injection)
│   ├── cost/                   # Cost tracking
│   │   ├── logger.py           # CostLogger (per-call + routing)
│   │   ├── alerting.py         # CostAlerter (threshold alerts)
│   │   └── db.py               # Schema migrations
│   ├── memory/                 # Advanced memory (working)
│   │   ├── manager.py          # MemoryManager
│   │   ├── episodic.py         # QDrant episodic memory
│   │   ├── working.py          # DELETED 2026-02-19 (Redis removed)
│   │   ├── fulltext.py         # Full-text search
│   │   ├── embedder.py         # Embedding generation
│   │   └── tool.py             # Memory tool interface
│   ├── tasks/                  # Task queue (working)
│   │   ├── manager.py          # TaskManager
│   │   ├── worker.py           # TaskWorker
│   │   └── tool.py             # Task tool interface
│   ├── tools/                  # Domain tools (V2)
│   │   ├── git.py              # Git operations
│   │   ├── browser.py          # Playwright automation
│   │   ├── document.py         # PDF/image/Excel parsing
│   │   ├── aws.py              # AWS boto3 operations
│   │   └── n8n.py              # n8n webhook integration
│   ├── status/                 # Status dashboard (working)
│   │   ├── aggregator.py       # Health check aggregation
│   │   └── tool.py             # Status tool
│   ├── dream/                  # Dream cycle (working)
│   │   ├── cycle.py            # Nightly job orchestration
│   │   ├── heartbeat.py        # Heartbeat service
│   │   ├── monitor.py          # Infrastructure monitors
│   │   └── supervisor.py       # Process supervisor
│   ├── threading/              # Thread tracking
│   │   └── tracker.py          # Topic thread detection
│   ├── voice/                  # Voice transcription
│   │   └── transcriber.py      # faster-whisper + API fallback
│   └── alerting/               # Alert management
│       ├── bus.py              # Alert bus
│       └── commands.py         # Alert commands
│
├── channels/                   # 10 communication channels
│   ├── manager.py              # ChannelManager lifecycle
│   ├── whatsapp.py             # WhatsApp via Baileys bridge
│   ├── telegram.py             # Telegram Bot API
│   ├── discord.py              # Discord Bot
│   ├── slack.py                # Slack (socket mode)
│   ├── email.py                # IMAP/SMTP
│   ├── feishu.py               # Feishu (ByteDance)
│   ├── dingtalk.py             # DingTalk (Alibaba)
│   ├── qq.py                   # QQ
│   └── mochat.py               # MoChat (WeChat-like)
│
├── providers/                  # LLM provider abstraction
│   ├── base.py                 # LLMProvider ABC
│   ├── litellm_provider.py     # LiteLLM integration
│   ├── registry.py             # 30+ provider routing (399 lines)
│   └── transcription.py        # Groq voice transcription
│
├── cli/commands.py             # Typer CLI + gateway startup (47 KB)
├── session/manager.py          # Session lifecycle (JSONL persistence)
├── bus/                        # Event bus (InboundMessage ↔ OutboundMessage)
├── cron/                       # Scheduled task system
├── heartbeat/                  # Health monitoring
└── config/                     # Pydantic config schemas + loader
```

---

## Routing (Implemented)

**RouterProvider** (`copilot/routing/router.py`) — drop-in replacement for `LiteLLMProvider`.

Deterministic heuristic classification (no LLM call to route):

1. Private mode active → local only (no cloud)
2. Manual provider override (`/use venice`) → forced provider
3. Images attached → big model (vision)
4. Input >4096 chars → big model
5. Conversation tokens >3000 → fast model
6. Keyword complexity (code blocks, multi-step, analysis) → big model
7. Default → local

**Failover chain**: local → fast (Haiku) → big (Sonnet). Each tier tries all configured cloud providers (OpenRouter, Venice, Nvidia NIM, etc.) before moving to next tier.

**Self-escalation**: When routed to local, system prompt includes `[ESCALATE]` instruction. If local model responds with `[ESCALATE] reason`, router automatically retries with big model. Disabled during private mode.

**Provider registry** supports 30+ providers with auto-prefixing, per-model overrides, and API key detection.

---

## Context Assembly (Implemented)

**ExtendedContextBuilder** wraps base `ContextBuilder`:

- **Tier 1**: Last 2-3 exchanges verbatim (always included)
- **Tier 2**: Structured extractions from background SLM — facts, decisions, constraints formatted as briefing block
- **Tier 3**: Identity docs (soul.md, user.md, agents.md) with 60s cache TTL
- **Lessons**: Active lessons injected into system prompt (~100 tokens)
- **Onboarding**: When `/onboard` active, interview instructions injected

**Seamless continuation**: When conversation tokens approach 70% of model's budget, context rebuilt from Tier 2 extractions + last 2 exchanges. User sees brief note.

**Token budget**: Configurable (default 1500 tokens for injected context). `TokenBudget` class tracks and enforces.

---

## Approval System ~~(Implemented)~~ **DELETED 2026-02-15**

> **This system was removed.** The approval interceptor added code to override LLM judgment — this contradicts the LLM-first design principle. LLM judgment belongs to the LLM, not regex guardrails. See `POLICY.md` (workspace) for the current policy model and TROUBLESHOOTING.md (AGENT-APPROVAL-REMOVED-001).

~~- `exec` and `message` tools require approval by default~~
~~- Approval request sent via WhatsApp with plain-language summary~~
~~- **Natural language parsing**: "yeah go for it" → approve, "no too risky" → deny, "change the subject" → modify~~
~~- **Dynamic rules**: "auto-approve AWS under $50" → persistent rule in SQLite~~
- **Quick cancel**: "skip", "later", "nevermind" → immediate cancel without timeout wait
- Denied actions create lessons for future reference
- Timeout → auto-deny + lesson creation

---

## Metacognition (Implemented)

- **SatisfactionDetector**: regex patterns for positive/negative signals, enhanced by background extraction sentiment
- **LessonManager**: CRUD with confidence scoring (0-1), reinforcement/penalization, automatic deactivation
- Lessons created from: approval denials, negative satisfaction signals, shadow mode feedback
- Top 3 relevant lessons injected into system prompt (keyword overlap scoring)
- Lifecycle: create → inject → reinforce/penalize → deactivate if unhelpful

---

## Onboarding Interview (Implemented)

`/onboard` command triggers a structured interview conducted by nanobot's own LLM:

1. BASICS: Name, timezone, languages
2. LIFE CONTEXT: Current situation, responsibilities
3. GOALS: Career, personal, financial, health priorities
4. PROJECTS: Active projects, deadlines, where help needed
5. WORK STYLE: Brief vs detailed, proactive vs reactive, hours
6. AUTONOMY: When to act vs ask, what to never decide alone
7. ASSISTANCE: Tasks to hand off, reminders, bad news delivery

Results stored token-consciously:
- **USER.md** (~10 lines, loaded every message): lean essentials
- **MEMORY.md** (~400 token budget, loaded every message): behavioral core only (autonomy rules, communication style, prime directive). Detailed context (goals, action plan, life situation) stored in Qdrant episodic memory, retrieved on-demand via `recall_messages`

---

## Background Extraction (Implemented)

Runs async after every exchange:
- Sends exchange to local SLM (free) or Haiku fallback
- Extracts: facts, decisions, constraints, entities, sentiment
- Stores as JSON in session metadata
- Monitors token accumulation for continuation triggers
- Never blocks main flow — cancelled if new message arrives

---

## Cost Tracking (Implemented)

- Every LLM call logged: model, tokens in/out, cost USD
- Per-call alerts (configurable threshold, default $0.50)
- Daily spend alerts via WhatsApp
- Routing decisions logged: target, provider, model, reason, latency, cost
- No hard caps — advisory only

---

## Security (Implemented)

- MRO chain sandbox escape blocked (sanitizer.py)
- API keys in config.json, never in LLM-readable files
- Every LLM-initiated action logged to SQLite
- WhatsApp `allowFrom` restricts to user's number
- Private mode: local-only routing, no cloud calls
- Private mode auto-timeout (30 min default, configurable)
- Approval system gates all sensitive tool calls

---

## Channels (Implemented)

10 channels with standardized `BaseChannel` interface:
- WhatsApp (primary) — Node.js bridge via @whiskeysockets/baileys, auto-start, jidDecode fix
- Telegram, Discord, Slack, Email, Feishu, DingTalk, QQ, MoChat
- CLI interactive mode

---

## MCP Integration (Implemented)

Model Context Protocol support for external tool servers:
- `mcp/client.py` — connects to external MCP servers
- `mcp/manager.py` — manages tool discovery and routing
- `mcp/bridge.py` — bridges MCP tools into nanobot's tool system
- Optional dependency (`mcp>=1.0.0`)

---

## Memory System (Working)

**Episodic memory** (`memory/episodic.py`, 282 lines) — QDrant-backed with multi-factor scoring (recency, relevance, importance, access frequency) and hybrid search (dense + sparse vectors with RRF fusion).

**Working memory** (`memory/working.py`, 154 lines) — Redis-backed with async operations, auto-reconnect, entity tracking, and TTL-based expiration.

**Full-text search** (`memory/fulltext.py`) — FTS5 + BM25 ranking via SQLite for structured data queries.

**Memory manager** (`memory/manager.py`, 222 lines) — Orchestrates all three memory backends with graceful degradation. Initialized with 3-retry logic for transient infrastructure delays.

---

## Dream Cycle & Self-Maintenance (Working)

**Dream cycle** (`dream/cycle.py`) — 13 nightly jobs: memory consolidation, cost reporting, lesson review, backup, monitoring, memory reconciliation, zero-vector cleanup, routing cleanup, MEMORY.md budget check, metacognitive self-reflection, identity evolution, observation cleanup, codebase indexing. Scheduled via `croniter` at 7 AM EST. *(Original doc said "7 jobs" — Sentience Plan expanded to 13.)*

**Heartbeat** (`dream/heartbeat.py`, 180 lines) — Proactive task execution during active hours (7 AM–10 PM), periodic background checks.

**Monitor** (`dream/monitor.py`, 138 lines) — State-transition alerting for infrastructure (QDrant, Redis, LM Studio), morning nag messages, automated remediation attempts.

**Process supervisor** (`dream/supervisor.py`, 128 lines) — Auto-restart with exponential backoff, max restart limits, alert bus integration. Supports fire-and-forget services via `get_task_fn`.

---

## Deferred to V2

| Module | Status | Notes |
|---|---|---|
| `tools/git.py` | Code exists | Not registered as agent tools |
| `tools/browser.py` | Code exists | Playwright not installed |
| `tools/aws.py` | Code exists | AWS credentials not configured |
| `tools/n8n.py` | Code exists | n8n not deployed |
| `tools/document.py` | Code exists | Bridge media download not implemented |

---

## Tech Stack (As Built)

| Layer | Technology | Status |
|---|---|---|
| Interface | Baileys (WhatsApp) + 9 other channels | Working |
| Foundation | nanobot (modified with copilot hooks) | Working |
| Local LLM | LM Studio (Windows 5070ti) | Working |
| Cloud LLMs | OpenRouter, Venice, Nvidia NIM, Groq, + 25 more | Configured |
| Routing | RouterProvider (heuristic + failover) | Working |
| Context | ExtendedContextBuilder (tiered) | Working |
| Extraction | Background SLM (async) | Working |
| Approval | NL parser + dynamic rules + queue | Working |
| Metacognition | Lessons + satisfaction detection | Working |
| Cost | Per-call + daily logging + alerts | Working |
| Embeddings | Embedder module (LM Studio / OpenAI) | Working |
| Vector DB | QDrant (episodic memory, hybrid search) | Working |
| Cache | Redis (working memory, entity tracking) | Working |
| Structured Data | SQLite | Working |
| Voice | faster-whisper + Groq transcription | Configured |
| MCP | External tool server bridge | Working |
| Session | JSONL persistence | Working |

---

## Slash Commands

| Command | Description |
|---|---|
| `/new` | Start new conversation session |
| `/help` | Show available commands |
| `/use <provider>` | Force specific cloud provider |
| `/private` | Enable private mode (local only) |
| `/onboard` | Start onboarding interview |
| `/profile` | Show current user profile |
| `/status` | System health dashboard |

---

## Remaining Setup (User Action)

1. **Cloud API key** — Add at least one cloud provider key to `~/.nanobot/config.json` for fallback when LM Studio is offline (OpenRouter recommended).
2. **E2E verification** — Restart gateway, verify memory persists across sessions, verify dream cycle fires.

---

## Success Criteria (V1) — All Complete

- [x] Multi-channel communication (WhatsApp primary)
- [x] Intelligent routing (local vs cloud, heuristic-based)
- [x] Seamless model switching (context preserved across providers)
- [x] Automatic context continuation (70% budget trigger)
- [x] Background extraction (facts, decisions, constraints)
- [x] ~~Natural language approvals~~ (removed 2026-02-15 — see TROUBLESHOOTING.md AGENT-APPROVAL-REMOVED-001)
- [x] Self-improvement via lessons
- [x] Cost tracking and alerting
- [x] Onboarding interview
- [x] Private mode (local-only)
- [x] Self-escalation (local → cloud when needed)
- [x] Episodic memory (QDrant, multi-factor scoring, hybrid search)
- [x] Working memory (Redis, auto-reconnect, entity tracking)
- [x] Dream cycle nightly maintenance (7 jobs, cron-scheduled)
- [x] Process supervisor with auto-restart
- [x] Health monitoring with alerting
- [x] Task queue with worker (registered with supervisor)
