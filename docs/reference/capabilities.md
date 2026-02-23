> **DEPRECATED** — This content has been merged into workspace/AGENTS.md. Do not update this file.

# System Capabilities

## Commands
- /status — Health, costs, routing, memory, alerts, session context
- /use <provider> — Override routing to cloud provider (auto-reverts after 60 min idle)
- /private — Local-only mode (no cloud calls)
- /new — Start fresh session
- /dream — Trigger dream cycle manually
- /tasks — List active tasks with status
- /task <id> — Detailed task view with steps
- /cancel <id> — Cancel a running task

## Tools
- read_file, write_file, edit_file, list_dir — Filesystem
- exec — Shell (governed by POLICY.md guardrails)
- web_search, web_fetch — Internet access
- message — Send to channels
- task — Create and manage persistent tasks with background execution
- recall_messages — Search episodic memory (Qdrant)
- status — System dashboard

## Skills
Skills in `~/.nanobot/workspace/skills/` define specialized capabilities.
You can create new skills to teach yourself how to do things you can't yet.
Each skill has a SKILL.md describing its purpose and usage.

## Infrastructure
- Qdrant: Episodic memory vector DB (localhost:6333, 768d embeddings)
- SQLite: Costs, routing, lessons, alerts, tasks, events, structured memory items, FTS5 keyword search, SLM work queue
- Routing: Automatic Tier 1 → Tier 2 → Tier 3 with self-escalation
- Model Pool: 12 models cataloged in data/copilot/models.md — reviewed weekly via recon findings
- Dream cycle: Daily 7 AM EST — memory consolidation, lesson decay, cost report
- Recon system: 5 cron jobs scan AI ecosystem (GitHub repos, web sources, email newsletters, model landscape, source discovery) → store findings in recon_findings table → weekly/monthly reviews triage into actionable proposals
- Weekly Review: Sunday 9 AM EST — recon intelligence triage, cost trends, strategic reflection
- Heartbeat: Every 2h (7 AM-10 PM) — updates, task review, event logging
- Background extraction: Tier 0 SLM extracts facts/decisions/entities after each exchange
- Extraction resilience: SLM work queue (SQLite) buffers extraction/embedding when LM Studio is offline; drains automatically on reconnect. Falls back to heuristic extraction — no cloud fallback.

## NOT Configured (Do Not Attempt)
- Calendar (no CalDAV/Google) — do not ask for provider info
- User's To-do list — not yet connected
- n8n workflows — not yet deployed

## Model Tiers (Conversation Routing)
- Tier 0 — Brainstem SLM (4B, local): Extraction, classification only
- Tier 1 — Local Cortex (~20-30B, local): Basic Conversation, privacy mode
- Tier 2 — Tactical Hub (cloud cheap): Fallback, quick tasks, metacognition
- Tier 3 — Cognitive Core (cloud strong): Complex reasoning, creative, multi-step

## Model Pool (Task Execution)
See data/copilot/models.md for the full 12-model pool with selection guide.
Task decomposer recommends a model per step; executor uses it via recommended_model field.
