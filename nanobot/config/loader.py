"""Configuration loading utilities."""

import json
import os
from pathlib import Path
from typing import Any

from nanobot.config.schema import Config

# Keys that are secrets (nested under their respective sections)
_SECRET_KEYS = {
    "api_key", "apiKey",
    "token", "bot_token", "botToken", "app_token", "appToken",
    "secret", "app_secret", "appSecret", "client_secret", "clientSecret",
    "password", "imap_password", "smtp_password",
    "monitor_chat_id", "monitorChatId",
    "approval_chat_id", "approvalChatId",
    "allow_from", "allowFrom",
}

# Sections with flat secret keys (key is direct child, not nested under a name)
_FLAT_SECRET_SECTIONS = ("copilot",)


def get_config_path() -> Path:
    """Get the default configuration file path."""
    return Path.home() / ".nanobot" / "config.json"


def get_secrets_path() -> Path:
    """Get the secrets file path (API keys, tokens)."""
    return Path.home() / ".nanobot" / "secrets.json"


def get_data_dir() -> Path:
    """Get the nanobot data directory."""
    from nanobot.utils.helpers import get_data_path
    return get_data_path()


def load_config(config_path: Path | None = None) -> Config:
    """Load configuration from config.json + secrets.json (merged)."""
    path = config_path or get_config_path()
    secrets_path = get_secrets_path()

    if path.exists():
        try:
            with open(path) as f:
                data = json.load(f)
            data = _migrate_config(data)

            # Merge secrets on top (API keys override empty config values)
            if secrets_path.exists():
                with open(secrets_path) as f:
                    secrets = json.load(f)
                _deep_merge(data, secrets)
            elif _has_secrets(data):
                # First run: config.json has secrets but no secrets.json yet
                _migrate_secrets(data, path, secrets_path)

            return Config.model_validate(convert_keys(data))
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Warning: Failed to load config from {path}: {e}")
            print("Using default configuration.")

    return Config()


def save_config(config: Config, config_path: Path | None = None) -> None:
    """Save configuration, splitting secrets into a separate file."""
    path = config_path or get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    data = config.model_dump()
    data = convert_to_camel(data)

    # Extract secrets before writing config
    secrets = _extract_secrets(data)

    with open(path, "w") as f:
        json.dump(data, f, indent=2)

    # Write secrets file with restrictive permissions
    if secrets:
        secrets_path = get_secrets_path()
        with open(secrets_path, "w") as f:
            json.dump(secrets, f, indent=2)
        os.chmod(secrets_path, 0o600)


def _deep_merge(base: dict, override: dict) -> None:
    """Recursively merge override into base (mutates base)."""
    for key, val in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(val, dict):
            _deep_merge(base[key], val)
        elif val is not None:  # Override with any non-None value
            base[key] = val


def _has_secrets(data: dict) -> bool:
    """Check if config data contains non-empty secret values."""
    for section in ("providers", "channels", "tools"):
        sub = data.get(section, {})
        if isinstance(sub, dict):
            for val in sub.values():
                if isinstance(val, dict):
                    for k, v in val.items():
                        if k in _SECRET_KEYS and v:
                            return True
    for section in _FLAT_SECRET_SECTIONS:
        sub = data.get(section, {})
        if isinstance(sub, dict):
            for k, v in sub.items():
                if k in _SECRET_KEYS and v:
                    return True
    return False


def _extract_secrets(data: dict) -> dict:
    """Extract secret values from data (mutates data by clearing them). Returns secrets dict."""
    secrets: dict = {}
    for section in ("providers", "channels", "tools"):
        sub = data.get(section, {})
        if not isinstance(sub, dict):
            continue
        for name, val in sub.items():
            if not isinstance(val, dict):
                continue
            for k in list(val.keys()):
                if k in _SECRET_KEYS and val[k]:
                    secrets.setdefault(section, {}).setdefault(name, {})[k] = val[k]
                    val[k] = ""
    # Flat sections — secret keys are direct children
    for section in _FLAT_SECRET_SECTIONS:
        sub = data.get(section, {})
        if not isinstance(sub, dict):
            continue
        for k in list(sub.keys()):
            if k in _SECRET_KEYS and sub[k]:
                secrets.setdefault(section, {})[k] = sub[k]
                sub[k] = ""
    return secrets


def _migrate_secrets(data: dict, config_path: Path, secrets_path: Path) -> None:
    """One-time migration: extract secrets from config.json into secrets.json."""
    secrets = _extract_secrets(data)
    if not secrets:
        return

    # Write secrets file
    with open(secrets_path, "w") as f:
        json.dump(secrets, f, indent=2)
    os.chmod(secrets_path, 0o600)

    # Re-write config without secrets
    with open(config_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Migrated API keys to {secrets_path} (mode 600). Config cleaned.")


def _migrate_config(data: dict) -> dict:
    """Migrate old config formats to current."""
    # Move tools.exec.restrictToWorkspace → tools.restrictToWorkspace
    tools = data.get("tools", {})
    exec_cfg = tools.get("exec", {})
    if "restrictToWorkspace" in exec_cfg and "restrictToWorkspace" not in tools:
        tools["restrictToWorkspace"] = exec_cfg.pop("restrictToWorkspace")
    return data


def convert_keys(data: Any) -> Any:
    """Convert camelCase keys to snake_case for Pydantic."""
    if isinstance(data, dict):
        return {camel_to_snake(k): convert_keys(v) for k, v in data.items()}
    if isinstance(data, list):
        return [convert_keys(item) for item in data]
    return data


def convert_to_camel(data: Any) -> Any:
    """Convert snake_case keys to camelCase."""
    if isinstance(data, dict):
        return {snake_to_camel(k): convert_to_camel(v) for k, v in data.items()}
    if isinstance(data, list):
        return [convert_to_camel(item) for item in data]
    return data


def camel_to_snake(name: str) -> str:
    """Convert camelCase to snake_case."""
    result = []
    for i, char in enumerate(name):
        if char.isupper() and i > 0:
            result.append("_")
        result.append(char.lower())
    return "".join(result)


def snake_to_camel(name: str) -> str:
    """Convert snake_case to camelCase."""
    components = name.split("_")
    return components[0] + "".join(x.title() for x in components[1:])
