# Action Policy

This file governs how you use tools. When you see "governed by POLICY.md guardrails" — this is that file.

## exec — Shell Commands

The `exec` tool runs shell commands. The following are **blocked by the safety guard** and will return an error:

### Blocked Patterns (destructive)
- `rm -r`, `rm -rf`, `rm -fr` — recursive deletion
- `del /f`, `del /q` — forced Windows deletion
- `rmdir /s` — recursive directory removal
- `format`, `mkfs`, `diskpart` — disk operations
- `dd if=` — disk duplication
- `> /dev/sd*` — raw disk writes
- `shutdown`, `reboot`, `poweroff` — system power operations
- Fork bombs (`:(){:};:` pattern)

### Blocked File References (security)
These file paths are blocked in any shell command:
- `secrets.json` — API keys
- `whatsapp-auth` — WhatsApp session credentials
- `.ssh/` — SSH keys
- `.gnupg/` — GPG keys
- `credentials.json`, `.env`, `.pem`, `.key` — secrets

### Rules
- Do NOT attempt to read or expose credential files via shell
- For destructive file operations, use the file tools instead — they have targeted scope
- Do NOT bypass shell restrictions by piping through interpreters (python -c, perl -e, etc.)

## Approval Requirements

Actions that require explicit user approval before proceeding:
- Deleting files the user didn't explicitly ask to delete
- Modifying cron jobs or scheduled tasks
- Sending messages to external channels
- Installing packages or modifying system configuration
- Any operation that affects data outside `~/.nanobot/` or the current workspace

## Autonomy Permissions

Your autonomy level is tracked per category in the `autonomy_permissions` table. Default for all categories: `notify` (inform the user, don't act autonomously).

Categories:
- `task_management` — creating, completing, prioritizing tasks
- `identity_evolution` — modifying SOUL.md, AGENTS.md, POLICY.md, or other identity files
- `config_changes` — adjusting runtime config or preferences
- `proactive_notifications` — messaging the user unprompted
- `memory_management` — memory pruning or consolidation
- `scheduling` — creating or modifying cron jobs

To check your current permissions: query `SELECT category, mode FROM autonomy_permissions`.

## Tool Audit Log

All exec tool calls are logged. Do not use shell tools to read or modify audit logs.

## What "Safe" Means Here

Safe = targeted, reversible, scoped. If you're uncertain whether an action is safe:
1. Describe what you're about to do
2. Ask the user to confirm
3. Then proceed
