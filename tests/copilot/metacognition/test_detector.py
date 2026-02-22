"""Test satisfaction detector."""

import pytest

from nanobot.copilot.metacognition.detector import SatisfactionDetector


@pytest.fixture
def detector():
    """Create detector without lesson manager."""
    return SatisfactionDetector(lesson_manager=None)


def test_detect_negative_signals(detector):
    """Negative satisfaction signals are detected."""
    negative_cases = [
        "try again",
        "that's wrong",
        "no that's not right",
        "you're wrong about this",
        "not what I asked for",
        "terrible response",
        "awful job",
        "that's useless",
    ]
    for text in negative_cases:
        result = detector.detect_regex(text)
        assert result is not None, f"Failed for: {text}"
        polarity, confidence = result
        assert polarity == "negative"
        assert confidence >= 0.8


def test_detect_positive_signals(detector):
    """Positive satisfaction signals are detected."""
    positive_cases = [
        "perfect!",
        "thanks so much",
        "great work",
        "exactly what I needed",
        "well done",
        "nice job",
        "good job",
        "that's right",
    ]
    for text in positive_cases:
        result = detector.detect_regex(text)
        assert result is not None, f"Failed for: {text}"
        polarity, confidence = result
        assert polarity == "positive"
        assert confidence >= 0.7


def test_neutral_messages_ignored(detector):
    """Neutral messages don't trigger satisfaction detection."""
    neutral_cases = [
        "hello",
        "what time is it?",
        "tell me about Python",
        "how does this work?",
    ]
    for text in neutral_cases:
        result = detector.detect_regex(text)
        assert result is None, f"False positive for: {text}"
