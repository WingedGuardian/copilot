# System Capabilities

## Commands
- /status — Health, costs, routing, memory, alerts, session context
- /use <provider> — Override routing to cloud provider (auto-reverts after 60 min idle)
- /private — Local-only mode (no cloud calls)
- /new — Start fresh session
- /dream — Trigger dream cycle manually

## Tools
- read_file, write_file, edit_file, list_dir — Filesystem
- exec — Shell (governed by POLICY.md guardrails)
- web_search, web_fetch — Internet access
- message — Send to channels
- recall_messages — Search episodic memory (Qdrant)
- status — System dashboard

## Skills
Skills in `~/.nanobot/workspace/skills/` define specialized capabilities.
You can create new skills to teach yourself how to do things you can't yet.
Each skill has a SKILL.md describing its purpose and usage.

## Infrastructure
- Qdrant: Episodic memory vector DB (localhost:6333, 768d embeddings)
- Redis: Cache layer (localhost:6379)
- SQLite: Costs, routing, lessons, alerts, tasks, events, SLM work queue
- Routing: Automatic Tier 1 → Tier 2 → Tier 3 with self-escalation
- Dream cycle: Daily 7 AM EST — memory consolidation, lesson decay, cost report
- Heartbeat: Every 2h (7 AM-10 PM) — health checks, task review, event logging
- Background extraction: Tier 0 SLM extracts facts/decisions/entities after each exchange
- Extraction resilience: SLM work queue (SQLite) buffers extraction/embedding when LM Studio is offline; drains automatically on reconnect. Falls back to heuristic extraction — no cloud fallback.

## NOT Configured (Do Not Attempt)
- Email (no IMAP/SMTP) — do not ask for provider info
- Calendar (no CalDAV/Google) — do not ask for provider info
- To-do list — not yet connected
- n8n workflows — not yet deployed

## Model Tiers
- Tier 0 — Brainstem SLM (4B, local): Extraction, classification only
- Tier 1 — Local Cortex (~20-30B, local): Conversation, privacy mode
- Tier 2 — Tactical Hub (cloud cheap): Fallback, quick tasks, metacognition
- Tier 3 — Cognitive Core (cloud strong): Complex reasoning, creative, multi-step
- Tier 4 — Executive Office (cloud frontier + thinking): Weekly audits, architecture (V2)
