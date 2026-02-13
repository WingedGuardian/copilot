"""Credential isolation via SecretsProvider.

Tools call secrets.get(key) instead of os.environ[key]. Only pre-registered
keys are accessible. Leak detection logs warnings when credential values
appear in tool output.
"""

from __future__ import annotations

import os
import re
from typing import Any

from loguru import logger


class SecretsProvider:
    """Centralized credential store with access control and leak detection.

    Loads allowed keys once at startup from os.environ. Tools request
    credentials via get(key) — unauthorized keys raise PermissionError.
    check_for_leaks() scans text for accidental credential exposure.
    """

    def __init__(self, allowed_keys: list[str] | None = None):
        """Initialize with explicit allowlist of environment variable names.

        Args:
            allowed_keys: Keys to load from os.environ.  If None, uses a
                built-in default list covering known tool credentials.
        """
        if allowed_keys is None:
            allowed_keys = self._default_keys()

        self._allowed: set[str] = set(allowed_keys)
        self._store: dict[str, str] = {}

        for key in allowed_keys:
            val = os.environ.get(key, "")
            if val:
                self._store[key] = val

        loaded = list(self._store.keys())
        logger.debug(f"SecretsProvider loaded {len(loaded)} keys: {loaded}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key: str) -> str:
        """Retrieve a credential by key name.

        Raises:
            PermissionError: If key is not in the allowed set.
        """
        if key not in self._allowed:
            raise PermissionError(
                f"Access denied: '{key}' is not in the allowed secrets list"
            )
        return self._store.get(key, "")

    def has(self, key: str) -> bool:
        """Check if a key is loaded (non-empty)."""
        return key in self._store and bool(self._store[key])

    def check_for_leaks(self, text: str) -> list[str]:
        """Scan text for any loaded secret values.

        Returns list of leaked key names (empty if clean).  Only checks
        secrets that are at least 8 characters long to avoid false positives
        on short values like 'true' or '1234'.
        """
        leaked: list[str] = []
        for key, val in self._store.items():
            if len(val) >= 8 and val in text:
                leaked.append(key)
        if leaked:
            logger.warning(f"Credential leak detected in output: {leaked}")
        return leaked

    @property
    def loaded_keys(self) -> list[str]:
        """List of keys that were successfully loaded."""
        return list(self._store.keys())

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _default_keys() -> list[str]:
        """Built-in list of known credential env var names."""
        return [
            "BRAVE_API_KEY",
            "N8N_API_KEY",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN",
            "OPENROUTER_API_KEY",
            "DEEPSEEK_API_KEY",
            "GROQ_API_KEY",
            "GEMINI_API_KEY",
        ]
