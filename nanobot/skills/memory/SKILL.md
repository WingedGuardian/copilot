---
name: memory
description: Memory tool reference — search, store, and stats actions.
always: false
---

# Memory Tool Reference

## Actions

### search
Find memories across all stored data (semantic + keyword).
```
memory(action="search", query="user's timezone preference")
```

### store
Persist a fact to all backends (SQLite + Qdrant + FTS5). Immediately searchable.
```
memory(action="store", category="fact", content="User prefers dark mode")
memory(action="store", category="preference", content="Communication style: direct and concise")
memory(action="store", category="entity", content="Alice is the project lead for Nexus")
```

### stats
Check memory system health and counts.
```
memory(action="stats")
```

## When to Use

- **Search** before claiming you don't know something
- **Store** user preferences, project context, and key decisions immediately
- MEMORY.md is a lean scratchpad (active goals/blockers only) — facts go to `memory store`
