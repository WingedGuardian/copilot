# Help Topics

## routing

Control which models handle your requests.

**Commands:**
- `/use <provider>` — Switch to a specific provider (e.g., `/use venice`)
- `/use <provider> fast` — Use the fast/cheap tier
- `/use <provider> <model>` — Use a specific model (e.g., `/use openrouter gpt4o`)
- `/use auto` — Return to automatic routing
- `/private` — Local-only mode (no cloud calls)

**Common customizations (ask me to change these):**
- Switch default model — "change my default model to claude-sonnet-4"
- Adjust escalation — "disable self-escalation" or "enable escalation"
- Change fast model — "use gemini-flash as my fast model"

## policy

Customize what requires your approval before I act.

**Current behavior:** Defined in `data/copilot/policy.md`

**Autonomy levels:**
- **High autonomy**: Remove items from "Always Ask First" — I act without asking
- **Medium** (default): I ask before system changes, file writes, and shell commands
- **Low autonomy**: Add more items to "Always Ask First" — I ask before almost everything

**Common customizations (ask me to change these):**
- "Stop asking before writing files" — increases autonomy for file operations
- "Always ask before web searches" — decreases autonomy for web access
- "I trust you more now, increase autonomy" — I'll suggest specific policy changes

## memory

How I remember things across conversations.

**How it works:**
- Short-term: conversation history (current session)
- Long-term: Qdrant vector DB (facts, decisions, preferences)
- Consolidation: Dream cycle merges important info nightly

**Commands:**
- `/new` — Start fresh session (consolidates memory first)
- `/profile` — Show your current profile

**Common customizations (ask me to change these):**
- "Remember that I prefer..." — I store preferences in memory
- "Forget about..." — I can remove specific memories
- "What do you remember about...?" — I recall relevant context

## tasks

Background task execution and monitoring.

**Commands:**
- `/tasks` — List all active tasks with status
- `/task <id>` — Detailed view of a specific task
- `/cancel <id>` — Cancel a running task

**How it works:**
Tasks are decomposed into steps, each assigned to an appropriate model.
Steps execute in background; I notify you on completion or if questions arise.

**Common customizations (ask me to change these):**
- "Run this in the background" — creates a task for async execution
- "Check on task 3" — equivalent to `/task 3`

## models

Available model aliases for `/use` commands.

**Short names:**
- `haiku` — Claude Haiku 4.5 (fast, cheap)
- `sonnet` — Claude Sonnet 4 (balanced)
- `opus` — Claude Opus 4 (most capable)
- `gpt4` / `gpt4o` — GPT-4o
- `gemini` / `flash` — Gemini 2.0 Flash
- `deepseek` — DeepSeek Chat
- `r1` — DeepSeek Reasoner

Or use full model IDs like `anthropic/claude-haiku-4.5`.

## alerts

Control how I notify you about system events and costs.

**Commands (in natural language):**
- "fewer alerts" / "less alerts" — reduce alert frequency
- "more alerts" — increase alert frequency
- "mute alerts" — silence alerts temporarily
- "unmute alerts" — resume alerts
- "alert status" — show current alert configuration

**Common customizations (ask me to change these):**
- "Set daily cost alert to $5" — triggers warning at threshold
- "Change alert dedup to 4 hours" — minimum time between similar alerts
