# Approval Lite + Resilience Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the deadlock-prone programmatic approval system with policy-in-prompt guardrails, add tool description annotations, and fix four resilience issues (CoT decay, wall-clock limit, reconnect backoff, graceful shutdown).

**Architecture:** Hard limits remain in code (ExecTool deny patterns, OutputSanitizer). Soft approvals move to a POLICY.md file loaded into the system prompt. The dead approval interceptor/queue/parser code is deleted. Four bonus resilience fixes harden the agent loop.

**Tech Stack:** Python 3.11+, asyncio, aiosqlite, pytest

---

### Task 1: Create POLICY.md

**Files:**
- Create: `data/copilot/policy.md`

**Step 1: Create the policy file**

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

**Step 2: Verify file exists**

Run: `cat data/copilot/policy.md | head -5`
Expected: Shows "# Action Policy"

**Step 3: Commit**

```bash
git add data/copilot/policy.md
git commit -m "feat(safety): add POLICY.md for LLM-driven soft approvals"
```

---

### Task 2: Load POLICY.md in System Prompt

**Files:**
- Modify: `nanobot/copilot/context/extended.py:208`

**Step 1: Write the failing test**

Create: `tests/copilot/context/test_policy_loading.py`

```python
"""Test that POLICY.md is loaded into the system prompt."""

import tempfile
from pathlib import Path

from nanobot.copilot.context.extended import ExtendedContextBuilder
from nanobot.agent.context import ContextBuilder


def test_policy_md_loaded_into_identity_docs(tmp_path):
    """POLICY.md should be loaded alongside soul.md, user.md, agents.md."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "soul.md").write_text("I am a helpful bot.")
    (docs_dir / "policy.md").write_text("# Action Policy\n\n## Always Ask First\n- Do X")

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    base = ContextBuilder(workspace)
    ext = ExtendedContextBuilder(base)
    ext._docs_dir = docs_dir
    ext._identity_cache = ""  # force reload

    result = ext._load_identity_docs()
    assert "Action Policy" in result
    assert "Always Ask First" in result


def test_policy_md_absent_no_error(tmp_path):
    """Missing POLICY.md should not cause errors."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "soul.md").write_text("I am a helpful bot.")

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    base = ContextBuilder(workspace)
    ext = ExtendedContextBuilder(base)
    ext._docs_dir = docs_dir
    ext._identity_cache = ""

    result = ext._load_identity_docs()
    assert "Action Policy" not in result
    # Should still have soul.md content
    assert "helpful bot" in result
```

**Step 2: Run test to verify it fails**

Run: `cd /home/ubuntu/executive-copilot/nanobot && python -m pytest tests/copilot/context/test_policy_loading.py -v`
Expected: FAIL — `test_policy_md_loaded_into_identity_docs` fails because "policy.md" is not in the file list

**Step 3: Add policy.md to identity docs loader**

Modify `nanobot/copilot/context/extended.py:208`. Change:

```python
        for fname in ("soul.md", "user.md", "agents.md"):
```

to:

```python
        for fname in ("soul.md", "user.md", "agents.md", "policy.md"):
```

**Step 4: Run test to verify it passes**

Run: `cd /home/ubuntu/executive-copilot/nanobot && python -m pytest tests/copilot/context/test_policy_loading.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add nanobot/copilot/context/extended.py tests/copilot/context/test_policy_loading.py
git commit -m "feat(safety): load POLICY.md into system prompt via identity docs"
```

---

### Task 3: Add Tool Description Annotations

**Files:**
- Modify: `nanobot/agent/tools/shell.py:44`
- Modify: `nanobot/agent/tools/filesystem.py:100-101`
- Modify: `nanobot/agent/tools/filesystem.py:143-144`
- Modify: `nanobot/agent/tools/message.py:37`

**Step 1: Update ExecTool description**

In `nanobot/agent/tools/shell.py:44`, change:

```python
        return "Execute a shell command and return its output. Use with caution."
```

to:

```python
        return "Execute a shell command and return its output. Per POLICY.md: ask user before commands that modify system state."
```

**Step 2: Update WriteFileTool description**

In `nanobot/agent/tools/filesystem.py:101`, change:

```python
        return "Write content to a file at the given path. Creates parent directories if needed."
```

to:

```python
        return "Write content to a file at the given path. Creates parent directories if needed. Per POLICY.md: ask user before writing outside memory/.md files."
```

**Step 3: Update EditFileTool description**

In `nanobot/agent/tools/filesystem.py:144`, change:

```python
        return "Edit a file by replacing old_text with new_text. The old_text must exist exactly in the file."
```

to:

```python
        return "Edit a file by replacing old_text with new_text. The old_text must exist exactly in the file. Per POLICY.md: ask user before editing outside memory/.md files."
```

**Step 4: Update MessageTool description**

In `nanobot/agent/tools/message.py:37`, change:

```python
        return "Send a message to the user. Use this when you want to communicate something."
```

to:

```python
        return "Send a message to the user. Per POLICY.md: ask user before messaging persons/channels other than the current user."
```

**Step 5: Run existing tests**

Run: `cd /home/ubuntu/executive-copilot/nanobot && python -m pytest tests/ -v --timeout=30 2>&1 | tail -20`
Expected: All existing tests pass

**Step 6: Commit**

```bash
git add nanobot/agent/tools/shell.py nanobot/agent/tools/filesystem.py nanobot/agent/tools/message.py
git commit -m "feat(safety): add POLICY.md annotations to tool descriptions"
```

---

### Task 4: Delete Dead Approval Code

**Files:**
- Delete: `nanobot/copilot/approval/` (entire directory)
- Delete: `tests/copilot/approval/` (entire directory)

**Step 1: Delete the approval module**

```bash
rm -rf nanobot/copilot/approval/
rm -rf tests/copilot/approval/
```

**Step 2: Verify no remaining imports**

Run: `cd /home/ubuntu/executive-copilot/nanobot && grep -r "from nanobot.copilot.approval" nanobot/ tests/ 2>/dev/null`
Expected: No output (no references remain)

**Step 3: Run tests to verify nothing breaks**

Run: `cd /home/ubuntu/executive-copilot/nanobot && python -m pytest tests/ -v --timeout=30 2>&1 | tail -20`
Expected: All tests pass

**Step 4: Commit**

```bash
git add -A nanobot/copilot/approval/ tests/copilot/approval/
git commit -m "chore: remove dead approval interceptor system (replaced by POLICY.md)"
```

---

### Task 5: Clean Up Config Fields

**Files:**
- Modify: `nanobot/copilot/config.py:97,180-183,244-245`
- Modify: `nanobot/cli/commands.py:605-606`
- Modify: `nanobot/config/loader.py:17`

**Step 1: Remove approval config fields**

In `nanobot/copilot/config.py`, remove these lines:

```python
    approval_slm_model: str = ""       # empty = use routing_model
```

(line 97)

```python
    # Approval system
    approval_channel: str = "whatsapp"
    approval_chat_id: str = ""  # User's WhatsApp LID; empty = same as sender
    approval_timeout: float = 300.0  # 5 minutes
```

(lines 180-183)

```python
    @property
    def resolved_approval_slm_model(self) -> str:
        return self.approval_slm_model or self.routing_model
```

(lines 244-245)

**Step 2: Update CostAlerter to use monitor_channel/monitor_chat_id**

In `nanobot/cli/commands.py:601-607`, change:

```python
        cost_alerter = CostAlerter(
            db_path, bus,
            config.copilot.daily_cost_alert,
            config.copilot.per_call_cost_alert,
            config.copilot.approval_channel,
            config.copilot.approval_chat_id,
        )
```

to:

```python
        cost_alerter = CostAlerter(
            db_path, bus,
            config.copilot.daily_cost_alert,
            config.copilot.per_call_cost_alert,
            config.copilot.monitor_channel,
            config.copilot.monitor_chat_id,
        )
```

**Step 3: Remove approval_chat_id from secrets list**

In `nanobot/config/loader.py:17`, remove `"approval_chat_id", "approvalChatId",` from the `_SECRET_KEYS` set.

**Step 4: Run tests**

Run: `cd /home/ubuntu/executive-copilot/nanobot && python -m pytest tests/ -v --timeout=30 2>&1 | tail -20`
Expected: All tests pass

**Step 5: Commit**

```bash
git add nanobot/copilot/config.py nanobot/cli/commands.py nanobot/config/loader.py
git commit -m "chore: remove unused approval config fields, use monitor_channel for cost alerts"
```

---

### Task 6: CoT Reflection Decay

**Files:**
- Modify: `nanobot/agent/loop.py:563-564,695-696`

**Step 1: Write the failing test**

Create: `tests/test_cot_decay.py`

```python
"""Test that CoT reflection prompt decays near max iterations."""


def test_cot_reflection_decays():
    """After max_iterations - 3, reflection should prompt wrap-up."""
    max_iterations = 10
    wind_down = max_iterations - 3

    # Simulate: early iterations get "Reflect" prompt
    for i in range(1, wind_down):
        prompt = _get_reflection_prompt(i, max_iterations)
        assert "Reflect" in prompt

    # Late iterations get "Summarize" prompt
    for i in range(wind_down, max_iterations + 1):
        prompt = _get_reflection_prompt(i, max_iterations)
        assert "Summarize" in prompt


def _get_reflection_prompt(iteration: int, max_iterations: int) -> str:
    """Mirror the logic that will be in loop.py."""
    if iteration >= max_iterations - 3:
        return "Summarize your findings and respond to the user."
    return "Reflect on the results and decide next steps."
```

**Step 2: Run test to verify it passes (logic test)**

Run: `cd /home/ubuntu/executive-copilot/nanobot && python -m pytest tests/test_cot_decay.py -v`
Expected: PASS (this validates the logic before we wire it)

**Step 3: Apply decay to agent loop**

In `nanobot/agent/loop.py`, replace both instances (lines 564 and 696) of:

```python
                messages.append({"role": "user", "content": "Reflect on the results and decide next steps."})
```

with:

```python
                if iteration >= self.max_iterations - 3:
                    messages.append({"role": "user", "content": "Summarize your findings and respond to the user."})
                else:
                    messages.append({"role": "user", "content": "Reflect on the results and decide next steps."})
```

**Step 4: Run all tests**

Run: `cd /home/ubuntu/executive-copilot/nanobot && python -m pytest tests/ -v --timeout=30 2>&1 | tail -20`
Expected: All tests pass

**Step 5: Commit**

```bash
git add nanobot/agent/loop.py tests/test_cot_decay.py
git commit -m "fix(loop): decay CoT reflection prompt near max iterations to prevent looping"
```

---

### Task 7: Wall-Clock Turn Time Limit

**Files:**
- Modify: `nanobot/agent/loop.py:57,492-497`

**Step 1: Add max_turn_time parameter**

In `nanobot/agent/loop.py`, add to `__init__` parameter list (after `llm_timeout` parameter around line 57):

```python
        max_turn_time: int = 300,
```

And in the body:

```python
        self._max_turn_time = max_turn_time
```

**Step 2: Add wall-clock check to agent loop**

In `nanobot/agent/loop.py`, after line 492 (`iteration = 0`), add:

```python
        turn_start = __import__('time').monotonic()
```

Inside the while loop, after `iteration += 1` (line 498), add:

```python
            # Wall-clock safety: prevent runaway turns
            if __import__('time').monotonic() - turn_start > self._max_turn_time:
                logger.warning(f"Turn exceeded {self._max_turn_time}s wall-clock limit")
                final_content = "I've been working on this for a while. Here's what I have so far — let me know if you'd like me to continue."
                break
```

Apply the same pattern to the second agent loop starting at line 654.

**Step 3: Run all tests**

Run: `cd /home/ubuntu/executive-copilot/nanobot && python -m pytest tests/ -v --timeout=30 2>&1 | tail -20`
Expected: All tests pass

**Step 4: Commit**

```bash
git add nanobot/agent/loop.py
git commit -m "fix(loop): add wall-clock turn time limit (300s default) to prevent runaway turns"
```

---

### Task 8: WhatsApp Reconnect Exponential Backoff

**Files:**
- Modify: `nanobot/channels/whatsapp.py:66-74`

**Step 1: Replace fixed delay with exponential backoff**

In `nanobot/channels/whatsapp.py`, replace lines 66-74:

```python
            except Exception as e:
                self._connected = False
                self._ws = None
                self._stop_all_composing()
                logger.warning(f"WhatsApp bridge connection error: {e}")

                if self._running:
                    logger.info("Reconnecting in 5 seconds...")
                    await asyncio.sleep(5)
```

with:

```python
            except Exception as e:
                self._connected = False
                self._ws = None
                self._stop_all_composing()
                logger.warning(f"WhatsApp bridge connection error: {e}")

                if self._running:
                    import random
                    delay = min(5 * (2 ** attempt) + random.uniform(0, 1), 120)
                    logger.info(f"Reconnecting in {delay:.1f}s (attempt {attempt + 1})...")
                    await asyncio.sleep(delay)
                    attempt += 1
```

Also add `attempt = 0` before the `while self._running:` loop, and reset `attempt = 0` after `self._connected = True` (line 54).

**Step 2: Run existing tests**

Run: `cd /home/ubuntu/executive-copilot/nanobot && python -m pytest tests/ -v --timeout=30 2>&1 | tail -20`
Expected: All tests pass

**Step 3: Commit**

```bash
git add nanobot/channels/whatsapp.py
git commit -m "fix(whatsapp): exponential backoff with jitter for reconnection (cap 120s)"
```

---

### Task 9: Graceful Task Cleanup on Stop

**Files:**
- Modify: `nanobot/agent/loop.py:226-229`

**Step 1: Make stop() async and cancel tracked tasks**

In `nanobot/agent/loop.py`, replace:

```python
    def stop(self) -> None:
        """Stop the agent loop."""
        self._running = False
        logger.info("Agent loop stopping")
```

with:

```python
    async def stop(self) -> None:
        """Stop the agent loop and cancel pending background tasks."""
        self._running = False
        if self._tracked_tasks:
            logger.info(f"Cancelling {len(self._tracked_tasks)} tracked tasks...")
            for task in self._tracked_tasks:
                task.cancel()
            await asyncio.gather(*self._tracked_tasks, return_exceptions=True)
            self._tracked_tasks.clear()
        logger.info("Agent loop stopped")
```

**Step 2: Update all callers of stop()**

Search for calls to `agent.stop()` or `loop.stop()` and ensure they `await` it. Check:

Run: `cd /home/ubuntu/executive-copilot/nanobot && grep -rn "\.stop()" nanobot/ | grep -v "__pycache__" | grep -v ".pyc"`

Update any synchronous calls to use `await`.

**Step 3: Run all tests**

Run: `cd /home/ubuntu/executive-copilot/nanobot && python -m pytest tests/ -v --timeout=30 2>&1 | tail -20`
Expected: All tests pass

**Step 4: Commit**

```bash
git add nanobot/agent/loop.py
git commit -m "fix(loop): graceful shutdown cancels and awaits tracked background tasks"
```

---

### Task 10: Final Verification

**Step 1: Run full test suite**

Run: `cd /home/ubuntu/executive-copilot/nanobot && python -m pytest tests/ -v --timeout=30`
Expected: All tests pass, no import errors

**Step 2: Verify no approval references remain**

Run: `cd /home/ubuntu/executive-copilot/nanobot && grep -r "ApprovalInterceptor\|approval_interceptor\|from nanobot.copilot.approval" nanobot/ tests/ 2>/dev/null`
Expected: No output

**Step 3: Verify POLICY.md is in identity docs list**

Run: `cd /home/ubuntu/executive-copilot/nanobot && grep "policy.md" nanobot/copilot/context/extended.py`
Expected: Shows `"policy.md"` in the file list

**Step 4: Verify tool descriptions have annotations**

Run: `cd /home/ubuntu/executive-copilot/nanobot && grep -n "POLICY.md" nanobot/agent/tools/*.py`
Expected: Shows 4 files with POLICY.md references

**Step 5: Commit any final adjustments**

```bash
git add -A
git commit -m "chore: final verification pass for approval-lite redesign"
```
