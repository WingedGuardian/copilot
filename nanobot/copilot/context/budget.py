"""Token budget calculator for context assembly."""

from typing import Any

# Known context window sizes (tokens).
_MODEL_WINDOWS: dict[str, int] = {
    # Local
    "llama-3.2-3b-instruct": 8_192,
    "microsoft/phi-4-mini-reasoning": 16_384,
    "mistral-small-3.2-24b-instruct": 32_768,
    # Cloud — Anthropic
    # Sonnet 4.6 and Opus 4.6 support 1M tokens in beta
    # (requires anthropic-beta: context-1m-2025-08-07 header).
    # Default without the header is 200K. Use 200K here until we add that header.
    "anthropic/claude-3-haiku-20240307": 200_000,
    "anthropic/claude-3-5-haiku-20241022": 200_000,
    "anthropic/claude-haiku-4.5": 200_000,
    "anthropic/claude-haiku-4-5": 200_000,
    "anthropic/claude-sonnet-4-20250514": 200_000,
    "anthropic/claude-sonnet-4-6": 200_000,
    "anthropic/claude-opus-4-20250514": 200_000,
    "anthropic/claude-opus-4.6": 200_000,
    "anthropic/claude-opus-4-6": 200_000,
}

# Conservative default for unknown models.
_DEFAULT_WINDOW = 8_192


def _try_tiktoken(text: str) -> int | None:
    """Count tokens with tiktoken if available."""
    try:
        import tiktoken  # noqa: F811
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return None


class TokenBudget:
    """Tracks and manages token budgets for context assembly."""

    def get_window(self, model: str) -> int:
        """Return the context window size for *model*."""
        return _MODEL_WINDOWS.get(model, _DEFAULT_WINDOW)

    def get_budget(self, model: str, fill_percent: float = 0.75) -> int:
        """Max tokens to fill before leaving room for the response."""
        return int(self.get_window(model) * fill_percent)

    def count_tokens(self, text: str) -> int:
        """Estimate token count.  Uses tiktoken if installed, else len/4."""
        n = _try_tiktoken(text)
        if n is not None:
            return n
        return max(1, len(text) // 4)

    def count_messages_tokens(self, messages: list[dict[str, Any]]) -> int:
        """Rough token count across an entire messages list."""
        total = 0
        for msg in messages:
            c = msg.get("content", "")
            if isinstance(c, str):
                total += self.count_tokens(c)
            elif isinstance(c, list):
                for part in c:
                    if isinstance(part, dict) and part.get("type") == "text":
                        total += self.count_tokens(part.get("text", ""))
        return total

    def needs_continuation(
        self,
        messages: list[dict[str, Any]],
        model: str,
        threshold: float = 0.70,
    ) -> bool:
        """True if current token usage exceeds *threshold* of the model budget."""
        used = self.count_messages_tokens(messages)
        window = self.get_window(model)
        return used > int(window * threshold)
