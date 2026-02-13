"""Tests for HTTP endpoint protection (SSRF defense)."""

import pytest

from nanobot.agent.tools.web import _validate_url, DEFAULT_HTTP_DENY


def test_normal_url_allowed():
    """Standard URLs pass validation."""
    ok, _ = _validate_url("https://example.com/page")
    assert ok is True


def test_localhost_allowed():
    """localhost is intentionally allowed (LM Studio, Qdrant, etc.)."""
    ok, _ = _validate_url("http://localhost:6333")
    assert ok is True


def test_private_network_allowed():
    """192.168.x.x is allowed (user's LAN)."""
    ok, _ = _validate_url("http://192.168.50.100:1234/v1")
    assert ok is True


def test_ten_network_allowed():
    """10.x.x.x is allowed (user's LAN)."""
    ok, _ = _validate_url("http://10.0.0.1:8080")
    assert ok is True


def test_cloud_metadata_blocked():
    """AWS/GCP metadata endpoint is blocked."""
    ok, err = _validate_url("http://169.254.169.254/latest/meta-data/")
    assert ok is False
    assert "link-local" in err.lower() or "blocked" in err.lower()


def test_google_metadata_blocked():
    """GCP metadata hostname is blocked."""
    ok, err = _validate_url("http://metadata.google.internal/computeMetadata/v1/")
    assert ok is False
    assert "blocked" in err.lower() or "deny" in err.lower()


def test_custom_deny_list():
    """Custom deny list blocks specified hosts."""
    ok, err = _validate_url("http://evil.com", deny_list=["evil.com"])
    assert ok is False
    assert "deny" in err.lower()


def test_custom_deny_list_allows_others():
    """Custom deny list doesn't affect other hosts."""
    ok, _ = _validate_url("http://good.com", deny_list=["evil.com"])
    assert ok is True


def test_non_http_scheme_rejected():
    """Non-HTTP schemes are rejected."""
    ok, err = _validate_url("ftp://example.com")
    assert ok is False
    assert "http" in err.lower()


def test_missing_domain_rejected():
    """URLs without domains are rejected."""
    ok, err = _validate_url("http://")
    assert ok is False
