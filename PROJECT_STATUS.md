# Project Status

> Quick reference for where everything stands.

**Last updated**: 2026-02-16

**V1 Status**: Complete

---

## Feature Status

| Feature | Status | Notes |
|---|---|---|
| WhatsApp channel | **Working** | Baileys bridge, auto-start, jidDecode fix |
| 9 other channels | **Available** | Telegram, Discord, Slack, Email, Feishu, DingTalk, QQ, MoChat, CLI |
| LM Studio (local LLM) | **Working** | 192.168.50.100:1234, phi-4-mini-reasoning |
| Heuristic routing | **Working** | RouterProvider with 7-point classification |
| Multi-cloud failover | **Working** | OpenRouter, Venice, Nvidia NIM + 25 providers |
| Self-escalation | **Working** | Local → cloud when model says [ESCALATE] |
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
| Episodic memory (QDrant) | **Working** | QDrant connected, multi-factor scoring, hybrid search |
| Working memory (Redis) | **Working** | Redis connected, auto-reconnect, entity tracking |
| Full-text search | **Working** | FTS5 + BM25 ranking via SQLite |
| Dream cycle | **Working** | Nightly at 3 AM via croniter, 10 jobs orchestrated (incl. MEMORY.md budget check) |
| Process supervisor | **Working** | Auto-restart with exponential backoff, fire-and-forget support |
| Health monitor | **Working** | State-transition alerting, morning nag, remediation |
| Copilot heartbeat | **Working** | Proactive task execution, active hours guard (7am-10pm) |
| Task queue | **Working** | Manager + worker registered with supervisor |
| Status dashboard | **Working** | Aggregator + alerts + session tokens + error visibility |
| Voice transcription | **Configured** | Groq-based transcriber ready, needs E2E test |
| Domain tools | **V2** | Git, browser, docs, AWS, n8n — code exists, not registered as agent tools |

---

## Infrastructure

| Service | Status | Location |
|---|---|---|
| LM Studio | Running | 192.168.50.100:1234 (Windows 5070ti) |
| QDrant | Running | localhost:6333 (systemd), `episodic_memory` collection |
| Redis | Running | localhost:6379 (systemd) |
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
| Test count | 33 automated tests | 3 Manual E2E
| Package version | 0.1.3.post7 |
| Python version | ≥3.11 |

---

## Directory Structure Note

`workspace/` contains upstream nanobot defaults (SOUL.md, USER.md, HEARTBEAT.md, AGENTS.md). `data/copilot/` contains executive copilot overrides that take precedence at runtime.

## Documentation Index

| Document | Location | Purpose |
|---|---|---|
| V1 Architecture (Updated) | `Executive Co-Pilot V1 Architecture — Updated.md` | What's built, how it works |
| V2 Architecture | `Executive Co-Pilot V2 Architecture.md` | What's next, prioritized roadmap |
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
