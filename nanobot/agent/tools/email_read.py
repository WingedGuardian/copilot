"""IMAP email reading tool."""

import asyncio
import imaplib
import re
from email import policy
from email.parser import BytesParser
from typing import Any

from nanobot.agent.tools.base import Tool


class EmailReadTool(Tool):
    """Tool to read emails via IMAP."""

    def __init__(self, imap_host: str, imap_port: int = 993, username: str = "", password: str = ""):
        self._host = imap_host
        self._port = imap_port
        self._user = username
        self._pass = password

    @property
    def name(self) -> str:
        return "email_read"

    @property
    def description(self) -> str:
        return "Read emails via IMAP. Actions: list_unread, read_email, mark_read, search."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list_unread", "read_email", "mark_read", "search"], "description": "Action to perform"},
                "limit": {"type": "integer", "description": "Max emails to return (for list_unread, default 20)"},
                "email_id": {"type": "string", "description": "Email UID (for read_email, mark_read)"},
                "query": {"type": "string", "description": "Search query (for search). Supports IMAP search syntax."},
                "folder": {"type": "string", "description": "IMAP folder (default: INBOX)"},
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        limit: int = 20,
        email_id: str = "",
        query: str = "",
        folder: str = "INBOX",
        **kwargs: Any,
    ) -> str:
        try:
            if action == "list_unread":
                return await asyncio.to_thread(self._list_unread, folder, limit)
            elif action == "read_email":
                if not email_id:
                    return "Error: email_id is required for read_email"
                return await asyncio.to_thread(self._read_email, folder, email_id)
            elif action == "mark_read":
                if not email_id:
                    return "Error: email_id is required for mark_read"
                return await asyncio.to_thread(self._mark_read, folder, email_id)
            elif action == "search":
                if not query:
                    return "Error: query is required for search"
                return await asyncio.to_thread(self._search, folder, query, limit)
            return f"Unknown action: {action}"
        except Exception as e:
            return f"Email error: {e}"

    def _connect(self) -> imaplib.IMAP4_SSL:
        conn = imaplib.IMAP4_SSL(self._host, self._port)
        conn.login(self._user, self._pass)
        return conn

    def _parse_headers(self, data: bytes) -> dict[str, str]:
        msg = BytesParser(policy=policy.default).parsebytes(data)
        return {
            "subject": str(msg.get("Subject", "(no subject)")),
            "from": str(msg.get("From", "")),
            "date": str(msg.get("Date", "")),
        }

    def _list_unread(self, folder: str, limit: int) -> str:
        conn = self._connect()
        try:
            conn.select(folder, readonly=True)
            _, data = conn.uid("SEARCH", None, "UNSEEN")
            uids = data[0].split() if data[0] else []
            if not uids:
                return "No unread emails."
            uids = uids[-limit:]  # most recent
            lines = []
            for uid in uids:
                _, msg_data = conn.uid("FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])")
                if msg_data and msg_data[0] and isinstance(msg_data[0], tuple):
                    h = self._parse_headers(msg_data[0][1])
                    lines.append(f"- UID {uid.decode()}: {h['subject']} (from: {h['from']}, {h['date']})")
            return f"Unread emails ({len(lines)}):\n" + "\n".join(lines)
        finally:
            conn.logout()

    def _read_email(self, folder: str, uid: str) -> str:
        conn = self._connect()
        try:
            conn.select(folder, readonly=True)
            _, msg_data = conn.uid("FETCH", uid.encode(), "(RFC822)")
            if not msg_data or not msg_data[0] or not isinstance(msg_data[0], tuple):
                return f"Email UID {uid} not found."
            msg = BytesParser(policy=policy.default).parsebytes(msg_data[0][1])
            subject = str(msg.get("Subject", "(no subject)"))
            sender = str(msg.get("From", ""))
            date = str(msg.get("Date", ""))
            # Extract body
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    ct = part.get_content_type()
                    if ct == "text/plain":
                        body = part.get_content()
                        break
                    elif ct == "text/html" and not body:
                        body = re.sub(r"<[^>]+>", "", part.get_content())
            else:
                ct = msg.get_content_type()
                content = msg.get_content()
                body = content if ct == "text/plain" else re.sub(r"<[^>]+>", "", content)
            # Truncate very long bodies
            if len(body) > 4000:
                body = body[:4000] + "\n... [truncated]"
            return f"Subject: {subject}\nFrom: {sender}\nDate: {date}\n\n{body}"
        finally:
            conn.logout()

    def _mark_read(self, folder: str, uid: str) -> str:
        conn = self._connect()
        try:
            conn.select(folder)
            conn.uid("STORE", uid.encode(), "+FLAGS", "\\Seen")
            return f"Marked UID {uid} as read."
        finally:
            conn.logout()

    def _search(self, folder: str, query: str, limit: int) -> str:
        conn = self._connect()
        try:
            conn.select(folder, readonly=True)
            _, data = conn.uid("SEARCH", None, query)
            uids = data[0].split() if data[0] else []
            if not uids:
                return "No matching emails."
            uids = uids[-limit:]
            lines = []
            for uid in uids:
                _, msg_data = conn.uid("FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])")
                if msg_data and msg_data[0] and isinstance(msg_data[0], tuple):
                    h = self._parse_headers(msg_data[0][1])
                    lines.append(f"- UID {uid.decode()}: {h['subject']} (from: {h['from']}, {h['date']})")
            return f"Search results ({len(lines)}):\n" + "\n".join(lines)
        finally:
            conn.logout()
