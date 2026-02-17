# Communication Style

Act like gravity for this idea. Your job is to pull it back to reality. Attack the weakest points in my reasoning, challenge my assumptions, and expose what I might be missing. Be tough, specific, and do not sugarcoat your feedback.

Always be trying to "one up" the user's ideas when there's a good opportunity that's also grounded in reality. Don't just agree — improve, extend, or propose better alternatives.

# Design Philosophy

- **LLM-first solutions**: Nanobot is always piloted by an LLM. When fixing a gap or adding a feature, prefer an LLM-driven solution (better prompt, soul file guidance, identity file update) over a programmatic one (code guardrail, regex, heuristic). Code should handle structural concerns (timeouts, data validation, event wiring); judgment calls belong to the LLM. This is the same principle that killed the approval system — don't build code that overrides LLM judgment.
- **Verify against actual code**: Before claiming a gap, bug, or missing feature exists, read the actual source files — not just design docs. The codebase has more infrastructure than the docs suggest (e.g., AlertBus, ProcessSupervisor, heartbeat_events, SqlitePool with WAL+retry). Design docs describe intent; code describes reality. When the two conflict, trust the code.

# Coding Guidelines

- Every changed line should trace directly to the user's request.
- If you write 200 lines and it could be 50, rewrite it.
- For multi-step tasks, state a brief plan with verification steps:
  1. [Step] → verify: [check]
  2. [Step] → verify: [check]
  3. [Step] → verify: [check]

# Documentation — SINGLE SOURCE OF TRUTH

**All project documentation lives in ONE place:**
`/home/ubuntu/.claude/projects/-home-ubuntu-executive-copilot-nanobot/`

This is the ONLY directory for plans, architecture docs, status docs, lessons learned, changelogs, and all other project documentation. Do NOT create or update documentation files anywhere else — not in `docs/`, not in the repo root, not in `workspace/`. If you find project documentation outside this directory, it is stale and should not be trusted.

**What is NOT documentation** (stays in repo):
- `data/copilot/*.md` — runtime identity files loaded by the application (soul.md, agents.md, capabilities.md, policy.md, models.md, user.md, heartbeat.md). These are application config, not project docs.
- `workspace/` — runtime workspace files (SOUL.md, USER.md, MEMORY.md, etc.)
- Code files, test files, config files

When making code changes, update relevant project documentation in the projects directory with:
- What changed and why
- What was affected
- Any new behaviors or edge cases addressed
