"""Test extraction schemas."""


from nanobot.copilot.extraction.schemas import ExtractionResult


def test_extraction_result_validation():
    """ExtractionResult validates required fields."""
    # Valid result
    result = ExtractionResult(
        facts=["Python is a programming language"],
        decisions=["Use FastAPI for the API"],
        entities=["FastAPI", "API"],
        sentiment="neutral",
        topic="web development",
    )

    assert len(result.facts) == 1
    assert len(result.decisions) == 1
    assert len(result.entities) == 2
    assert result.sentiment == "neutral"


def test_extraction_empty_lists():
    """Empty lists are valid for optional fields."""
    result = ExtractionResult(
        facts=[],
        decisions=[],
        entities=[],
        sentiment="neutral",
        topic="general",
    )

    assert result.facts == []
    assert result.decisions == []
    assert result.entities == []


def test_extraction_result_has_tags():
    """ExtractionResult includes tags field."""
    result = ExtractionResult(
        facts=["hiccups are caused by diaphragm spasms"],
        tags=["hiccups", "diaphragm", "medical"],
    )
    assert result.tags == ["hiccups", "diaphragm", "medical"]


def test_extraction_result_tags_default_empty():
    """Tags default to empty list."""
    result = ExtractionResult()
    assert result.tags == []


def test_sentiment_values():
    """Valid sentiment values are accepted."""
    valid_sentiments = ["positive", "negative", "neutral", "frustrated"]

    for sentiment in valid_sentiments:
        result = ExtractionResult(
            facts=[],
            decisions=[],
            entities=[],
            sentiment=sentiment,
            topic="test",
        )
        assert result.sentiment == sentiment
