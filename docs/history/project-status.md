# Project Status

> Quick reference for where everything stands.

**Last updated**: 2026-02-21 (Routing visibility + test hardening)

**V1 Status**: Complete

---

## Feature Status

| Feature | Status | Notes |
|---|---|---|
| WhatsApp channel | **Working** | Baileys bridge, auto-start, jidDecode fix |
| 9 other channels | **Available** | Telegram, Discord, Slack, Email, Feishu, DingTalk, QQ, MoChat, CLI |
| LM Studio (local LLM) | **Working** | 192.168.50.100:1234 |
| Router V2 (plan-based) | **Working** | LLM-generated routing plans via PlanRoutingTool, mandatory safety net |
| PlanRoutingTool | **Working** | propose/validate/activate/clear routing plans with API probes |
| router.md | **Working** | Routing planner ground truth (provider table, costs, constraints) |
| Multi-cloud failover | **Working** | OpenRouter, Venice, Nvidia NIM + 25 providers, recovery probing |
| Self-escalation | **Working** | Default model → escalation_model when model says [ESCALATE] |
| Tiered context | **Working** | 3 tiers + identity docs + lessons |
| Background extraction | **Working** | Async facts/decisions/constraints |
| Context continuation | **Working** | 70% budget trigger, auto-rebuild |
| POLICY.md guardrails | **Working** | Regex-based safety checks, tool blocking, forensic audit log |
| Metacognition/lessons | **Working** | Satisfaction detection, confidence lifecycle |
| Cost tracking | **Working** | Per-call + daily logging + alerts + litellm fallback pricing |
| Private mode | **Working** | Local-only, 30-min timeout (idle-based, fixed) |
| Onboarding interview | **Working** | /onboard, prompt-injected interview |
| MCP integration | **Working** | External tool server bridge |
| Security (MRO block) | **Working** | Sandbox escape prevention |
| Episodic memory (Qdrant) | **Working** | Qdrant connected, multi-factor scoring, hybrid search |
| Full-text search | **Working** | FTS5 + BM25 ranking via SQLite |
| Core facts injection | **Working** | High-confidence items (≥0.8) auto-injected into system prompt |
| Dream cycle | **Working** | Nightly at 7 AM EST via croniter, 13 jobs (incl. identity evolution, observation cleanup, codebase indexing) |
| Dream observations pipeline | **Working** | Structured JSON output → `dream_observations` table → heartbeat → weekly review |
| Cognitive heartbeat | **Working** | `CopilotHeartbeatService` — dream observations, pending tasks, autonomy context injected into heartbeat prompt |
| Autonomy permissions | **Working** | Per-category (6 categories) in `autonomy_permissions` table; all default to `notify` |
| Task retrospectives | **Working** | Post-task LLM diagnosis stored in `task_retrospectives` + embedded in Qdrant for future wisdom injection |
| Identity evolution | **Working** | Dream Job 11 applies/proposes identity file changes; versioned in `evolution_log`, gated by `autonomy_permissions` |
| Weekly review expanded | **Working** | Capability gap synthesis, failure patterns, roadmap proposals, evolution proposals, stored in `weekly_review_log` |
| /dream command | **Working** | Triggers dream cycle on demand |
| /review command | **Working** | Triggers weekly review on demand |
| Process supervisor | **Working** | Auto-restart with exponential backoff, fire-and-forget support |
| HealthCheckService | **Working** | Programmatic health checks (renamed from HealthMonitorService, LLM call removed) |
| Task queue | **Working** | Manager + worker registered with supervisor |
| Status dashboard | **Working** | Aggregator + alerts + session tokens + error visibility |
| Voice transcription | **Configured** | Groq-based transcriber ready, needs E2E test |
| Domain tools | **V2** | Git, browser, docs, AWS, n8n — code exists, not registered as agent tools |

---

## Infrastructure

| Service | Status | Location |
|---|---|---|
| LM Studio | Running | 192.168.50.100:1234 (Windows 5070ti) |
| Qdrant | Running | localhost:6333 (systemd), `episodic_memory` collection |
| SQLite | Running | data/sqlite/copilot.db |
| WhatsApp bridge | Running | localhost:3001 (Node.js) |
| Nanobot gateway | Running | localhost:18790 |

---

## Remaining Setup (User Action)

1. **Cloud API key** — Add at least one cloud provider key to `~/.nanobot/config.json` for fallback when LM Studio is offline (OpenRouter recommended).
2. **E2E verification** — Restart gateway, verify memory persists across sessions, verify dream cycle fires.
3. **Git commit** — All recent changes need to be committed.

---

## Code Statistics

| Metric | Value |
|---|---|
| Total Python files | 117 |
| Core nanobot (upstream) | ~3,600 lines |
| Copilot additions | ~2,800 lines |
| Upstream files modified | 5 files, ~270 lines |
| Test count | ~368 automated tests (version-controlled, ruff-clean) |
| Package version | 0.1.3.post7 |
| Python version | ≥3.11 |

---

## Directory Structure Note

`workspace/` contains upstream nanobot defaults (SOUL.md, USER.md, HEARTBEAT.md, AGENTS.md). `data/copilot/` contains executive copilot overrides that take precedence at runtime.

## New SQLite Tables (Sentience Plan)

| Table | Purpose |
|-------|---------|
| `dream_observations` | Structured observations from dream/heartbeat/weekly/task failures |
| `autonomy_permissions` | Per-category autonomy modes (notify/autonomous/disabled) |
| `task_retrospectives` | Post-task LLM diagnosis and learnings |
| `weekly_review_log` | Full weekly review storage with roadmap proposals |
| `evolution_log` | Versioned identity file change tracking |
| `dream_cycle_log.reflection_full` | Full dream reflection (ALTER TABLE addition) |

---

## Documentation Index

| Document | Location | Purpose |
|---|---|---|
| V1 Architecture (Updated) | `Executive Co-Pilot V1 Architecture — Updated.md` | What's built, how it works |
| V2 Architecture | `Executive Co-Pilot V2 Architecture.md` | What's next, prioritized roadmap |
| **V2.1 Brain Architecture** | **`2026-02-16-v2.1-brain-architecture-plan.md`** | **CURRENT implementation plan — orchestrator, DAG, parallel workers** |
| ~~V2.1 Task Lifecycle Plan~~ | `2026-02-16-v2.1-task-lifecycle-plan.md` | SUPERSEDED — old flat-step plan, Tasks 2/5/7 dropped |
| V1 Completion Plan | `V1 Completion Plan.md` | What was done to finish V1 |
| Lessons Learned | `Lessons Learned.md` | Hard-won insights |
| Decisions & Tradeoffs | `Decisions & Tradeoffs.md` | Why we chose what we chose |
| Changes from Upstream | `Changes from Upstream Nanobot.md` | Every modification to base nanobot |
| Changelog | `CHANGELOG.md` | Chronological feature history |
| README | `README.md` | GitHub-ready project overview |
| Phase 1 Setup | `PHASE_1_SETUP.md` (in repo) | Original infrastructure setup guide |
| Testing Guide | `TESTING.md` (in repo) | How to run and write tests |
| Security Policy | `SECURITY.md` (in repo) | Security practices and known limitations |
| Network Topology | `NETWORKING SUMMARY FOR CLAUDE CODE.txt` | IPs, ports, connection flows |

---

## Deferred Work

### Memory Confidence Decay — Activity-Based Displacement
- **Problem**: `memory_items` grows monotonically. No confidence decay means old facts never fade.
- **Key constraint**: Decay must be activity-gated (triggered by new memory formation), NOT time-based. Idle periods with no interactions must not cause forgetting.
- **Proposed approach**: Displacement model — protect top-N most recently updated items, decay the rest, but ONLY when new items have been stored since last dream run. Guard: `SELECT COUNT(*) FROM memory_items WHERE updated_at > :last_dream_timestamp` — if 0, skip decay.
- **Also needed**: Extraction quality gate (current pipeline stores garbage like "$0.40", "The Good" as entities at confidence 0.5). Consider minimum content-length or LLM-based quality filter before storing.
- **Current mitigation**: 200-token budget cap on core facts injection + 0.8 confidence threshold act as natural limiters.
