# Executive Co-Pilot V1: Full Architecture

---

## Overview

A personal autonomous assistant accessible via WhatsApp, built by extending nanobot (stock, unmodified) with an intelligent proxy layer that handles routing, context management, memory, self-improvement, approvals, tools, and proactive background tasks.

**Interface**: Regular WhatsApp via Baileys (not Business API)
**Foundation**: nanobot (HKUDS, ~4K lines, MIT license) — kept stock, never modified
**Intelligence**: Copilot Proxy (our code) sitting between nanobot and all LLMs
**Philosophy**: Reduce the user's burden, never add to it. Automate the "how." Escalate only when genuinely uncertain or high-stakes.

---

## System Architecture (All Phases Complete)

```
WhatsApp (voice or text, phone)
    ↓ Baileys
Nanobot (stock, unmodified, localhost:3001)
    ↓ LiteLLM → localhost:5001/v1
┌──────────────────────────────────────────────────────┐
│  COPILOT PROXY (FastAPI, localhost:5001)              │
│                                                      │
│  ┌──────────────────────────────────────────────┐    │
│  │  MAIN FLOW (blocking, every request)         │    │
│  │  1. Voice? → transcribe                      │    │
│  │  2. Satisfaction signals (regex baseline)     │    │
│  │  3. Route (heuristics + lessons, no LLM)     │    │
│  │  4. Continuation check (refresh if needed)   │    │
│  │  5. Assemble context (tiered)                │    │
│  │  6. Call LLM (failover chain)                │    │
│  │  7. Approval check (intercept if needed)     │    │
│  │  8. Log routing, cost, outcome               │    │
│  │  9. Return response                          │    │
│  └──────────────────────────────────────────────┘    │
│                                                      │
│  ┌──────────────────────────────────────────────┐    │
│  │  BACKGROUND SLM (async, after each exchange) │    │
│  │  - Extract facts/decisions/constraints (JSON) │    │
│  │  - Sentiment detection (better than regex)    │    │
│  │  - Token accumulation monitoring              │    │
│  │  - Local SLM when available, Haiku fallback   │    │
│  │  - Never blocks main flow                     │    │
│  └──────────────────────────────────────────────┘    │
│                                                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐     │
│  │ Router   │ │ Context  │ │ Approval Queue   │     │
│  │ (heur-   │ │ Assembly │ │ (natural language │     │
│  │  istics  │ │ (tiered) │ │  approve/deny,   │     │
│  │ +lessons)│ │          │ │  dynamic rules)  │     │
│  └────┬─────┘ └────┬─────┘ └────────┬─────────┘     │
│       │            │                │                │
│  ┌────▼────────────▼────────────────▼──────────┐     │
│  │           PROVIDER LAYER                    │     │
│  │  LM Studio ←→ Haiku ←→ Sonnet ←→ Opus      │     │
│  │  (local)      (cheap)   (smart)   (best)    │     │
│  └─────────────────────────────────────────────┘     │
│                                                      │
│  ┌─────────────────────────────────────────────┐     │
│  │         METACOGNITION                       │     │
│  │  Outcome detection → Lesson creation        │     │
│  │  Lesson application → Routing adjustment    │     │
│  │  Shadow period calibration (first 2 weeks)  │     │
│  └─────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────┘
         │              │              │
    ┌────▼────┐   ┌─────▼─────┐  ┌────▼────┐
    │ SQLite  │   │  QDrant   │  │  Redis  │
    │ (logs,  │   │ (episodic │  │(working │
    │ lessons,│   │  memory,  │  │ memory, │
    │ tasks,  │   │  semantic │  │ session │
    │ costs,  │   │  search)  │  │ state)  │
    │ rules)  │   └───────────┘  └─────────┘
    └─────────┘

SIDECAR (separate process, Phase 7)
    │
    ├── Scheduler (email checks, LinkedIn, morning brief)
    ├── Dream Cycle (review, learn, summarize, backup)
    └── Proactive Messenger (sends WhatsApp when needed)
```

---

## The Proxy: Core Behaviors

### Routing (Phase 2)

Deterministic — no LLM classification call. First match wins:

1. Images → Sonnet
2. Input >4096 chars → Sonnet
3. Conversation tokens >3000 → Haiku
4. High-confidence lesson override → route per lesson
5. LM Studio down → Haiku (simple) or Sonnet (complex)
6. Heuristic complexity (keywords + length, code blocks, multi-step) → Sonnet
7. Default → local

Failover chain: local → Haiku → Sonnet. OpenRouter fails → Venice. All fail → friendly error.

### Context Assembly (Phase 2)

Three tiers, filled until target model's token budget (75% of context limit):

- **Tier 1**: Last 2-3 exchanges verbatim (always included)
- **Tier 2**: Structured extractions — JSON of facts, decisions, constraints accumulated by the background SLM. Formatted as a briefing. **This is what makes model switching seamless.**
- **Tier 3**: Session summaries from previous sessions (Phase 4 memory layer populates these; basic truncation until then)

Local model gets compressed context. Cloud models get generous context. Lessons injected as system notes (~100 tokens).

**Seamless continuation**: When conversation tokens approach 70% of current model's budget (detected by background processor), the proxy rebuilds context from Tier 2 extractions + last 2 exchanges on the next message. User gets a brief note: "📝 Context refreshed." No user action needed.

### Background Extraction (Phase 2)

Critical infrastructure — always runs after every exchange:

- Sends exchange to local SLM (free) or Haiku fallback (~$0.001) with structured prompt
- Extracts: facts, decisions, constraints, specific values/names, sentiment
- Stores as JSON in `conversation_state.structured_extraction`
- Also monitors token accumulation and flags continuation when needed
- Never blocks user messages — cancelled if new message arrives
- If both local and Haiku fail, falls back to heuristic extraction (first/last sentences)

### Self-Improvement (Phase 2-3)

- Detects user satisfaction/dissatisfaction (regex baseline, SLM-enhanced via background processor)
- Creates lessons on negative outcomes, reinforces on positive
- Lessons have confidence scores that increase with reinforcement, lead to deactivation if consistently unhelpful
- Relevant lessons injected into routing decisions and system prompts
- **Shadow period** (first 2 weeks after onboarding): system runs in more conservative mode, explicitly asks "Was that the right call?" after autonomous actions to calibrate thresholds

### Approval System (Phase 3)

- Actions matching approval patterns (send email, post to social media, execute shell commands, spend money) get intercepted
- Approval message sent via WhatsApp with plain-language summary
- **Natural language approval** — no forced Y/N format. User can reply naturally ("yeah go for it", "hold on, change the second paragraph", "not now"). The proxy (or background SLM) interprets intent as approve/deny/modify. If unclear, asks for clarification.
- **Dynamic rules**: User can say "auto-approve AWS under $50 from now on" and it becomes a persistent rule in SQLite. Rules can expire or be revoked.
- Denied actions create lessons ("User denied this type of action — don't attempt without more context")

### Voice (Phase 2)

- WhatsApp voice notes transcribed via faster-whisper (local CPU) or OpenAI Whisper API fallback
- Transcribed text enters normal routing flow
- Voice synthesis for responses is V2

### Thread Tagging (Phase 2)

- Background extraction detects topic shifts → assigns new `thread_id` and `thread_label`
- Next response prepended with `[{label}]`
- User can force with `> TopicName`
- Thread IDs tracked in routing_log for per-thread cost analysis

---

## Memory (Phase 4)

### Working Memory (Redis)

- Current session state, active tasks, recent context
- AOF persistence — survives restarts
- TTL-based expiry for stale sessions

### Episodic Memory (QDrant)

- Dense vectors (V1) for semantic search
- Hybrid search with sparse/BM25 vectors (V2) for exact term matching
- Important exchanges embedded and stored: approved actions, learned preferences, project context
- Top 3-5 relevant memories retrieved by semantic similarity before each LLM call
- Tiered chunking: semantic for critical docs, recursive (512 tokens) for general, AST-based for code
- Contextual retrieval: document context summaries prepended to chunks before embedding

### Session Summarization

- After every N exchanges (or at session close), proxy generates ~100-token summary
- Conversations older than 7 days get summarized, raw exchanges archived
- Only summaries remain in active retrieval (Tier 3 context)

### Smart Context Budget

- Total injected "system" context stays under configurable limit (default 1500 tokens)
- Current message + session summary + relevant episodic memories + applicable lessons
- Never dump everything — surgical retrieval only

---

## Tools (Phase 5)

Implemented as nanobot SKILL.md files (markdown instructions for the LLM) backed by standalone Python scripts called via nanobot's `exec` tool:

- **Email checker** — connects via IMAP, returns summary
- **LinkedIn poster** — drafts and posts via API/browser automation
- **System admin** — server management commands
- **Status dashboard** — health checks formatted for WhatsApp

### Dry-Run Mode

Every tool script accepts a `DRY_RUN` flag. When true, logs what would happen without executing. Essential for testing.

### Approval Integration

Proxy recognizes when nanobot is about to execute a tool that matches approval-required patterns → intercepts → queues approval → waits for natural language response.

---

## Onboarding & Preferences (Phase 6)

### Onboarding Interview

Structured conversation (stored as SKILL.md) covering:
- Active projects and priorities
- Communication preferences (when to interrupt, when to stay quiet)
- Approval preferences (what needs OK, what can auto-approve)
- Work patterns (availability, sleep schedule)
- Goals (big-picture direction)

### Shadow Period (First 2 Weeks)

After onboarding, system operates conservatively:
- Asks "I handled X on my own — was that the right call?" after autonomous actions
- User responses become high-confidence lessons
- Calibrates approval thresholds and routing behavior based on actual (vs stated) preferences

### Preference Evolution

- Preferences stored as structured data in SQLite + semantic data in QDrant
- Brief "about the user" section (~100 tokens) injected into every prompt
- Preferences update automatically via lessons system ("User consistently approves email summaries without changes" → auto-approve email summaries)

---

## Background Tasks & Dream Cycle (Phase 7)

### Sidecar Scheduler (Separate Process)

Runs alongside nanobot and the proxy, handling:
- Scheduled tasks (check email every 4 hours, LinkedIn post weekly)
- Morning brief — summarizes overnight activity, queued items, reminders
- Nightly dream cycle
- Proactive WhatsApp messages when something is worth saying

### Dream Cycle (Nightly)

Reviews the day's interactions:
- **Routing analysis**: Which routing decisions led to bad outcomes? Update lessons/heuristics.
- **Memory consolidation**: Compress day's conversations into episodic memories, prune noise
- **Skill extraction** (V2): If the same task type succeeds 3+ times, compile a skill file
- **Security review**: Static analysis of any code changes, dependency CVE checks (flag for user, never auto-act)
- **Cost analytics**: Daily spend report, anomaly detection
- **Versioned heuristic updates**: Sage generates proposed routing rule changes, sends summary for user approval via WhatsApp before applying

### Weekly Review

- Compare activities against stated goals
- Long-term memory review and pruning
- Attack surface tracking (accepted tradeoffs, accumulated risk)

---

## Security (Woven Throughout)

### Silent Protections (Zero Friction)

- Proxy sanitizes LLM responses before tool execution
- API keys in `.env` only, never in files the LLM can read
- Every LLM-initiated action logged to SQLite (audit trail)
- Rate limiting on cloud API calls (prevents runaway token burn)
- WhatsApp `allowFrom` restricted to user's number
- Never log raw user messages (SHA256 hash only in routing_log)

### Minimal Friction

- Actions involving email, social media, spending money → natural language approval
- Cost threshold: single LLM call exceeding $0.50 → pause and ask

### Dream Cycle Security Consciousness

- Reviews code changes with security lens
- Maintains a security ledger of accepted tradeoffs
- Flags compounding risks ("Port X + no rate limit + public IP = elevated risk")
- Self-corrects minor issues (linting, config), escalates architectural tradeoffs
- **Never takes automated "burn protocol" actions** — flags for user, that's it

### Deferred to V2

- Prompt injection defense (relevant when adding email/web input)
- Advanced credential management
- Network-level isolation

---

## Cost Observability

- Real-time tracking: every LLM call logged with model, tokens, cost
- Daily/weekly/monthly views (via `/status` command and eventually web dashboard)
- Per-thread cost tracking
- Anomaly alerts ("Spike: $18/hr vs $4 avg") — warning only, never blocks
- **No hard caps.** User retains full control. System optimizes cost through intelligent routing, not enforcement.

---

## Phase Breakdown

| Phase | What | Foundation It Builds On |
|-------|------|------------------------|
| **1** ✅ | Nanobot + WhatsApp + LM Studio running | Infrastructure |
| **2** | Copilot Proxy: routing, context assembly, background extraction, voice, logging, systemd | Everything below depends on this |
| **3** | Approval system (natural language), self-improvement loop, cost alerting | Proxy + metacognition |
| **4** | Memory layer: QDrant episodic, Redis working, session summarization, smart context budget | Proxy + context assembly |
| **5** | Tool layer: SKILL.md files + scripts, dry-run mode, approval integration | Proxy + approvals |
| **6** | Onboarding interview, preference model, shadow period calibration | Memory + metacognition |
| **7** | Sidecar: scheduler, dream cycle, morning brief, proactive messaging, backups | Everything |

---

## V2 Enhancements (After All V1 Phases)

- Hybrid search (QDrant sparse vectors + RRF fusion)
- Neo4j semantic graph for relationship mapping
- DSPy-optimized dream cycle prompts
- Automatic skill compilation from repeated task patterns
- Advanced browser stealth (residential proxies, CAPTCHA handling)
- Matryoshka embeddings (multi-resolution vectors)
- Web dashboard (React) for cost visualization, memory inspection, rule management
- Sub-agent orchestration (proxy spawns specialized agents)
- Voice synthesis for responses
- "See what I see, hear what I hear" ambient awareness

---

## What This Architecture Preserves for V2

The proxy pattern means all V2 additions slot in without re-architecting:

- Neo4j → `context.py` gets a new retrieval backend
- Sub-agents → proxy spawns them with their own context
- Browser stealth → tool scripts upgraded, SKILL.md updated
- Hybrid search → QDrant collection updated, retrieval logic extended
- Dashboard → reads from the same SQLite/QDrant the proxy already populates

---

## Tech Stack

| Layer | Technology | Fallback |
|-------|-----------|----------|
| Interface | Baileys (regular WhatsApp) | Whatsmeow, or Business API if banned |
| Foundation | Nanobot (stock, unmodified) | — |
| Proxy | FastAPI + uvicorn | — |
| Local LLM | LM Studio (Windows PC, 5070ti) | Ollama on Proxmox |
| Cloud LLM | OpenRouter (Haiku/Sonnet/Opus) | Venice, MiniMax |
| Embeddings | LM Studio (nomic) or OpenAI | voyage-3 |
| Vector DB | QDrant (dense V1, hybrid V2) | ChromaDB |
| Cache | Redis (AOF persistence) | SQLite fallback |
| Structured Data | SQLite (V1) → PostgreSQL (V2) | — |
| Voice | faster-whisper (local CPU) | OpenAI Whisper API |
| Tools | Nanobot SKILL.md + Python scripts | — |
| Services | systemd | — |
| Backup | Nightly QDrant snapshot + SQLite → S3 | rsync to NAS |

---

## Success Criteria (V1 Complete)

- Zero manual context management — user never resets conversations
- Model switches are seamless — cloud model picks up with full awareness of what was discussed locally
- Context windows managed automatically — continuation triggers invisibly when needed
- Voice messages work — transcribed and answered naturally
- Approvals are natural language — no forced formats, works well with voice
- System learns from outcomes — routing and behavior improve over time
- Shadow period calibrates real preferences — not just what user stated in onboarding
- Cost is visible but never obstructive
- All "doing" is automated — user is the executive, system is the company