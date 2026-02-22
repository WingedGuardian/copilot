# Dream Cycle & Routing Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix routing cost (big_model Opus→Sonnet), silence LM Studio in all recurring cycles, fix truncated reflection, fix import bug.

**Architecture:** Six targeted edits across config, routing, dream cycle, and heartbeat. No structural changes — just fixing defaults, filtering optional infrastructure noise, and fixing a broken import.

**Tech Stack:** Python, asyncio, aiosqlite, pytest

---

### Task 1: Fix big_model default (Opus → Sonnet)

**Files:**
- Modify: `nanobot/copilot/config.py:71`

**Step 1: Change the default**

In `nanobot/copilot/config.py` line 71, change:
```python
big_model: str = "anthropic/claude-opus-4.6"
```
to:
```python
big_model: str = "anthropic/claude-sonnet-4-6"
```

Also update the comment block above it (lines 64-70) to list Sonnet as the default and Opus as an option:
```python
    #   "anthropic/claude-sonnet-4-6"          — strong reasoning, cost-effective (DEFAULT)
    #   "anthropic/claude-opus-4-6"            — most capable (use via weekly_model or /use)
    #   "openai/gpt-4o"                        — strong all-rounder
    #   "google/gemini-2.0-pro"                — large context window
    big_model: str = "anthropic/claude-sonnet-4-6"
```

**Step 2: Run existing tests to verify no breakage**

Run: `pytest tests/copilot/routing/test_heuristics.py -v`
Expected: All 15 tests PASS (tests use `classify()` directly with its own defaults, not CopilotConfig)

**Step 3: Commit**

```bash
git add nanobot/copilot/config.py
git commit -m "fix(routing): big_model default Opus→Sonnet to prevent cost escalation"
```

---

### Task 2: Fix import bug (HealthMonitorService → CopilotHeartbeatService)

**Files:**
- Modify: `nanobot/cli/commands.py:989`

**Step 1: Fix the import**

In `nanobot/cli/commands.py` line 989, change:
```python
from nanobot.copilot.dream.heartbeat import HealthMonitorService
```
to:
```python
from nanobot.copilot.dream.heartbeat import CopilotHeartbeatService
```

**Step 2: Fix the instantiation**

In `nanobot/cli/commands.py` line 1039, change:
```python
health_monitor = HealthMonitorService(
```
to:
```python
health_monitor = CopilotHeartbeatService(
```

**Step 3: Verify no other references to HealthMonitorService**

Run: `grep -rn "HealthMonitorService" nanobot/`
Expected: No matches remain.

**Step 4: Commit**

```bash
git add nanobot/cli/commands.py
git commit -m "fix(gateway): import CopilotHeartbeatService (was renamed, import not updated)"
```

---

### Task 3: Suppress lm_studio alerts in failover chain

**Files:**
- Modify: `nanobot/copilot/routing/failover.py:88-90`

**Step 1: Add lm_studio guard to circuit breaker alert**

In `nanobot/copilot/routing/failover.py`, the `record_failure` method at line 88-90 currently reads:
```python
        elif len(s["failures"]) >= self._failure_threshold:
            s["state"] = "open"
            s["opened_at"] = now
            logger.warning(f"CircuitBreaker: {name} -> open ({len(s['failures'])} failures in {self._window_s}s)")
```

This is followed by the half-open probe failure path at lines 85-90:
```python
        if s["state"] == "half-open":
            # Probe failed -> back to open
            s["state"] = "open"
            s["opened_at"] = now
            logger.warning(f"CircuitBreaker: {name} -> open (probe failed)")
            _fire_alert(f"LLM provider '{name}' circuit opened")
        elif len(s["failures"]) >= self._failure_threshold:
            s["state"] = "open"
            s["opened_at"] = now
            logger.warning(f"CircuitBreaker: {name} -> open ({len(s['failures'])} failures in {self._window_s}s)")
```

Change the `_fire_alert` call at line 90 to skip lm_studio:
```python
        if s["state"] == "half-open":
            s["state"] = "open"
            s["opened_at"] = now
            logger.warning(f"CircuitBreaker: {name} -> open (probe failed)")
            if "lm_studio" not in name:
                _fire_alert(f"LLM provider '{name}' circuit opened")
        elif len(s["failures"]) >= self._failure_threshold:
            s["state"] = "open"
            s["opened_at"] = now
            logger.warning(f"CircuitBreaker: {name} -> open ({len(s['failures'])} failures in {self._window_s}s)")
```

Note: The `logger.warning` stays — it's log-level output, not user-facing. Only the AlertBus alert is suppressed.

**Step 2: Commit**

```bash
git add nanobot/copilot/routing/failover.py
git commit -m "fix(routing): suppress AlertBus alert for lm_studio circuit opens (optional infra)"
```

---

### Task 4: Filter LM Studio from dream cycle + fix reflection limit

**Files:**
- Modify: `nanobot/copilot/dream/cycle.py` (3 changes)

**Step 1: Filter LM Studio from Job 5 (_monitor_and_remediate)**

In `nanobot/copilot/dream/cycle.py` lines 319-332, the current code:
```python
    async def _monitor_and_remediate(self) -> dict:
        if not self._status:
            return {"alerts": [], "remediations": 0}

        report = await self._status.collect()
        alerts = []
        remediations = 0

        for sub in report.subsystems:
            if not sub.healthy:
                alerts.append(f"{sub.name}: {sub.details}")

        return {"alerts": alerts, "remediations": remediations}
```

Change the loop to filter LM Studio:
```python
        for sub in report.subsystems:
            if not sub.healthy and sub.name != "LM Studio":
                alerts.append(f"{sub.name}: {sub.details}")
```

**Step 2: Filter lm_studio alerts from Job 11 (_gather_reflection_context)**

In `nanobot/copilot/dream/cycle.py` lines 514-524, the current DB query:
```python
                    cur = await db.execute(
                        """SELECT severity, subsystem, message FROM alerts
                           WHERE timestamp > datetime('now', '-1 day')
                           ORDER BY timestamp DESC LIMIT 5"""
                    )
```

Change to exclude lm_studio alerts:
```python
                    cur = await db.execute(
                        """SELECT severity, subsystem, message FROM alerts
                           WHERE timestamp > datetime('now', '-1 day')
                             AND message NOT LIKE '%lm_studio%'
                             AND message NOT LIKE '%LM Studio%'
                           ORDER BY timestamp DESC LIMIT 5"""
                    )
```

**Step 3: Increase reflection character limit**

In `nanobot/copilot/dream/cycle.py` line 451, change:
```python
            if len(text) > 200:
                text = text[:197] + "..."
```
to:
```python
            if len(text) > 1000:
                text = text[:997] + "..."
```

**Step 4: Commit**

```bash
git add nanobot/copilot/dream/cycle.py
git commit -m "fix(dream): filter LM Studio from alerts/reflection, increase reflection limit to 1000 chars"
```

---

### Task 5: Filter lm_studio from CopilotHeartbeatService alert query

**Files:**
- Modify: `nanobot/copilot/dream/heartbeat.py` (lines 303-326)

**Step 1: Update the _check_unresolved_alerts query**

In `nanobot/copilot/dream/heartbeat.py`, the `_check_unresolved_alerts` method queries:
```python
                cur = await db.execute(
                    """SELECT severity, message FROM alerts
                       WHERE timestamp > datetime('now', '-4 hours')
                         AND severity IN ('high', 'medium')
                         AND resolved_at IS NULL
                       ORDER BY timestamp DESC LIMIT 5""",
                )
```

Change to exclude lm_studio alerts:
```python
                cur = await db.execute(
                    """SELECT severity, message FROM alerts
                       WHERE timestamp > datetime('now', '-4 hours')
                         AND severity IN ('high', 'medium')
                         AND resolved_at IS NULL
                         AND message NOT LIKE '%lm_studio%'
                         AND message NOT LIKE '%LM Studio%'
                       ORDER BY timestamp DESC LIMIT 5""",
                )
```

**Step 2: Commit**

```bash
git add nanobot/copilot/dream/heartbeat.py
git commit -m "fix(heartbeat): filter lm_studio alerts from unresolved alert check"
```

---

### Task 6: Documentation + final verification

**Files:**
- Modify: `~/.claude/projects/-home-ubuntu-executive-copilot-nanobot/CHANGELOG.md`
- Modify: `~/.nanobot/CHANGELOG.local`

**Step 1: Run all routing tests**

Run: `pytest tests/copilot/routing/ -v`
Expected: All tests PASS.

**Step 2: Verify no remaining HealthMonitorService references**

Run: `grep -rn "HealthMonitorService" nanobot/`
Expected: No matches.

**Step 3: Verify LM Studio filter completeness**

Run: `grep -rn "_fire_alert\|lm_studio.*alert\|LM Studio.*alert" nanobot/copilot/`
Expected: Only the guarded `_fire_alert` in failover.py and filtered queries in cycle.py/heartbeat.py.

**Step 4: Update project CHANGELOG.md**

Append entry to `/home/ubuntu/.claude/projects/-home-ubuntu-executive-copilot-nanobot/CHANGELOG.md`:
```
## 2026-02-19 — Dream Cycle & Routing Fixes

- **Routing:** Changed `big_model` default from Opus to Sonnet — prevents $5+/day routing cost escalation
- **LM Studio:** Silenced in all recurring cycles (dream, heartbeat, monitor). Optional infrastructure no longer generates alerts or appears in dream reports. Still visible in interactive `/status`.
- **Dream reflection:** Increased character limit from 200 to 1000 chars — full reflection now delivered to WhatsApp
- **Bug fix:** Fixed import of CopilotHeartbeatService (was HealthMonitorService, would crash gateway startup)
```

**Step 5: Update CHANGELOG.local**

Append to `~/.nanobot/CHANGELOG.local`:
```
[2026-02-19 HH:MM] claude-code: routing big_model Opus→Sonnet, LM Studio silenced in dream/heartbeat/failover, reflection limit 200→1000, fixed CopilotHeartbeatService import
```

**Step 6: Final commit (docs only)**

```bash
git add -A  # only doc changes at this point
git commit -m "docs: changelog for dream cycle & routing fixes"
```
