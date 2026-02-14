"""Session management for conversation history."""

import json
import os
import re
import tempfile
import time
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from loguru import logger

from nanobot.utils.helpers import ensure_dir, safe_filename

# Phrases that activate private mode
_PRIVATE_ON_PATTERNS = [
    re.compile(r"\b(?:private\s+mode|keep\s+(?:this|it)\s+local|local\s+only|go\s+private)\b", re.I),
]

# Phrases that deactivate private mode
_PRIVATE_OFF_PATTERNS = [
    re.compile(r"\b(?:end\s+private\s+mode|exit\s+private|back\s+to\s+normal|normal\s+mode|stop\s+private)\b", re.I),
]

# Phrase to extend private mode during timeout warning
_PRIVATE_EXTEND_PATTERNS = [
    re.compile(r"\b(?:stay\s+private|keep\s+private|extend\s+private)\b", re.I),
]


@dataclass
class Session:
    """
    A conversation session.
    
    Stores messages in JSONL format for easy reading and persistence.
    """
    
    key: str  # channel:chat_id
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def add_message(self, role: str, content: str, **kwargs: Any) -> None:
        """Add a message to the session."""
        msg = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            **kwargs
        }
        self.messages.append(msg)
        self.updated_at = datetime.now()
    
    def get_history(self, max_messages: int = 50) -> list[dict[str, Any]]:
        """
        Get message history for LLM context.
        
        Args:
            max_messages: Maximum messages to return.
        
        Returns:
            List of messages in LLM format.
        """
        # Get recent messages
        recent = self.messages[-max_messages:] if len(self.messages) > max_messages else self.messages
        
        # Convert to LLM format (just role and content)
        return [{"role": m["role"], "content": m["content"]} for m in recent]
    
    @property
    def private_mode(self) -> bool:
        """Whether private mode is active for this session."""
        return self.metadata.get("private_mode", False)

    @property
    def private_mode_since(self) -> float:
        """Timestamp when private mode was activated (0 if not active)."""
        return self.metadata.get("private_mode_since", 0.0)

    @property
    def last_user_message_at(self) -> float:
        """Timestamp of the last user message activity."""
        return self.metadata.get("last_user_message_at", 0.0)

    def activate_private_mode(self) -> None:
        """Enable private mode for this session."""
        self.metadata["private_mode"] = True
        self.metadata["private_mode_since"] = time.time()
        self.metadata["last_user_message_at"] = time.time()

    def deactivate_private_mode(self) -> None:
        """Disable private mode for this session."""
        self.metadata.pop("private_mode", None)
        self.metadata.pop("private_mode_since", None)

    def touch_activity(self) -> None:
        """Update last user message timestamp (for private mode timeout)."""
        self.metadata["last_user_message_at"] = time.time()

    def clear(self) -> None:
        """Clear all messages in the session."""
        self.messages = []
        self.updated_at = datetime.now()


class SessionManager:
    """
    Manages conversation sessions.
    
    Sessions are stored as JSONL files in the sessions directory.
    """
    
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.sessions_dir = ensure_dir(Path.home() / ".nanobot" / "sessions")
        self._cache: dict[str, Session] = {}
    
    def _get_session_path(self, key: str) -> Path:
        """Get the file path for a session."""
        safe_key = safe_filename(key.replace(":", "_"))
        return self.sessions_dir / f"{safe_key}.jsonl"
    
    def get_or_create(self, key: str) -> Session:
        """
        Get an existing session or create a new one.
        
        Args:
            key: Session key (usually channel:chat_id).
        
        Returns:
            The session.
        """
        # Check cache
        if key in self._cache:
            return self._cache[key]
        
        # Try to load from disk
        session = self._load(key)
        if session is None:
            session = Session(key=key)
        
        self._cache[key] = session
        return session
    
    def _load(self, key: str) -> Session | None:
        """Load a session from disk."""
        path = self._get_session_path(key)
        
        if not path.exists():
            return None
        
        try:
            messages = []
            metadata = {}
            created_at = None
            
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    data = json.loads(line)
                    
                    if data.get("_type") == "metadata":
                        metadata = data.get("metadata", {})
                        created_at = datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None
                    else:
                        messages.append(data)
            
            return Session(
                key=key,
                messages=messages,
                created_at=created_at or datetime.now(),
                metadata=metadata
            )
        except Exception as e:
            logger.warning(f"Failed to load session {key}: {e}")
            # Try backup file
            bak_path = path.with_suffix(".jsonl.bak")
            if bak_path.exists():
                logger.info(f"Trying backup for session {key}")
                try:
                    return self._load_from_path(key, bak_path)
                except Exception as e2:
                    logger.warning(f"Backup also failed for {key}: {e2}")
            return None
    
    def _load_from_path(self, key: str, path: Path) -> Session | None:
        """Load a session from a specific file path."""
        messages = []
        metadata = {}
        created_at = None

        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                if data.get("_type") == "metadata":
                    metadata = data.get("metadata", {})
                    created_at = datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None
                else:
                    messages.append(data)

        return Session(
            key=key,
            messages=messages,
            created_at=created_at or datetime.now(),
            metadata=metadata
        )

    def save(self, session: Session) -> None:
        """Save a session to disk atomically (write-to-temp + os.replace)."""
        path = self._get_session_path(session.key)

        # Write to temp file in same directory, then atomic rename
        fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                # Write metadata first
                metadata_line = {
                    "_type": "metadata",
                    "created_at": session.created_at.isoformat(),
                    "updated_at": session.updated_at.isoformat(),
                    "metadata": session.metadata
                }
                f.write(json.dumps(metadata_line) + "\n")

                # Write messages
                for msg in session.messages:
                    f.write(json.dumps(msg) + "\n")

            # Keep backup of previous version
            if path.exists():
                bak_path = path.with_suffix(".jsonl.bak")
                try:
                    os.replace(str(path), str(bak_path))
                except OSError:
                    pass

            os.replace(tmp_path, str(path))
        except BaseException:
            # Clean up temp file on any error
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        self._cache[session.key] = session
    
    def delete(self, key: str) -> bool:
        """
        Delete a session.
        
        Args:
            key: Session key.
        
        Returns:
            True if deleted, False if not found.
        """
        # Remove from cache
        self._cache.pop(key, None)
        
        # Remove file
        path = self._get_session_path(key)
        if path.exists():
            path.unlink()
            return True
        return False
    
    def list_sessions(self) -> list[dict[str, Any]]:
        """
        List all sessions.
        
        Returns:
            List of session info dicts.
        """
        sessions = []
        
        for path in self.sessions_dir.glob("*.jsonl"):
            try:
                # Read just the metadata line
                with open(path) as f:
                    first_line = f.readline().strip()
                    if first_line:
                        data = json.loads(first_line)
                        if data.get("_type") == "metadata":
                            sessions.append({
                                "key": path.stem.replace("_", ":"),
                                "created_at": data.get("created_at"),
                                "updated_at": data.get("updated_at"),
                                "path": str(path)
                            })
            except Exception:
                continue
        
        return sorted(sessions, key=lambda x: x.get("updated_at", ""), reverse=True)

    @staticmethod
    def detect_private_mode_command(message: str) -> str | None:
        """Detect private mode commands in user message.

        Returns:
            "on" if activating, "off" if deactivating, "extend" if extending, None otherwise.
        """
        for p in _PRIVATE_OFF_PATTERNS:
            if p.search(message):
                return "off"
        for p in _PRIVATE_ON_PATTERNS:
            if p.search(message):
                return "on"
        for p in _PRIVATE_EXTEND_PATTERNS:
            if p.search(message):
                return "extend"
        return None
