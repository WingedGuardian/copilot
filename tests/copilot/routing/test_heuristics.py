"""Test routing heuristics classifier."""

import pytest

from nanobot.copilot.routing.heuristics import classify


def test_images_route_to_big():
    """Images always route to big model."""
    decision = classify("hello", has_images=True, token_count=100)
    assert decision.target == "big"
    assert decision.reason == "images"
    assert "sonnet" in decision.model


def test_long_input_routes_to_big():
    """Messages > 4096 chars route to big model."""
    long_text = "x" * 5000
    decision = classify(long_text, has_images=False, token_count=100)
    assert decision.target == "big"
    assert decision.reason == "overflow"


def test_explicit_upgrade_intent():
    """User saying 'think hard' routes to big model."""
    upgrade_phrases = [
        "think hard about this",
        "let's brainstorm some ideas",
        "take your time on this one",
        "this is important",
        "use the big model",
        "use claude for this",
    ]
    for phrase in upgrade_phrases:
        decision = classify(phrase, has_images=False, token_count=100)
        assert decision.target == "big", f"Failed for phrase: {phrase}"
        assert decision.reason == "user_upgrade"


def test_explicit_downgrade_intent():
    """User saying 'quick question' routes to local model."""
    downgrade_phrases = [
        "quick question",
        "just a quick thing",
        "simple question",
        "keep it simple",
        "don't overthink this",
        "use the local model",
    ]
    for phrase in downgrade_phrases:
        decision = classify(phrase, has_images=False, token_count=100)
        assert decision.target == "local", f"Failed for phrase: {phrase}"
        assert decision.reason == "user_downgrade"


def test_high_token_count_routes_to_fast():
    """Conversations with > 3000 tokens route to fast model."""
    decision = classify("hello", has_images=False, token_count=3500)
    assert decision.target == "fast"
    assert decision.reason == "token_accumulation"
    assert "haiku" in decision.model


def test_lesson_override():
    """High-confidence lessons override default routing."""
    lessons = [
        {
            "trigger_pattern": "deploy",
            "route_target": "big",
            "confidence": 0.80,
        }
    ]
    decision = classify(
        "deploy to production",
        has_images=False,
        token_count=100,
        lessons=lessons,
    )
    assert decision.target == "big"
    assert decision.reason == "lesson"


def test_low_confidence_lesson_ignored():
    """Lessons below 0.70 confidence are ignored."""
    lessons = [
        {
            "trigger_pattern": "deploy",
            "route_target": "big",
            "confidence": 0.60,
        }
    ]
    decision = classify(
        "deploy to production",
        has_images=False,
        token_count=100,
        lessons=lessons,
    )
    # Falls through to complexity pattern (deploy is a complexity keyword)
    assert decision.target == "big"
    assert decision.reason == "complexity"


def test_complexity_patterns():
    """Code blocks and multi-step tasks route to big model."""
    complexity_cases = [
        "```python\nprint('hello')\n```",
        "first do this, then do that, finally verify",
        "debug this kubernetes deployment",
        "refactor the authentication module",
        "optimize this SQL query",
    ]
    for text in complexity_cases:
        decision = classify(text, has_images=False, token_count=100)
        assert decision.target == "big", f"Failed for text: {text[:50]}"
        assert decision.reason == "complexity"


def test_default_routes_to_local():
    """Simple conversational messages route to local model."""
    simple_cases = [
        "hello",
        "how are you?",
        "what time is it?",
        "tell me a joke",
        "what's 2 + 2?",
    ]
    for text in simple_cases:
        decision = classify(text, has_images=False, token_count=100)
        assert decision.target == "local", f"Failed for text: {text}"
        assert decision.reason == "default"


def test_custom_model_names():
    """Custom model names are respected."""
    decision = classify(
        "hello",
        has_images=False,
        token_count=100,
        local_model="custom-local",
        fast_model="custom-fast",
        big_model="custom-big",
    )
    assert decision.model == "custom-local"


def test_priority_order():
    """Explicit user intent overrides complexity patterns."""
    # Message has both complexity keyword (kubernetes) and downgrade intent
    decision = classify(
        "quick question about kubernetes",
        has_images=False,
        token_count=100,
    )
    # Downgrade intent (rule 4) beats complexity (rule 7)
    assert decision.target == "local"
    assert decision.reason == "user_downgrade"
