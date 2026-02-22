# nanobot-copilot

A fork of [nanobot](https://github.com/HKUDS/nanobot) with executive AI copilot extensions: autonomous memory, routing, dream cycles, task management, cost tracking, and more.

## Design Philosophy

- **LLM-first solutions**: Prefer prompt-driven approaches (better system prompts, identity file guidance) over programmatic guardrails (regex, heuristics, code overrides). Code handles structural concerns (timeouts, data validation, event wiring); judgment calls belong to the LLM.
- **Verify against actual code**: Before claiming a gap or missing feature, read the actual source — not just design docs. The codebase has more infrastructure than docs suggest.
- **API keys live in `~/.nanobot/secrets.json`**: Never check environment variables to determine if an API key is set. The `api_key: str = ""` defaults in Pydantic schemas are structural defaults populated from `secrets.json` at runtime.

## Coding Guidelines

- Every changed line should trace directly to the task at hand.
- If you write 200 lines and it could be 50, rewrite it.
- New `try/except` blocks in background services must surface errors loudly (AlertBus, `/status`, or logs). No silent `logger.warning` for conditions the user would want to know about.
- Keep commits under ~10 files. If a change touches more, break it into atomic commits.

## Architecture

The copilot extensions live in `nanobot/copilot/` and hook into the core nanobot agent loop:

- `memory/` — Hybrid recall: Qdrant vectors + SQLite FTS5, multi-factor scoring via Reciprocal Rank Fusion
- `routing/` — RouterProvider V2: circuit breaker, self-escalation, multi-provider failover
- `dream/` — Nightly dream cycle (13 jobs), cognitive heartbeat (2h), health check (30min), monitor (5min)
- `tasks/` — Task decomposition, navigator duo peer review, retrospectives
- `cost/` — Per-model token tracking, budget enforcement, cost reporting
- `alerting/` — Severity-aware alerts with deduplication and cooldown
- `extraction/` — Background structured fact extraction with SLM fallback
- `metacognition/` — Confidence-based lesson manager with decay/reinforcement
- `slm_queue/` — SQLite-backed durable async work queue
- `status/` — Unified system health dashboard
- `context/` — Extended context builder (identity files, episodic memory, situational briefing)

## Identity Files

Runtime identity files in `data/copilot/`:
- `heartbeat.md` — Cognitive heartbeat instructions
- `dream.md` — Dream cycle job definitions
- `weekly.md` — Weekly review (MANAGER role)
- `monthly.md` — Monthly review (DIRECTOR role)
- `recon.md` — AI landscape reconnaissance jobs
- `router.md` — Routing logic instructions
- `navigator.md` — Navigator duo instructions
- `models.md` — Model registry reference
