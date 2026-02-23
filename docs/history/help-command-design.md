# /help Command Design

**Date:** 2026-02-17
**Status:** Approved
**Approach:** Hybrid (static commands + dynamic tips + file-based customizations guide)

## Problem

Nanobot has no discoverability mechanism. Users don't know what commands exist, what customizations are available, or how to get more out of the system. The existing `/help` handler (loop.py:311-313) returns a flat list of commands with no context, tips, or drill-down capability.

## Design

### Command Syntax

- `/help` — Summary: commands + top tips + available topics
- `/help <topic>` — Detailed section from help.md (e.g., `/help routing`, `/help policy`)
- Unknown topic — List available topics

### Architecture

```
User types: /help [topic]
    |
loop.py intercepts slash command
    |
    +-- _build_help_response(topic, session)
         |
         +-- topic is None:
         |     +-- Static commands list
         |     +-- Dynamic tips (from copilot_config + session state)
         |     +-- Available topics list
         |
         +-- topic is set:
               +-- Load data/copilot/help.md
               +-- Extract matching ## section
               +-- Return section content (or "topic not found")
```

### Files Changed

1. **`nanobot/agent/loop.py`** — Replace static `/help` handler with call to `_build_help_response()`. New private method (~40 lines).
2. **`data/copilot/help.md`** — New file. Topic-based help content for customizations, routing, policy, memory, tasks, models.

### Risk Mitigation

- If `help.md` is missing or unreadable: fall back to static commands-only output
- If `copilot_config` is None (copilot disabled): show commands only, skip tips
- No LLM calls, no async concerns, no routing/extraction interaction
- Helper method keeps slash command block clean

### Content Structure (help.md)

Sections (## headers) map directly to `/help <topic>`:
- **routing** — Model switching, provider overrides, auto-routing
- **policy** — Autonomy levels, POLICY.md customization
- **memory** — Long-term storage, recall, dream cycle consolidation
- **tasks** — Background task execution, monitoring
- **models** — Available models, aliases, selection guide
- **alerts** — Alert frequency, muting, cost alerts

### Dynamic Tips

Generated from runtime state, shown in `/help` summary:
- Local model availability
- Active routing override
- Task system status
- Dream cycle schedule
- Memory system status
- Private mode state
