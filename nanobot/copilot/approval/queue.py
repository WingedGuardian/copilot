"""Approval queue: pending approvals with asyncio.Event for blocking."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiosqlite
from loguru import logger

from nanobot.copilot.approval.parser import ApprovalResponse


@dataclass
class PendingApproval:
    """A pending approval request waiting for user response."""

    id: str
    session_key: str
    tool_name: str
    tool_args: dict[str, Any]
    summary: str
    event: asyncio.Event = field(default_factory=asyncio.Event)
    response: ApprovalResponse | None = None
    created_at: float = field(default_factory=time.time)
    timeout: float = 300.0


class ApprovalQueue:
    """Manages pending approval requests with asyncio blocking and crash recovery."""

    def __init__(self, db_path: str | Path):
        self._db_path = str(db_path)
        self._pending: dict[str, PendingApproval] = {}

    def create_request(
        self,
        session_key: str,
        tool_name: str,
        tool_args: dict[str, Any],
        summary: str,
        timeout: float = 300.0,
    ) -> PendingApproval:
        """Create a new pending approval request."""
        request_id = str(uuid.uuid4())[:8]
        pending = PendingApproval(
            id=request_id,
            session_key=session_key,
            tool_name=tool_name,
            tool_args=tool_args,
            summary=summary,
            timeout=timeout,
        )
        self._pending[session_key] = pending

        # Persist for crash recovery (fire-and-forget)
        asyncio.ensure_future(self._persist(pending))

        logger.info(f"Approval request {request_id} for {tool_name} in {session_key}")
        return pending

    def has_pending(self, session_key: str) -> bool:
        """Check if there's a pending approval for this session."""
        pending = self._pending.get(session_key)
        if pending is None:
            return False
        # Check if expired
        if time.time() - pending.created_at > pending.timeout:
            del self._pending[session_key]
            return False
        return True

    def get_pending(self, session_key: str) -> PendingApproval | None:
        """Get the pending approval for a session."""
        return self._pending.get(session_key)

    def resolve(self, session_key: str, response: ApprovalResponse) -> None:
        """Resolve a pending approval with a user response."""
        pending = self._pending.get(session_key)
        if pending is None:
            logger.warning(f"No pending approval for {session_key}")
            return

        pending.response = response
        pending.event.set()

        # Cleanup
        del self._pending[session_key]
        asyncio.ensure_future(self._cleanup_persisted(pending.id))

        logger.info(f"Approval {pending.id} resolved: {response.intent}")

    def cleanup_expired(self) -> int:
        """Remove timed-out entries. Returns count of removed entries."""
        now = time.time()
        expired = [
            key for key, p in self._pending.items()
            if now - p.created_at > p.timeout
        ]
        for key in expired:
            pending = self._pending.pop(key)
            pending.response = ApprovalResponse(
                intent="deny", confidence=1.0, reason="Approval timed out"
            )
            pending.event.set()
        return len(expired)

    async def _persist(self, pending: PendingApproval) -> None:
        """Persist pending approval to SQLite for crash recovery."""
        try:
            import json
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    """INSERT OR REPLACE INTO pending_approvals
                       (id, session_key, tool_name, tool_args_json, summary,
                        created_at, timeout_seconds, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')""",
                    (
                        pending.id,
                        pending.session_key,
                        pending.tool_name,
                        json.dumps(pending.tool_args),
                        pending.summary,
                        pending.created_at,
                        pending.timeout,
                    ),
                )
                await db.commit()
        except Exception as e:
            logger.warning(f"Failed to persist approval: {e}")
            from nanobot.copilot.alerting.bus import get_alert_bus
            await get_alert_bus().alert("approval", "medium", f"Approval persistence failed: {e}", "persist_failed")

    async def _cleanup_persisted(self, approval_id: str) -> None:
        """Remove resolved approval from SQLite."""
        try:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    "DELETE FROM pending_approvals WHERE id = ?",
                    (approval_id,),
                )
                await db.commit()
        except Exception as e:
            logger.warning(f"Failed to cleanup approval: {e}")

    async def recover_from_crash(self) -> int:
        """Load pending approvals from SQLite on startup, auto-deny stale ones (>1hr old).

        Returns number of recovered/denied approvals.
        """
        import json
        count = 0
        try:
            async with aiosqlite.connect(self._db_path) as db:
                cur = await db.execute(
                    "SELECT id, session_key, tool_name, tool_args_json, summary, created_at, timeout_seconds "
                    "FROM pending_approvals WHERE status = 'pending'"
                )
                rows = await cur.fetchall()

                now = time.time()
                for row in rows:
                    approval_id, session_key, tool_name, args_json, summary, created_at, timeout_s = row
                    age = now - created_at

                    if age > 3600:  # >1 hour old: auto-deny
                        await db.execute(
                            "UPDATE pending_approvals SET status = 'denied_stale' WHERE id = ?",
                            (approval_id,),
                        )
                        logger.info(f"Auto-denied stale approval {approval_id} (age: {age:.0f}s)")
                    else:
                        # Still valid — log but don't restore to in-memory queue
                        # (the original asyncio.Event is lost on crash)
                        await db.execute(
                            "UPDATE pending_approvals SET status = 'denied_crash' WHERE id = ?",
                            (approval_id,),
                        )
                        logger.info(f"Denied orphaned approval {approval_id} from crash recovery")
                    count += 1

                await db.commit()
        except Exception as e:
            logger.warning(f"Approval crash recovery failed: {e}")

        if count:
            logger.info(f"Approval crash recovery: processed {count} orphaned approvals")
        return count
