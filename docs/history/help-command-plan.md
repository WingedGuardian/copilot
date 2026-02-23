# /help Command Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

> **⚠️ Stale markers (2026-02-20)**:
> - **`heartbeat_interval` config key**: Any dynamic tips code in this plan that checks `hasattr(copilot_config, "heartbeat_interval")` is wrong. The key was renamed to `health_check_interval` in Router V2.
> - **Old tier routing model**: The help content in Task 1 describes `/use fast`, `/use local`, tier-based routing. These tier names (`local`, `fast`, `cloud`) are from the heuristic router, which was replaced by Router V2 plan-based routing (`PlanRoutingTool`). The help content has been updated in `data/copilot/help.md` to reflect plan-based routing.
> - **Implementation status unclear**: No CHANGELOG entry for the `/help` command implementation. If not yet shipped, this plan needs updating before execution.

**Goal:** Replace the static `/help` handler in loop.py with an adaptive help system that shows commands, dynamic tips, and drill-down topic details from `data/copilot/help.md`.

**Architecture:** Slash command handler calls `_build_help_response(topic, session)` which combines static command list, dynamic tips from copilot config/state, and topic sections parsed from `help.md`. Falls back gracefully when copilot is disabled or help.md is missing.

**Tech Stack:** Python, Pydantic (existing config), pytest

---

### Task 1: Write help.md content file

**Files:**
- Create: `data/copilot/help.md`

**Step 1: Create help.md with topic sections**

```markdown
# Help Topics

## routing

Control which models handle your requests.

**Commands:**
- `/use <provider>` — Switch to a specific provider (e.g., `/use venice`)
- `/use <provider> fast` — Use the fast/cheap tier
- `/use <provider> <model>` — Use a specific model (e.g., `/use openrouter gpt4o`)
- `/use auto` — Return to automatic routing
- `/private` — Local-only mode (no cloud calls)

**Common customizations (ask me to change these):**
- Switch default model — "change my default model to claude-sonnet-4"
- Adjust escalation — "disable self-escalation" or "enable escalation"
- Change fast model — "use gemini-flash as my fast model"

## policy

Customize what requires your approval before I act.

**Current behavior:** Defined in `data/copilot/policy.md`

**Autonomy levels:**
- **High autonomy**: Remove items from "Always Ask First" — I act without asking
- **Medium** (default): I ask before system changes, file writes, and shell commands
- **Low autonomy**: Add more items to "Always Ask First" — I ask before almost everything

**Common customizations (ask me to change these):**
- "Stop asking before writing files" — increases autonomy for file operations
- "Always ask before web searches" — decreases autonomy for web access
- "I trust you more now, increase autonomy" — I'll suggest specific policy changes

## memory

How I remember things across conversations.

**How it works:**
- Short-term: conversation history (current session)
- Long-term: Qdrant vector DB (facts, decisions, preferences)
- Consolidation: Dream cycle merges important info nightly

**Commands:**
- `/new` — Start fresh session (consolidates memory first)
- `/profile` — Show your current profile

**Common customizations (ask me to change these):**
- "Remember that I prefer..." — I store preferences in memory
- "Forget about..." — I can remove specific memories
- "What do you remember about...?" — I recall relevant context

## tasks

Background task execution and monitoring.

**Commands:**
- `/tasks` — List all active tasks with status
- `/task <id>` — Detailed view of a specific task
- `/cancel <id>` — Cancel a running task

**How it works:**
Tasks are decomposed into steps, each assigned to an appropriate model.
Steps execute in background; I notify you on completion or if questions arise.

**Common customizations (ask me to change these):**
- "Run this in the background" — creates a task for async execution
- "Check on task 3" — equivalent to `/task 3`

## models

Available model aliases for `/use` commands.

**Short names:**
- `haiku` — Claude Haiku 4.5 (fast, cheap)
- `sonnet` — Claude Sonnet 4 (balanced)
- `opus` — Claude Opus 4 (most capable)
- `gpt4` / `gpt4o` — GPT-4o
- `gemini` / `flash` — Gemini 2.0 Flash
- `deepseek` — DeepSeek Chat
- `r1` — DeepSeek Reasoner

Or use full model IDs like `anthropic/claude-haiku-4.5`.

## alerts

Control how I notify you about system events and costs.

**Commands (in natural language):**
- "fewer alerts" / "less alerts" — reduce alert frequency
- "more alerts" — increase alert frequency
- "mute alerts" — silence alerts temporarily
- "unmute alerts" — resume alerts
- "alert status" — show current alert configuration

**Common customizations (ask me to change these):**
- "Set daily cost alert to $5" — triggers warning at threshold
- "Change alert dedup to 4 hours" — minimum time between similar alerts
```

**Step 2: Verify file is readable**

Run: `python -c "from pathlib import Path; p = Path('data/copilot/help.md'); print(f'OK: {len(p.read_text())} chars, {p.read_text().count(chr(10))} lines')"`
Expected: OK with char/line count

**Step 3: Commit**

```bash
git add data/copilot/help.md
git commit -m "docs: add help.md for adaptive /help command topics"
```

---

### Task 2: Write tests for help response builder

**Files:**
- Create: `tests/test_help_command.py`

**Step 1: Write failing tests**

```python
"""Tests for /help command response builder."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock


def _make_agent_loop(**overrides):
    """Create a minimal AgentLoop-like object for testing _build_help_response."""
    from types import SimpleNamespace

    defaults = {
        "_copilot_config": None,
        "_memory_manager": None,
        "_task_manager": None,
        "provider": MagicMock(),
        "workspace": Path("/tmp/test-workspace"),
    }
    defaults.update(overrides)

    # Import the actual method
    from nanobot.agent.loop import AgentLoop

    # We'll test the static helper directly
    return defaults


class TestBuildHelpResponse:
    """Test _build_help_response helper."""

    def test_no_topic_returns_commands(self):
        """Default /help shows commands list."""
        from nanobot.agent.loop import _build_help_response
        result = _build_help_response(topic=None, copilot_config=None, session_meta={}, help_md_dir=None)
        assert "/new" in result
        assert "/status" in result
        assert "/tasks" in result
        assert "/help" in result

    def test_no_topic_shows_available_topics(self):
        """Default /help lists available drill-down topics."""
        from nanobot.agent.loop import _build_help_response
        result = _build_help_response(topic=None, copilot_config=None, session_meta={}, help_md_dir=None)
        assert "routing" in result.lower()
        assert "policy" in result.lower()

    def test_known_topic_returns_section(self, tmp_path):
        """Known topic returns matching section from help.md."""
        help_md = tmp_path / "help.md"
        help_md.write_text("# Help\n\n## routing\n\nRouting details here.\n\n## policy\n\nPolicy details here.\n")

        from nanobot.agent.loop import _build_help_response
        result = _build_help_response(topic="routing", copilot_config=None, session_meta={}, help_md_dir=str(tmp_path))
        assert "Routing details here" in result
        assert "Policy details" not in result

    def test_unknown_topic_lists_available(self, tmp_path):
        """Unknown topic shows error with available topics."""
        help_md = tmp_path / "help.md"
        help_md.write_text("# Help\n\n## routing\n\nDetails.\n\n## policy\n\nDetails.\n")

        from nanobot.agent.loop import _build_help_response
        result = _build_help_response(topic="banana", copilot_config=None, session_meta={}, help_md_dir=str(tmp_path))
        assert "banana" in result.lower() or "not found" in result.lower()
        assert "routing" in result
        assert "policy" in result

    def test_missing_help_md_fallback(self):
        """Missing help.md falls back gracefully."""
        from nanobot.agent.loop import _build_help_response
        result = _build_help_response(topic="routing", copilot_config=None, session_meta={}, help_md_dir="/nonexistent")
        assert "not available" in result.lower() or "not found" in result.lower()

    def test_dynamic_tips_with_copilot(self):
        """When copilot config present, tips are generated."""
        from nanobot.agent.loop import _build_help_response
        config = MagicMock()
        config.dream_cron_expr = "0 7 * * *"
        config.copilot_docs_dir = "/nonexistent"

        result = _build_help_response(topic=None, copilot_config=config, session_meta={}, help_md_dir=None)
        # Should include at least the commands even with copilot
        assert "/status" in result

    def test_active_override_shows_warning(self):
        """Active /use override shows in tips."""
        from nanobot.agent.loop import _build_help_response
        config = MagicMock()
        config.copilot_docs_dir = "/nonexistent"

        meta = {"force_provider": "venice", "force_tier": "big"}
        result = _build_help_response(topic=None, copilot_config=config, session_meta=meta, help_md_dir=None)
        assert "auto" in result.lower() or "override" in result.lower() or "venice" in result.lower()
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/ubuntu/executive-copilot/nanobot && python -m pytest tests/test_help_command.py -v`
Expected: FAIL with `ImportError: cannot import name '_build_help_response'`

**Step 3: Commit**

```bash
git add tests/test_help_command.py
git commit -m "test: add failing tests for /help command"
```

---

### Task 3: Implement _build_help_response helper

**Files:**
- Modify: `nanobot/agent/loop.py` (add module-level function, ~50 lines)

**Step 1: Add _build_help_response function after MODEL_ALIASES dict (after line 43)**

```python
def _build_help_response(
    topic: str | None,
    copilot_config: "CopilotConfig | None",
    session_meta: dict,
    help_md_dir: str | None,
) -> str:
    """Build /help response. Static commands + dynamic tips + topic drill-down."""

    COMMANDS = (
        "/new — Start a new conversation\n"
        "/status — System health, costs, routing, memory\n"
        "/tasks — List active tasks with status\n"
        "/task <id> — Detailed task view\n"
        "/cancel <id> — Cancel a running task\n"
        "/onboard — Start the getting-to-know-you interview\n"
        "/profile — Show your current profile\n"
        "/use <provider> [fast|<model>] — Switch LLM provider\n"
        "/use auto — Return to automatic routing\n"
        "/private — Local-only mode\n"
        "/help [topic] — This help (topics: routing, policy, memory, tasks, models, alerts)"
    )

    # --- Topic drill-down ---
    if topic:
        section = _load_help_section(topic, help_md_dir or (copilot_config.copilot_docs_dir if copilot_config else None))
        if section:
            return f"**{topic.title()}**\n\n{section}"
        # Unknown topic — list available
        available = _list_help_topics(help_md_dir or (copilot_config.copilot_docs_dir if copilot_config else None))
        topics_str = ", ".join(available) if available else "routing, policy, memory, tasks, models, alerts"
        return f"Topic '{topic}' not found. Available topics: {topics_str}"

    # --- Summary mode ---
    parts = ["\U0001f408 **nanobot help**\n", "**Commands:**\n" + COMMANDS]

    # Dynamic tips
    tips = _generate_tips(copilot_config, session_meta)
    if tips:
        parts.append("\n**Tips:**\n" + "\n".join(tips))

    parts.append("\nType `/help <topic>` for details. Topics: routing, policy, memory, tasks, models, alerts")
    return "\n".join(parts)


def _load_help_section(topic: str, docs_dir: str | None) -> str | None:
    """Load a ## section from help.md by topic name."""
    if not docs_dir:
        return None
    help_path = Path(docs_dir) / "help.md"
    try:
        content = help_path.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError):
        return None

    # Parse ## sections
    import re
    pattern = rf"^## {re.escape(topic)}\s*\n(.*?)(?=^## |\Z)"
    match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else None


def _list_help_topics(docs_dir: str | None) -> list[str]:
    """List available ## topics from help.md."""
    if not docs_dir:
        return []
    help_path = Path(docs_dir) / "help.md"
    try:
        content = help_path.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError):
        return []
    import re
    return re.findall(r"^## (\w+)", content, re.MULTILINE)


def _generate_tips(copilot_config, session_meta: dict) -> list[str]:
    """Generate dynamic tips based on config and session state."""
    if not copilot_config:
        return []
    tips = []
    if session_meta.get("force_provider"):
        provider = session_meta["force_provider"]
        tips.append(f"  \u26a0\ufe0f Manual routing active ({provider}) — `/use auto` to revert")
    if session_meta.get("private_mode"):
        tips.append("  \U0001f512 Private mode active — all requests stay local")
    if hasattr(copilot_config, "dream_cron_expr"):
        tips.append(f"  \U0001f4a4 Dream cycle: {copilot_config.dream_cron_expr}")
    if hasattr(copilot_config, "heartbeat_interval"):
        hrs = copilot_config.heartbeat_interval / 3600
        tips.append(f"  \U0001f493 Heartbeat: every {hrs:.0f}h")
    return tips[:5]
```

**Step 2: Run tests**

Run: `cd /home/ubuntu/executive-copilot/nanobot && python -m pytest tests/test_help_command.py -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add nanobot/agent/loop.py
git commit -m "feat: add _build_help_response helper for adaptive /help"
```

---

### Task 4: Wire handler into slash command block

**Files:**
- Modify: `nanobot/agent/loop.py:311-313` (replace existing /help handler)

**Step 1: Replace the existing /help block (line 311-313)**

Replace:
```python
        if cmd == "/help":
            return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id,
                                  content="🐈 nanobot commands:\n/new — Start a new conversation\n/status — System status dashboard\n/tasks — List active tasks with status\n/task <id> — Detailed task view with steps\n/cancel <id> — Cancel a running task\n/onboard — Start the getting-to-know-you interview\n/profile — Show your current profile\n/use <provider> [fast|<model>] — Switch LLM provider (e.g. /use venice, /use openrouter fast, /use venice gpt-4o)\n/model — Alias for /use\n/use auto — Return to automatic routing\n/help — Show available commands")
```

With:
```python
        if cmd == "/help" or cmd.startswith("/help "):
            topic = cmd[6:].strip() or None
            docs_dir = self._copilot_config.copilot_docs_dir if self._copilot_config else None
            content = _build_help_response(topic, self._copilot_config, session.metadata, docs_dir)
            return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, content=content)
```

**Step 2: Run full test suite to verify nothing breaks**

Run: `cd /home/ubuntu/executive-copilot/nanobot && python -m pytest tests/ -v --timeout=30 2>&1 | tail -30`
Expected: All tests PASS (including new help tests)

**Step 3: Manual smoke test**

Run: `cd /home/ubuntu/executive-copilot/nanobot && python -c "from nanobot.agent.loop import _build_help_response; print(_build_help_response(None, None, {}, 'data/copilot'))"`
Expected: Shows commands list with routing topic from help.md

Run: `cd /home/ubuntu/executive-copilot/nanobot && python -c "from nanobot.agent.loop import _build_help_response; print(_build_help_response('routing', None, {}, 'data/copilot'))"`
Expected: Shows routing section content

**Step 4: Commit**

```bash
git add nanobot/agent/loop.py
git commit -m "feat: wire adaptive /help into slash command handler"
```

---

### Task 5: Update capabilities.md

**Files:**
- Modify: `data/copilot/capabilities.md`

**Step 1: Update the Commands section**

Add `/help [topic]` to the commands list and note the available topics.

Replace:
```markdown
## Commands
- /status — Health, costs, routing, memory, alerts, session context
```

With:
```markdown
## Commands
- /help [topic] — Adaptive help (topics: routing, policy, memory, tasks, models, alerts)
- /status — Health, costs, routing, memory, alerts, session context
```

**Step 2: Commit**

```bash
git add data/copilot/capabilities.md
git commit -m "docs: add /help to capabilities.md commands list"
```
