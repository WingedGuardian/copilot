# Project: Copilot

Built on the [nanobot](https://github.com/HKUDS/nanobot) framework (upstream fork), with extensive copilot/executive extensions.

**Repositories & remotes:**
- `public` → [WingedGuardian/copilot](https://github.com/WingedGuardian/copilot) — public-facing repo
- `origin` → WingedGuardian/nanobot-copilot-data — private backup
- `upstream` → HKUDS/nanobot — upstream fork source
- **No association with `WingedGuardian/Genesis`** — that is a separate project. Do NOT push to, reference, or create remotes for it from this repo.

**Local naming:**
- Local directory: `~/executive-copilot/nanobot/`
- Python package: `nanobot` (upstream name, kept permanently)
- Runtime data: `~/.nanobot/` (kept permanently)
- Internal code references to "nanobot" and "copilot" remain unchanged

# Communication Style

Act like gravity for this idea. Your job is to pull it back to reality. Attack the weakest points in my reasoning, challenge my assumptions, and expose what I might be missing. Be tough, specific, and do not sugarcoat your feedback.

Always be trying to "one up" the user's ideas when there's a good opportunity that's also grounded in reality. Don't just agree — improve, extend, or propose better alternatives.

# Design Philosophy

- **LLM-first solutions**: Nanobot is always piloted by an LLM. When fixing a gap or adding a feature, prefer an LLM-driven solution (better prompt, soul file guidance, identity file update) over a programmatic one (code guardrail, regex, heuristic). Code should handle structural concerns (timeouts, data validation, event wiring); judgment calls belong to the LLM. This is the same principle that killed the approval system — don't build code that overrides LLM judgment.
- **Verify against actual code**: Before claiming a gap, bug, or missing feature exists, read the actual source files — not just design docs. The codebase has more infrastructure than the docs suggest (e.g., AlertBus, ProcessSupervisor, heartbeat_events, SqlitePool with WAL+retry). Design docs describe intent; code describes reality. When the two conflict, trust the code.
- **API keys live in `~/.nanobot/secrets.json`** — NEVER check environment variables to determine if an API key is set. The `api_key: str = ""` defaults in Pydantic schemas are structural defaults that get populated from `secrets.json` at runtime. Empty string in the schema does NOT mean the key is missing. If you need to verify a key exists, read `secrets.json` directly (path: `providers.<name>.apiKey`).

# Branch Discipline

- **Never commit directly to main.** All work happens on feature branches (`feat/`, `fix/`, `refactor/`, `chore/` prefixes). Main only receives code through merges/PRs.
- **One logical change per branch.** Don't mix unrelated work. If a second concern emerges mid-branch, stash it or note it for the next branch.
- **Commit on branch → review diff → merge.** Every merge to main is a deliberate decision, not a side effect of working.
- **Use git worktrees for parallel independent work** when multiple tasks have no shared state or sequential dependencies.
- **After merging to main, push to BOTH remotes:**
  ```
  git push public main && git push origin main
  ```
  `public` = public-facing repo (WingedGuardian/copilot). `origin` = private backup (nanobot-copilot-data). Every merge to main gets pushed to both. No exceptions.

# Session Discipline

- **Session wrap-up ritual**: Before ending a session, produce a structured handoff: what changed, what's pending, what decisions were made, what was learned. This goes to the Local Changelog and Lessons Learned as appropriate.
- **Self-correction loop**: When the user corrects a mistake, extract the lesson and add it to Lessons Learned with a concrete rule. Corrections that stay in conversation context evaporate — persistent rules compound.

# Process Discipline

- **Pre-commit verification**: Before committing, verify the specific code path changed. Query the DB table you referenced. Hit the endpoint you modified. Trigger the feature you added. "It looks right" is not verification.
- **Commit scope**: Keep commits under ~10 files. If a change touches more, break it into sequential atomic commits that each independently work. Large surface area = large blast radius.
- **Loud failure default**: New `try/except` blocks in background services must call `get_alert_bus().alert()` or surface in `/status`. No silent `logger.warning` for conditions the user would want to know about. If you're catching an exception just to log it, that's a smell — either handle it or alert on it.
- **Stabilize before extending**: Don't start new features while the previous feature has uncommitted fixes or known broken paths. Finish the fix chain first.

# Coding Guidelines

- Every changed line should trace directly to the user's request.
- If you write 200 lines and it could be 50, rewrite it.
- For multi-step tasks, state a brief plan with verification steps:
  1. [Step] → verify: [check]
  2. [Step] → verify: [check]
  3. [Step] → verify: [check]

# Groundwork Code Protection

Code is sometimes written as **intentional foundational infrastructure** for a planned feature that isn't fully connected yet. This is deliberate forward-engineering, not dead code.

**When writing groundwork code:**
- Tag it with an inline comment: `# GROUNDWORK(<feature-id>): <why this exists>`
- Example: `# GROUNDWORK(post-v3-knowledge-base): Collection param enables future KB retrieval alongside memory`
- Example: `# GROUNDWORK(v3-authority-tags): source_type field lets LLM distinguish memory from reference material`
- The `<feature-id>` must correspond to a documented feature in the project docs directory

**When you encounter GROUNDWORK-tagged code:**
- **NEVER delete or refactor it as "dead code."** It exists because a previous session laid infrastructure for a planned feature.
- **NEVER remove the GROUNDWORK comment** — it's cross-session memory that explains why unused-looking code exists.
- If the code appears unused, check the project docs for the referenced `<feature-id>` before making any judgment.
- If you're unsure whether the feature is still planned, **ASK the user** rather than removing it.
- Only remove GROUNDWORK code if: (a) the feature it supports is now fully implemented (the code is active, remove only the tag), or (b) the user explicitly says the feature is cancelled.

**Why this matters:** Multi-session development means session N+1 has no memory of session N's intent. Without these tags, foundational code looks like dead code and gets cleaned up, destroying deliberate architectural preparation. This has happened multiple times — this rule prevents it.

# Documentation — SINGLE SOURCE OF TRUTH

**All project documentation lives in ONE place:**
`/home/ubuntu/.claude/projects/-home-ubuntu-executive-copilot-nanobot/`

This is the ONLY directory for plans, architecture docs, status docs, lessons learned, changelogs, and all other project documentation. Do NOT create or update documentation files anywhere else — not in `docs/`, not in the repo root, not in `workspace/`. If you find project documentation outside this directory, it is stale and should not be trusted.

**What is NOT documentation** (stays in repo):
- `data/copilot/*.md` — runtime identity files loaded by the application (heartbeat.md, help.md, models.md, router.md, dream.md, weekly.md, monthly.md). These are application config, not project docs.
- `workspace/` — runtime workspace files (SOUL.md, USER.md, MEMORY.md, etc.)
- Code files, test files, config files

When making code changes, update relevant project documentation in the projects directory with:
- What changed and why
- What was affected
- Any new behaviors or edge cases addressed

# Local Changelog

After committing code changes, append a one/two-line entry to `~/.nanobot/CHANGELOG.local`:
```
[YYYY-MM-DD HH:MM] claude-code: brief description of everything changed
```
This file is read by nanobot's heartbeat to stay aware of external codebase changes. Keep entries concise but with specific keywords needed to understand what was affected (one/two line per commit MAX).

# Periodic Services — Quick Reference

| Service | Class | File | Interval | LLM? | Purpose |
|---------|-------|------|----------|------|---------|
| **Heartbeat** | `HeartbeatService` | `nanobot/heartbeat/service.py` | 2h | YES | Reads HEARTBEAT.md, executes tasks via LLM agent (upstream — do not modify) |
| **Cognitive Heartbeat** | `CopilotHeartbeatService` | `nanobot/copilot/dream/cognitive_heartbeat.py` | 2h | YES | Subclass of HeartbeatService; adds dream observations, pending tasks, autonomy permissions, and morning brief to heartbeat prompt. Active when copilot mode is enabled. |
| **Health check** | `HealthCheckService` | `nanobot/copilot/dream/health_check.py` | 30min | **NO** | Programmatic HTTP pings, DB queries, changelog diff, alert management |
| **Monitor** | `MonitorService` | `nanobot/copilot/dream/monitor.py` | 5min | NO | State-transition alerting, self-heal |
| **Dream cycle** | `DreamCycle` | `nanobot/copilot/dream/cycle.py` | Nightly (cron) | YES | 13 jobs: consolidation, cost, lessons, backup, monitor, reconcile, zero-vectors, routing cleanup, budget check, reflection, identity evolution, observation cleanup, codebase indexing |
| **Recon cron jobs** | `CronService` | `data/copilot/recon.md` | Various (cron) | YES | 5 jobs: email recon (daily 5AM), web source (Fri 6AM), GitHub (Sat 6AM), model pool (Sun 6AM), source discovery (28th 4AM). Write to `recon_findings` table. |
| **Weekly review** | `DreamCycle._run_weekly_review()` | `nanobot/copilot/dream/cycle.py` | Sunday (cron) | YES | MANAGER role — architecture, memory, recon triage, costs |
| **Monthly review** | `DreamCycle._run_monthly_review()` | `nanobot/copilot/dream/cycle.py` | 1st of month (cron) | YES | DIRECTOR role — audits weekly, adjusts budgets, recon system audit |

**Rules:**
- When copilot mode is enabled, `CopilotHeartbeatService` replaces `HeartbeatService` — same 2h interval, extended with cognitive context (dream observations, pending tasks, autonomy permissions). Upstream `HeartbeatService` is **never modified** — changes go in the subclass.
- `HealthCheckService` is purely programmatic. If it needs intelligence, escalate to the heartbeat or dream cycle — never add an LLM call to it.
- Config key `heartbeat_model` is for heartbeat LLM calls. Config key `health_check_interval` is for `HealthCheckService`. Don't confuse them.
- Dream cycle `is_running` flag is checked by `CopilotHeartbeatService` before executing — if dream is running, tick is skipped (avoids concurrent `process_direct()` calls).
- Recon cron jobs are config-driven (created via `CronService` at runtime, not hardcoded). They read `data/copilot/recon.md` as their identity/watch list. All scheduled before the 7AM dream cycle with 1h gaps to avoid `process_direct()` contention. Weekly review triages recon findings; monthly review audits recon quality.
