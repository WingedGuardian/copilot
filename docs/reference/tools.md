# Available Tools

This document describes the tools available to nanobot.

## File Operations

### read_file
Read the contents of a file.
```
read_file(path: str) -> str
```

### write_file
Write content to a file (creates parent directories if needed).
```
write_file(path: str, content: str) -> str
```

### edit_file
Edit a file by replacing specific text.
```
edit_file(path: str, old_text: str, new_text: str) -> str
```

### list_dir
List contents of a directory.
```
list_dir(path: str) -> str
```

## Shell Execution

### exec
Execute a shell command and return output.
```
exec(command: str, working_dir: str = None) -> str
```

**Safety Notes:**
- Commands have a configurable timeout (default 60s)
- Dangerous commands are blocked (rm -rf, format, dd, shutdown, etc.)
- Output is truncated at 10,000 characters
- Optional `restrictToWorkspace` config to limit paths

## Web Access

### web_search
Search the web using Brave Search API.
```
web_search(query: str, count: int = 5) -> str
```

Returns search results with titles, URLs, and snippets. Requires `tools.web.search.apiKey` in config.

### web_fetch
Fetch and extract main content from a URL.
```
web_fetch(url: str, extractMode: str = "markdown", maxChars: int = 50000) -> str
```

**Notes:**
- Content is extracted using readability
- Supports markdown or plain text extraction
- Output is truncated at 50,000 characters by default

## Communication

### message
Send a message to the user (used internally).
```
message(content: str, channel: str = None, chat_id: str = None) -> str
```

## Background Tasks

### spawn
Spawn a subagent to handle a task in the background.
```
spawn(task: str, label: str = None) -> str
```

Use for complex or time-consuming tasks that can run independently. The subagent will complete the task and report back when done.

## Task Management

### task
Create and manage persistent tasks with background execution.

```
task(action="create", title="Research VPS providers", description="Find top 3 under $20/month")
task(action="list")
task(action="get", task_id="abc123")
task(action="complete", task_id="abc123")
task(action="fail", task_id="abc123")
task(action="add_steps", task_id="abc123", steps=["Step 1", "Step 2"])
task(action="resume", task_id="abc123")
task(action="status_summary")
```

**When to use:**
- Multi-step requests (research, building, comparisons)
- Work the user wants done in the background
- Anything that would take >30 seconds of execution

The background TaskWorker picks up pending tasks, decomposes them into steps via a frontier model, executes each step, and sends progress updates to WhatsApp.

## Email (IMAP)

### email_read
Read emails via IMAP. General-purpose tool available when email is configured.

```python
email_read(action="list_unread", limit=20, folder="INBOX")
email_read(action="read_email", email_id="123")
email_read(action="mark_read", email_id="123")
email_read(action="search", query="FROM newsletter@example.com", limit=10)
```

**Actions:**
- `list_unread` — List unread emails with subject, sender, date (most recent first)
- `read_email` — Read full email body by UID (prefers text/plain, falls back to stripped HTML)
- `mark_read` — Mark an email as read by UID
- `search` — Search using IMAP search syntax (e.g., `FROM sender`, `SUBJECT keyword`, `SINCE 01-Feb-2026`)

**Configuration:** Requires `email_imap_host` in copilot config and credentials in `secrets.json` under `tools.email`.

---

## Scheduled Reminders (Cron)

Use the `exec` tool to create scheduled reminders with `nanobot cron add`:

### Set a recurring reminder
```bash
# Every day at 9am
nanobot cron add --name "morning" --message "Good morning! ☀️" --cron "0 9 * * *"

# Every 2 hours
nanobot cron add --name "water" --message "Drink water! 💧" --every 7200
```

### Set a one-time reminder
```bash
# At a specific time (ISO format)
nanobot cron add --name "meeting" --message "Meeting starts now!" --at "2025-01-31T15:00:00"
```

### Manage reminders
```bash
nanobot cron list              # List all jobs
nanobot cron remove <job_id>   # Remove a job
```

## Heartbeat Task Management

The `HEARTBEAT.md` file in the workspace is checked every 30 minutes.
Use file operations to manage periodic tasks:

### Add a heartbeat task
```python
# Append a new task
edit_file(
    path="HEARTBEAT.md",
    old_text="## Example Tasks",
    new_text="- [ ] New periodic task here\n\n## Example Tasks"
)
```

### Remove a heartbeat task
```python
# Remove a specific task
edit_file(
    path="HEARTBEAT.md",
    old_text="- [ ] Task to remove\n",
    new_text=""
)
```

### Rewrite all tasks
```python
# Replace the entire file
write_file(
    path="HEARTBEAT.md",
    content="# Heartbeat Tasks\n\n- [ ] Task 1\n- [ ] Task 2\n"
)
```

---

## Operational History

### ops_log
Query your own operational history: dream cycles, heartbeat events, alerts, and cost logs.

```python
ops_log(category="dream", hours=24)     # Last 24h of dream cycle runs
ops_log(category="heartbeat", hours=24) # Recent heartbeat runs + events
ops_log(category="alerts", hours=48)    # Alerts deduplicated by error_key
ops_log(category="cost", hours=168)     # Cost breakdown by model and day
```

**Categories:**
- `dream` — Dream cycle runs with timestamps, consolidation counts, errors
- `heartbeat` — Heartbeat runs + events (regardless of acknowledgment status)
- `alerts` — Recent alerts grouped by error_key with occurrence counts
- `cost` — Total spend, per-model breakdown, per-day breakdown

**When to use:**
- User asks "when did your dream cycle last run?"
- User asks about recent alerts or system health history
- User asks about spending or cost trends
- Self-check: verifying your own background processes are working

---

## Memory & Context

### recall_messages
Scroll up in conversation history. Retrieves recent messages that may not be in your current context window. Use when you sense the user is continuing a prior discussion.

```python
recall_messages(count: int = 20)  # max 50
```

**When to use:**
- User references something from earlier in the conversation
- Context feels thin or incomplete
- After a model switch or session restart

**Returns:** Timestamped message list with role labels. Error messages are filtered out.

**Note:** `/status` now includes SLM Queue stats (pending items, processed count, last drain time). Use this to monitor extraction backlog when LM Studio is offline.

### memory
Search, store, or query the episodic memory system. Cross-session semantic search across all stored exchanges and facts.

```python
# Search across all sessions
memory(action="search", query="authentication setup")

# Store a fact or preference
memory(action="store", content="User prefers TypeScript", category="preference")

# Check memory health
memory(action="stats")
```

**Actions:**
- `search` — Semantic search across memories (limit 5 results, scored by relevance)
- `store` — Save facts, preferences, or entities for long-term recall
- `stats` — Check Qdrant connection status and episode/item counts

---

## Adding Custom Tools

To add custom tools:
1. Create a class that extends `Tool` in `nanobot/agent/tools/`
2. Implement `name`, `description`, `parameters`, and `execute`
3. Register it in `AgentLoop._register_default_tools()`
