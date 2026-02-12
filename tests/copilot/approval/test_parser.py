"""Test approval response parser."""

import pytest

from nanobot.copilot.approval.parser import NLApprovalParser


@pytest.fixture
def parser():
    """Create parser instance."""
    return NLApprovalParser()


def test_clear_approve(parser):
    """Clear approval responses are detected."""
    approve_cases = [
        "yes",
        "yeah",
        "yep",
        "go",
        "do it",
        "approved",
        "ok",
        "sure",
        "go ahead",
        "go for it",
    ]
    for text in approve_cases:
        response = parser.parse(text)
        assert response.intent == "approve", f"Failed for: {text}"
        assert response.confidence >= 0.9


def test_clear_deny(parser):
    """Clear denial responses are detected."""
    deny_cases = [
        "no",
        "nope",
        "don't",
        "deny",
        "denied",
        "stop",
        "cancel",
        "not now",
        "hold",
    ]
    for text in deny_cases:
        response = parser.parse(text)
        assert response.intent == "deny", f"Failed for: {text}"
        assert response.confidence >= 0.9


def test_modify_intent(parser):
    """Modification requests are detected."""
    modify_cases = [
        "change the subject line",
        "modify the command",
        "update the parameter",
        "replace foo with bar",
        "instead use baz",
        "but with different args",
    ]
    for text in modify_cases:
        response = parser.parse(text)
        assert response.intent == "modify", f"Failed for: {text}"
        assert response.confidence >= 0.7


def test_unclear_responses(parser):
    """Ambiguous responses return unclear intent."""
    unclear_cases = [
        "hmm",
        "maybe",
        "I don't know",
        "what do you think?",
        "is this safe?",
    ]
    for text in unclear_cases:
        response = parser.parse(text)
        assert response.intent == "unclear", f"Failed for: {text}"


def test_rule_creation_detection(parser):
    """Detects when user is creating a dynamic rule."""
    rule_cases = [
        "auto-approve this from now on",
        "always allow git push",
        "always approve shell commands",
        "from now on just do it",
    ]
    for text in rule_cases:
        result = parser.detect_rule_creation(text)
        assert result is not None, f"Failed to detect rule in: {text}"


def test_no_false_positive_rules(parser):
    """Normal responses don't trigger rule creation."""
    normal_cases = [
        "yes",
        "no",
        "change the subject",
        "what does this do?",
    ]
    for text in normal_cases:
        result = parser.detect_rule_creation(text)
        assert result is None, f"False positive for: {text}"
