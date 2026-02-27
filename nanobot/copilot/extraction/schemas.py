"""Pydantic models for background extraction results."""

from pydantic import BaseModel, Field


class ExtractionResult(BaseModel):
    """Structured extraction from a single user↔assistant exchange."""

    facts: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    sentiment: str = "neutral"  # positive, negative, neutral, frustrated
    topic_shift: bool = False
    suggested_topic: str | None = None
    token_count_estimate: int = 0
    conversation_ts: float = 0.0  # When the exchange happened (for deferred processing)
