"""Rules engine: default patterns + dynamic SQLite rules for approval gating."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiosqlite
from loguru import logger

# Read-only, local-only operations that never require approval
AUTO_APPROVE = {
    "web_search", "web_fetch", "read_file", "list_files",
    "memory_search", "status", "list_dir",
}

# Shell commands that are safe to auto-approve (read-only)
_READ_ONLY_CMD_RE = re.compile(
    r"^(ls|cat|head|tail|git\s+(status|log|diff|branch|show)|pwd|whoami|df|free|uptime|ps|wc|file|which|env|echo)\b"
)

# Default patterns for tools that require approval
DEFAULT_APPROVAL_PATTERNS: dict[str, dict[str, Any]] = {
    "exec": {
        "description": "Shell command execution",
        "severity": "standard",
        "auto_approve_if": "read_only_command",
    },
    "message": {
        "description": "Send message to external channel",
        "severity": "high",
    },
    "send_email": {
        "description": "Send email externally",
        "severity": "high",
    },
    "write_file": {
        "description": "Write file to disk",
        "severity": "standard",
    },
    "edit_file": {
        "description": "Edit file on disk",
        "severity": "standard",
    },
    "git_push": {
        "description": "Push code to remote",
        "severity": "standard",
    },
    "n8n_trigger": {
        "description": "Trigger external workflow",
        "severity": "standard",
    },
    "aws_mutate": {
        "description": "AWS write operation",
        "severity": "high",
    },
    "tool_builder": {
        "description": "Create a new executable tool at runtime",
        "severity": "high",
    },
}


@dataclass
class ApprovalRequired:
    """Returned when a tool call requires user approval."""

    reason: str
    severity: str  # "standard" or "high"
    reroute_on_deny: str = ""  # Model tier to re-route to if denied (e.g. "fast")


class RulesEngine:
    """Checks tool calls against default patterns and dynamic SQLite rules."""

    def __init__(self, db_path: str | Path):
        self._db_path = str(db_path)
        self._route_context: dict[str, str] = {}

    def set_route_context(self, target: str = "", reason: str = "") -> None:
        """Set routing context for conditional approval rules (per-turn)."""
        self._route_context = {"target": target, "reason": reason}

    def clear_route_context(self) -> None:
        """Clear routing context."""
        self._route_context = {}

    async def check(
        self, tool_name: str, tool_args: dict[str, Any]
    ) -> ApprovalRequired | None:
        """Check if a tool call requires approval.

        Returns None if no approval needed, or ApprovalRequired with reason.
        """
        # 1. Auto-approve known read-only tools
        if tool_name in AUTO_APPROVE:
            # Conditional: web_search on auto-local requires consent
            if tool_name == "web_search" and self._requires_web_search_consent():
                query = tool_args.get("query", "")
                return ApprovalRequired(
                    reason=(
                        f"Local model wants to search: '{query[:100]}'. "
                        "Allow? (yes = keep local, no = use cloud)"
                    ),
                    severity="standard",
                    reroute_on_deny="fast",
                )
            return None

        # 2. Check dynamic rules from DB
        dynamic = await self._check_dynamic_rules(tool_name, tool_args)
        if dynamic is not None:
            return dynamic  # None = auto-approved by rule, ApprovalRequired = needs approval

        # 3. Check default patterns
        pattern = DEFAULT_APPROVAL_PATTERNS.get(tool_name)
        if pattern is None:
            return None  # Unknown tool, no approval needed

        # Special case: exec with read-only commands
        if pattern.get("auto_approve_if") == "read_only_command":
            command = tool_args.get("command", "")
            if _READ_ONLY_CMD_RE.match(command.strip()):
                return None

        return ApprovalRequired(
            reason=pattern["description"],
            severity=pattern["severity"],
        )

    async def add_rule(
        self,
        pattern: str,
        condition: str = "",
        action: str = "auto_approve",
        expires_at: float | None = None,
    ) -> int:
        """Insert a dynamic approval rule. Returns rule ID."""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """INSERT INTO approval_rules (pattern, condition, action, expires_at)
                   VALUES (?, ?, ?, ?)""",
                (pattern, condition, action, expires_at),
            )
            await db.commit()
            rule_id = cursor.lastrowid
            logger.info(f"Added approval rule {rule_id}: {action} for {pattern}")
            return rule_id

    async def revoke_rule(self, rule_id: int) -> None:
        """Delete a dynamic rule."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("DELETE FROM approval_rules WHERE id = ?", (rule_id,))
            await db.commit()

    async def get_active_rules(self) -> list[dict[str, Any]]:
        """Fetch all non-expired dynamic rules."""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """SELECT * FROM approval_rules
                   WHERE expires_at IS NULL OR expires_at > strftime('%s', 'now')"""
            )
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            return [dict(zip(cols, row)) for row in rows]

    async def _check_dynamic_rules(
        self, tool_name: str, tool_args: dict[str, Any]
    ) -> ApprovalRequired | None:
        """Check dynamic rules. Returns None if auto-approved by rule."""
        try:
            async with aiosqlite.connect(self._db_path) as db:
                cursor = await db.execute(
                    """SELECT id, pattern, condition, action FROM approval_rules
                       WHERE (expires_at IS NULL OR expires_at > strftime('%s', 'now'))"""
                )
                rules = await cursor.fetchall()
        except Exception:
            return None  # DB error — fall through to defaults

        for rule_id, pattern, condition, action in rules:
            if not re.search(pattern, tool_name, re.IGNORECASE):
                continue

            # Check condition against tool args (simple key=value matching)
            if condition:
                try:
                    if not self._eval_condition(condition, tool_args):
                        continue
                except Exception:
                    continue

            if action == "auto_approve":
                logger.debug(f"Auto-approved by rule {rule_id}: {pattern}")
                return None  # Explicitly auto-approved
            elif action == "deny":
                return ApprovalRequired(
                    reason=f"Denied by rule {rule_id}: {pattern}",
                    severity="high",
                )

        return None  # No matching dynamic rule — fall through

    def _requires_web_search_consent(self) -> bool:
        """Web search requires consent when auto-routed to local (not private mode).

        Returns False (no consent) when:
        - No route context is set (non-copilot / standalone mode)
        - Route target is not local (cloud handles it fine)
        - User explicitly chose local (private_mode or user_downgrade)
        """
        target = self._route_context.get("target", "")
        reason = self._route_context.get("reason", "")
        if target != "local":
            return False
        # Explicit user choices — no consent needed
        if reason in ("private_mode", "user_downgrade"):
            return False
        return True

    @staticmethod
    def _eval_condition(condition: str, args: dict[str, Any]) -> bool:
        """Simple condition evaluator for dynamic rules.

        Supports: ``key=value``, ``key~=regex``, ``key!=value``
        """
        for part in condition.split(";"):
            part = part.strip()
            if not part:
                continue
            if "~=" in part:
                key, regex = part.split("~=", 1)
                val = str(args.get(key.strip(), ""))
                if not re.search(regex.strip(), val):
                    return False
            elif "!=" in part:
                key, expected = part.split("!=", 1)
                if str(args.get(key.strip(), "")) == expected.strip():
                    return False
            elif "=" in part:
                key, expected = part.split("=", 1)
                if str(args.get(key.strip(), "")) != expected.strip():
                    return False
        return True
