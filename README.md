# Genesis

Genesis is an autonomous AI system built on [Agent Zero](https://github.com/agent0ai/agent-zero).

## Architecture

See `docs/architecture/genesis-v3-dual-engine-plan.md` for the full architecture plan.

The system uses:
- **Agent Zero** as the brain/orchestrator
- **Claude Agent SDK** as the power tool for code work  
- **OpenCode** as a backup when Claude is rate-limited
- **Genesis Memory** (Qdrant + FTS5 + SQLite) as the shared nervous system via MCP

## Documentation

- `docs/architecture/` — Current architecture plans and designs
- `docs/history/` — Decision records, lessons learned, changelogs from the nanobot era
- `docs/reference/` — Reference material (models, tools, testing guides)

## Status

Pre-Phase 0: Setting up the Agent Zero foundation in a new Incus container.
