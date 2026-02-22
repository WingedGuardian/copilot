# V1 Completion Plan

> V1 = fully functional reactive assistant with memory, self-maintenance, intelligent routing, and cost tracking. All the code exists. This plan makes it run.

---

## Key Finding

The memory system and dream cycle are **fully implemented** (~2000 lines of real code), not scaffolding. They silently degrade to no-ops because of two issues:
1. `qdrant-client` and `redis` not declared in `pyproject.toml` (import fails → graceful degradation → no memory)
2. ProcessSupervisor bug: fire-and-forget `start()` methods return immediately, supervisor interprets this as a crash, restarts 5 times, gives up

Infrastructure is already running: QDrant (localhost:6333), Redis (localhost:6379), LM Studio (192.168.50.100:1234).

---

## Changes Made

### 1. Declared missing dependencies ✅
**File:** `pyproject.toml`

Added: `qdrant-client>=1.7.0`, `redis>=5.0.0`, `openai>=1.0.0`, `aiosqlite>=0.19.0`

### 2. Fixed ProcessSupervisor false crash detection ✅
**File:** `nanobot/copilot/dream/supervisor.py`

Updated `register()` to accept optional `get_task_fn` parameter. Updated `_run_service()` to await the service's internal long-running task after `start()` returns, keeping the supervisor wrapper alive for the health loop.

### 3. Eliminated double-start of supervised services ✅
**File:** `nanobot/cli/commands.py`

Removed explicit `await xxx.start()` calls for services registered with the supervisor. The supervisor handles starting them via `_run_service()`. Updated `register()` calls to pass task accessors (`lambda: xxx._task`).

### 4. Scheduled the dream cycle ✅
**File:** `nanobot/cli/commands.py`

Added `_dream_scheduler()` async loop using `croniter` to consume `dream_cron_expr` config (default: `"0 3 * * *"` = 3 AM nightly). Started as `asyncio.create_task()` in the `run()` function.

### 5. Added memory init retry ✅
**File:** `nanobot/cli/commands.py`

Added 3 retries with 2s delay for `memory_manager.initialize()` to handle transient QDrant/Redis startup delays. Falls back to degraded mode after all retries fail.

---

## Still Needed (User Action)

### 6. Configure a cloud API key
**File:** `~/.nanobot/config.json`

Set at least `providers.openrouter.apiKey` (or another cloud provider). Without this:
- Dream cycle at 3 AM will fail if Windows PC / LM Studio is off
- No cloud fallback for complex queries
- Self-escalation has nowhere to escalate to

### 7. End-to-end verification

1. `nanobot gateway -v` — all green checkmarks, no supervisor restart warnings
2. Send message via WhatsApp → check QDrant for stored memory
3. Start new session → ask about previous topic → verify memory recall
4. Trigger dream cycle (temporarily set cron to `"*/2 * * * *"`) → check `dream_cycle_log` table
5. Stop Redis → verify monitor alerts → restart Redis → verify recovery notification
6. Send `/status` → verify dashboard shows memory stats

---

## Summary

| Change | File | Lines |
|---|---|---|
| Add 4 dependencies | `pyproject.toml` | +4 |
| Fix supervisor + register API | `copilot/dream/supervisor.py` | ~15 changed |
| Remove double-starts, add dream scheduler, add memory retry | `cli/commands.py` | ~30 changed |
| Configure cloud API key | `~/.nanobot/config.json` | 1 (user action) |

**Total: ~50 lines changed across 3 files. No new files. No new features. Just making existing code run.**
