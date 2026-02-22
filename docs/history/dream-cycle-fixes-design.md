# Dream Cycle & Routing Fixes Design

**[IMPLEMENTED/SUPERSEDED 2026-02-20 — Router V2]**

> **⚠️ File reference correction**: This doc references `nanobot/copilot/dream/heartbeat.py` — that file does not exist. The actual files are:
> - `cognitive_heartbeat.py` — LLM-powered `CopilotHeartbeatService` (2h, created Sentience Plan)
> - `health_check.py` — programmatic `HealthCheckService` (30min, contains `_check_unresolved_alerts`)
> The fix described (filtering lm_studio from `_check_unresolved_alerts`) was correctly applied to `health_check.py`.
> Naming chain: `CopilotHeartbeatService` (original programmatic) → `HealthMonitorService` (2026-02-19) → `HealthCheckService` (Router V2, moved to `health_check.py`). New `CopilotHeartbeatService` created in `cognitive_heartbeat.py` (Sentience Plan).

**Date:** 2026-02-19
**Status:** Approved
**Trigger:** Dream cycle reporting LM Studio alerts, $5.38/day from Opus routing, truncated reflection output

## Problem Statement

Three issues identified from dream cycle output:
1. Router's `big_model` defaults to Opus ($5/$25 per MTok), causing expensive routing for complexity-pattern matches and failover cascades
2. LM Studio (optional local infrastructure) generates alerts/noise across multiple recurring cycles when it's offline — which is its normal state most of the time
3. Dream cycle reflection truncated at 200 characters, cutting off actionable information

Additionally discovered: an import bug (`commands.py:989` imports `HealthMonitorService` but class is `CopilotHeartbeatService`) that would crash gateway startup.

## Design

### Change 1: big_model default Sonnet instead of Opus
- **File:** `nanobot/copilot/config.py:71`
- **Change:** `big_model: str = "anthropic/claude-opus-4.6"` → `"anthropic/claude-sonnet-4-6"`
- **Rationale:** Opus stays available via explicit config (`weekly_model`) or `/use`. Sonnet is the appropriate "big" tier for automatic routing — capable enough for complexity patterns, ~5x cheaper than Opus.

### Change 2: Fix import bug
- **File:** `nanobot/cli/commands.py:989`
- **Change:** Update import to match actual class name `CopilotHeartbeatService`
- **Rationale:** Runtime ImportError when copilot is enabled.

### Change 3: LM Studio silent in all recurring cycles

**Philosophy:** LM Studio is optional local infrastructure. When down, the failover chain silently skips it. No alert, no warning, no report entry. Just a debug log.

**5 touch points:**

| # | File | Location | What it does now | Fix |
|---|---|---|---|---|
| a | `failover.py:90` | `_fire_alert()` on circuit open | Fires `AlertBus.alert("llm", "medium", ...)` for lm_studio | Skip `_fire_alert` when provider name contains `"lm_studio"` |
| b | `cycle.py:319-332` | `_monitor_and_remediate()` | Adds all unhealthy subsystems to `DreamReport.alerts` | Filter out `"LM Studio"` subsystems |
| c | `cycle.py:514-524` | `_gather_reflection_context()` DB query | Queries ALL alerts from last 24h | Add `AND message NOT LIKE '%lm_studio%'` |
| d | `heartbeat.py:303-326` | `_check_unresolved_alerts()` DB query | Queries all unresolved high/medium alerts | Add `AND message NOT LIKE '%lm_studio%' AND message NOT LIKE '%LM Studio%'` |
| e | StatusAggregator | `_check_lm_studio()` | Runs on every `collect()` call | No change — `/status` (interactive) should still show LM Studio health |

### Change 4: Reflection character limit
- **File:** `nanobot/copilot/dream/cycle.py:451`
- **Change:** Truncation from 200 → 1000 characters
- **Rationale:** WhatsApp supports 4096 chars. Total dream summary rarely exceeds 1500 chars.

### Change 5: Test updates
- **File:** `tests/copilot/routing/test_heuristics.py`
- **Change:** Update any assertions that reference the old `big_model` default

### Change 6: Documentation
- Project CHANGELOG.md — entry for these changes
- `~/.nanobot/CHANGELOG.local` — entry after commit
- Copilot config comments — update big_model suggestions

## Files Modified (6)
1. `nanobot/copilot/config.py` — big_model default
2. `nanobot/cli/commands.py` — import fix
3. `nanobot/copilot/routing/failover.py` — suppress lm_studio alerts
4. `nanobot/copilot/dream/cycle.py` — filter LM Studio from Job 5 + Job 11, reflection limit
5. `nanobot/copilot/dream/heartbeat.py` — filter lm_studio from alert query
6. `tests/copilot/routing/test_heuristics.py` — update big_model assertion if needed

## What Stays the Same
- Router chain structure (local → fast → big → emergency) — correct architecture
- MonitorService `silent_subsystems={"LM Studio"}` — already correct
- HeartbeatService (`nanobot/heartbeat/service.py`) — no LM Studio references
- SLM queue drainer — silently checks LM Studio, no alerts
- StatusAggregator interactive behavior — `/status` still shows LM Studio health
- Weekly/monthly review prompts — don't hardcode LM Studio
