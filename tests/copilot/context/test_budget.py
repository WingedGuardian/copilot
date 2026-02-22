"""Test token budget calculator."""


from nanobot.copilot.context.budget import TokenBudget


def test_get_window_known_model():
    """Known models return correct window size."""
    budget = TokenBudget()

    assert budget.get_window("anthropic/claude-sonnet-4-20250514") == 200_000
    assert budget.get_window("llama-3.2-3b-instruct") == 8_192


def test_get_window_unknown_model():
    """Unknown models return conservative default."""
    budget = TokenBudget()

    assert budget.get_window("unknown-model") == 128_000


def test_get_budget_with_fill_percent():
    """Budget calculation respects fill percentage."""
    budget = TokenBudget()

    # 200k window, 75% fill = 150k budget
    assert budget.get_budget("anthropic/claude-sonnet-4-20250514") == 150_000

    # Custom fill percent: 50%
    assert budget.get_budget("anthropic/claude-sonnet-4-20250514", fill_percent=0.5) == 100_000


def test_count_tokens():
    """Token counting works with fallback."""
    budget = TokenBudget()

    # Should use tiktoken if available, else len/4
    count = budget.count_tokens("hello world")
    assert count > 0
    assert count < 100


def test_count_messages_tokens():
    """Counts tokens across message list."""
    budget = TokenBudget()

    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"},
        {"role": "assistant", "content": "Hi there!"},
    ]

    total = budget.count_messages_tokens(messages)
    assert total > 0
    # Should be roughly (30 + 6 + 9) / 4 = ~11 tokens minimum
    assert total >= 10


def test_count_messages_multimodal():
    """Handles multimodal content correctly."""
    budget = TokenBudget()

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What's in this image?"},
                {"type": "image_url", "image_url": {"url": "data:..."}},
            ],
        }
    ]

    # Should count only text parts
    total = budget.count_messages_tokens(messages)
    assert total > 0


def test_needs_continuation():
    """Detects when continuation is needed."""
    budget = TokenBudget()

    # Small messages, 8k window, 70% threshold = 5.6k tokens
    small_messages = [
        {"role": "user", "content": "x" * 100},
    ]
    assert not budget.needs_continuation(small_messages, "llama-3.2-3b-instruct")

    # Large messages exceeding threshold: 8192 * 0.70 = 5734 tokens needed
    # With tiktoken, "x" repeated gets ~8 tokens per 64 chars, so need ~46k chars
    large_messages = [
        {"role": "user", "content": "x" * 50000},
    ]
    assert budget.needs_continuation(large_messages, "llama-3.2-3b-instruct")
