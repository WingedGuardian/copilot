"""Tests for SecretsProvider credential isolation."""

import pytest

from nanobot.agent.tools.secrets import SecretsProvider


@pytest.fixture
def secrets(monkeypatch):
    """SecretsProvider with controlled env vars."""
    monkeypatch.setenv("TEST_KEY_1", "secret-value-12345678")
    monkeypatch.setenv("TEST_KEY_2", "another-secret-abcdef99")
    return SecretsProvider(allowed_keys=["TEST_KEY_1", "TEST_KEY_2", "MISSING_KEY"])


def test_get_allowed_key(secrets):
    """Allowed key returns env var value."""
    assert secrets.get("TEST_KEY_1") == "secret-value-12345678"


def test_get_missing_key_returns_empty(secrets):
    """Allowed but unset key returns empty string."""
    assert secrets.get("MISSING_KEY") == ""


def test_get_unauthorized_key_raises(secrets):
    """Key not in allowlist raises PermissionError."""
    with pytest.raises(PermissionError, match="not in the allowed"):
        secrets.get("UNAUTHORIZED_KEY")


def test_has_loaded_key(secrets):
    """has() returns True for loaded, non-empty keys."""
    assert secrets.has("TEST_KEY_1") is True
    assert secrets.has("MISSING_KEY") is False


def test_loaded_keys(secrets):
    """loaded_keys lists only keys with values."""
    assert "TEST_KEY_1" in secrets.loaded_keys
    assert "TEST_KEY_2" in secrets.loaded_keys
    assert "MISSING_KEY" not in secrets.loaded_keys


def test_leak_detection_finds_credential(secrets):
    """check_for_leaks detects secret values in text."""
    text = "The output was: secret-value-12345678 and more data"
    leaked = secrets.check_for_leaks(text)
    assert "TEST_KEY_1" in leaked


def test_leak_detection_clean_output(secrets):
    """check_for_leaks returns empty for clean text."""
    text = "This output contains no secrets at all."
    leaked = secrets.check_for_leaks(text)
    assert leaked == []


def test_leak_detection_ignores_short_values(monkeypatch):
    """Short secret values (< 8 chars) are ignored to avoid false positives."""
    monkeypatch.setenv("SHORT_KEY", "abc")
    s = SecretsProvider(allowed_keys=["SHORT_KEY"])
    leaked = s.check_for_leaks("contains abc in output")
    assert leaked == []


def test_default_keys():
    """Default key list includes known credential env vars."""
    keys = SecretsProvider._default_keys()
    assert "BRAVE_API_KEY" in keys
    assert "OPENAI_API_KEY" in keys
    assert "AWS_SECRET_ACCESS_KEY" in keys
