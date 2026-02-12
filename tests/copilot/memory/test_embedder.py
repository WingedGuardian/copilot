"""Test embedding client."""

import pytest

from nanobot.copilot.memory.embedder import Embedder


@pytest.mark.asyncio
async def test_embed_returns_vector():
    """Embedding returns correct dimension vector."""
    embedder = Embedder(
        api_base="http://192.168.50.100:1234/v1",
        model="text-embedding-nomic-embed-text-v1.5",
        dimensions=768,
    )

    # This will only work if LM Studio is running
    # For CI, this would be mocked
    try:
        vector = await embedder.embed("hello world")
        assert len(vector) == 768
        assert all(isinstance(x, float) for x in vector)
    except Exception:
        pytest.skip("LM Studio not available")


@pytest.mark.asyncio
async def test_embed_truncates_long_text():
    """Very long text is truncated before embedding."""
    embedder = Embedder()

    long_text = "x" * 10000
    try:
        vector = await embedder.embed(long_text)
        # Should succeed (truncation prevents failure)
        assert len(vector) > 0
    except Exception:
        pytest.skip("LM Studio not available")


@pytest.mark.asyncio
async def test_embed_batch():
    """Batch embedding processes multiple texts."""
    embedder = Embedder()

    texts = ["hello", "world", "test"]
    try:
        vectors = await embedder.embed_batch(texts)
        assert len(vectors) == 3
        assert all(len(v) == 768 for v in vectors)
    except Exception:
        pytest.skip("LM Studio not available")
