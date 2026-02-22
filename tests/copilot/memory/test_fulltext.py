"""Tests for FTS5 full-text search and Reciprocal Rank Fusion."""

import os
import tempfile

import pytest

from nanobot.copilot.memory.episodic import Episode
from nanobot.copilot.memory.fulltext import FTSResult, FullTextStore, reciprocal_rank_fusion


@pytest.fixture
async def fts_store():
    """Create a temporary FTS store for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    store = FullTextStore(db_path=db_path)
    await store.ensure_table()
    yield store
    os.unlink(db_path)


@pytest.mark.asyncio
async def test_store_and_search(fts_store):
    """Basic store and search."""
    await fts_store.store("The error code XYZ-123 appeared in production", "sess1")
    await fts_store.store("User prefers dark mode for the UI", "sess1")
    await fts_store.store("Database migration completed successfully", "sess2")

    results = await fts_store.search("XYZ-123")
    assert len(results) >= 1
    assert "XYZ-123" in results[0].text


@pytest.mark.asyncio
async def test_search_no_results(fts_store):
    """Search with no matches returns empty list."""
    await fts_store.store("Some stored text", "sess1")
    results = await fts_store.search("nonexistent-query-xyz")
    assert results == []


@pytest.mark.asyncio
async def test_session_key_filter(fts_store):
    """Session key filters results."""
    await fts_store.store("Error in production deployment", "sess1")
    await fts_store.store("Error in staging environment", "sess2")

    results = await fts_store.search("Error", session_key="sess1")
    assert all(r.session_key == "sess1" for r in results)


@pytest.mark.asyncio
async def test_count(fts_store):
    """Count returns number of stored entries."""
    assert await fts_store.count() == 0
    await fts_store.store("Entry one", "sess1")
    await fts_store.store("Entry two", "sess1")
    assert await fts_store.count() == 2


@pytest.mark.asyncio
async def test_empty_query(fts_store):
    """Empty query returns empty results."""
    results = await fts_store.search("")
    assert results == []


def test_rrf_vector_only():
    """RRF with only vector results."""
    episodes = [
        Episode(id="1", text="Vector result 1", score=0.9),
        Episode(id="2", text="Vector result 2", score=0.8),
    ]
    combined = reciprocal_rank_fusion(episodes, [])
    assert len(combined) == 2
    assert combined[0]["text"] == "Vector result 1"


def test_rrf_fts_only():
    """RRF with only FTS results."""
    fts_results = [
        FTSResult(id=1, text="FTS result 1", session_key="s1", timestamp=0.0, importance=0.5, rank=-1.0),
        FTSResult(id=2, text="FTS result 2", session_key="s1", timestamp=0.0, importance=0.5, rank=-0.5),
    ]
    combined = reciprocal_rank_fusion([], fts_results)
    assert len(combined) == 2
    assert combined[0]["text"] == "FTS result 1"


def test_rrf_both_sources():
    """RRF combines and deduplicates results from both sources."""
    episodes = [
        Episode(id="1", text="Shared result about error XYZ", score=0.9),
        Episode(id="2", text="Vector only result", score=0.7),
    ]
    fts_results = [
        FTSResult(id=1, text="Shared result about error XYZ", session_key="s1",
                  timestamp=0.0, importance=0.5, rank=-1.0),
        FTSResult(id=2, text="FTS only keyword match", session_key="s1",
                  timestamp=0.0, importance=0.5, rank=-0.5),
    ]
    combined = reciprocal_rank_fusion(episodes, fts_results)

    # Shared result should rank highest (boosted by both sources)
    assert combined[0]["source"] == "both"
    assert combined[0]["score"] > combined[1]["score"]


def test_rrf_score_ordering():
    """RRF scores decrease with rank position."""
    episodes = [
        Episode(id=str(i), text=f"Result {i}", score=0.9 - i * 0.1)
        for i in range(5)
    ]
    combined = reciprocal_rank_fusion(episodes, [])
    scores = [item["score"] for item in combined]
    assert scores == sorted(scores, reverse=True)
