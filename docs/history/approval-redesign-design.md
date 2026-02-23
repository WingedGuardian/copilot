# Approval System Redesign: "Approval Lite"

**Date:** 2026-02-15
**Status:** Approved
**Author:** Claude + User

## Problem

The programmatic approval system (`nanobot/copilot/approval/`) was designed to intercept tool calls, send approval requests to WhatsApp, and block execution until the user responded. This architecture has a fundamental deadlock: the LLM blocks waiting for approval, but the approval message can't be delivered because the LLM response is still "in progress." The user never sees the request, the timeout fires, and the approval auto-denies. The system was fully built but never successfully integrated — it was disconnected from the agent loop to prevent crashes.

## Design Principles

1. **Nothing blocks the agent loop.** No async waits, no event draining, no bus consumption during tool execution.
2. **Hard limits are silent and instant.** Truly dangerous commands (rm -rf, secrets access) are blocked by code and return an error string. The LLM adapts.
3. **Soft approvals are conversational.** The LLM is told via system prompt what requires confirmation. It asks the user naturally. The user responds naturally.
4. **Self-correcting.** If the LLM violates policy, the existing SatisfactionDetector + LessonManager loop catches it and creates lessons injected into future prompts.
5. **User can say anything.** No input is ever blocked, swallowed, or misinterpreted by a regex parser.

## Architecture

```
User Message -> Agent Loop -> LLM generates tool call
                                    |
                    +---------------+---------------+
                    |               |               |
              Hard Limit?     Policy says      No restrictions
              (code gate)     "ask first"?     -> execute
                    |          (LLM decides)
                    |               |
              Return error    LLM asks user
              to LLM         in conversation
              (no hang)       (no hang)
```

## Changes

### 1. Create POLICY.md

New file at `{workspace}/POLICY.md`, loaded into system prompt alongside SOUL.md and USER.md.

```markdown
# Action Policy

## Always Ask First
Before taking these actions, describe what you plan to do and ask for confirmation:
- Writing or modifying files outside of the memory system and related .md files
- Running shell commands that modify system state (install packages, change configs)
- Sending messages to persons or channels other than the user
- Any action involving credentials, API keys, or secrets
- Git operations (commit, push, branch delete)

## Always Allowed (No Confirmation Needed)
- Reading files
- Searching the web
- Memory operations (remember, search)
- Listing files/directories
- Running read-only shell commands (ls, cat, grep, ps, etc.)
- Responding to the user in conversation

## If Blocked
If a tool returns "Error: Command blocked by safety guard", explain what happened
and suggest an alternative approach. Do not try to work around safety guards.
```

### 2. Load POLICY.md in System Prompt

`ExtendedContextBuilder._load_identity_docs()` already loads `soul.md`, `user.md`, `agents.md` from the copilot docs directory. Add `policy.md` to this list. No new mechanism needed.

### 3. Tool Description Annotations

Add a one-line policy reference to tool descriptions that require confirmation:
- `ExecTool`: "Per POLICY.md: ask user before commands that modify system state."
- `WriteFileTool`: "Per POLICY.md: ask user before writing outside memory/.md files."
- `MessageTool`: "Per POLICY.md: ask user before messaging persons/channels other than the user."

### 4. Delete Dead Approval Code

Remove the entire `nanobot/copilot/approval/` directory:
- `interceptor.py` (242 lines)
- `patterns.py` (247 lines)
- `queue.py` (199 lines)
- `parser.py` (109 lines)
- `__init__.py`

### 5. Clean Up Config

Remove unused fields from `CopilotConfig`:
- `approval_channel`
- `approval_chat_id`
- `approval_timeout`
- `approval_slm_model` / `resolved_approval_slm_model`

Remove any remaining references in `commands.py`.

### 6. Resilience Fixes (Bonus)

#### 6a. CoT Reflection Decay

In `loop.py`, the reflection prompt `"Reflect on the results and decide next steps."` is injected after every tool call. After `max_iterations - 3`, switch to `"Summarize your findings and respond to the user."` to prevent infinite looping.

#### 6b. Wall-Clock Turn Time Limit

Add `max_turn_time` (default 300s) to the agent loop. Check `time.monotonic()` at the top of each iteration. If exceeded, break with a wrap-up message.

#### 6c. WhatsApp Reconnect Backoff

Replace fixed `await asyncio.sleep(5)` with exponential backoff: `delay = min(5 * 2^attempt + random(0,1), 120)`. Reset on successful connection.

#### 6d. Graceful Task Cleanup on Stop

In `AgentLoop.stop()`, cancel all tracked tasks and `await asyncio.gather(*tasks, return_exceptions=True)`.

## What Already Works (No Changes)

- `ExecTool._guard_command()` — hard blocks dangerous shell patterns
- `OutputSanitizer` — flags prompt injection in tool output
- `_audit_log()` — records every tool execution to SQLite
- `SatisfactionDetector` — catches user frustration, creates lessons
- `LessonManager` — injects learned lessons into future prompts
- `CircuitBreaker` + `FailoverChain` — provider resilience

## Guarantees

1. Zero hangs — no async blocking, no event waiting, no deadlocks
2. Zero crashes from approval system — it no longer exists
3. User can say anything — no input is ever blocked or swallowed
4. Truly dangerous actions blocked silently — rm -rf never executes
5. Soft approvals via conversation — LLM asks naturally, user responds naturally
6. Self-correcting — lessons learned from violations improve future behavior
7. Bounded execution — wall-clock limit prevents runaway turns
8. Clean shutdown — no lost background tasks

## Research Sources

- [MAST: Multi-Agent System Failure Taxonomy (UC Berkeley)](https://arxiv.org/abs/2503.13657)
- [Architecting Resilient LLM Agents](https://arxiv.org/abs/2509.08646)
- [Retries, Fallbacks, and Circuit Breakers (Portkey)](https://portkey.ai/blog/retries-fallbacks-and-circuit-breakers-in-llm-apps/)
- [LLM Guardrails Best Practices (Datadog)](https://www.datadoghq.com/blog/llm-guardrails-best-practices/)
- [AutoGPT Ungraceful Crash Issue #2937](https://github.com/Significant-Gravitas/AutoGPT/issues/2937)
- [AG2 Async Deadlock Issue #2144](https://github.com/ag2ai/ag2/issues/2144)
- [Asyncio Deadlocks in Python](https://superfastpython.com/asyncio-deadlock/)
