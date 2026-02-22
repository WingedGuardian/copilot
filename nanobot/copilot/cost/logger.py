"""Cost logging for all LLM calls and routing decisions."""

from pathlib import Path
from typing import Any

import aiosqlite
from loguru import logger

# Pricing per 1M tokens (input, output) in USD.
# Local models are free.  Cloud prices as of 2025-05.
_PRICING: dict[str, tuple[float, float]] = {
    # Local (free)
    "llama-3.2-3b-instruct": (0.0, 0.0),
    "microsoft/phi-4-mini-reasoning": (0.0, 0.0),
    "mistral-small-3.2-24b-instruct": (0.0, 0.0),
    "qwen2.5-14b-instruct": (0.0, 0.0),
    "huihui-qwen3-30b-a3b-instruct-2507-abliterated-i1@q4_k_m": (0.0, 0.0),
    "text-embedding-nomic-embed-text-v1.5": (0.0, 0.0),

    # OpenRouter / Anthropic (canonical + alias forms)
    "anthropic/claude-3-haiku-20240307": (0.25, 1.25),
    "anthropic/claude-3-5-haiku-20241022": (0.80, 4.00),
    "anthropic/claude-haiku-4.5": (0.80, 4.00),
    "anthropic/claude-haiku-4-5": (0.80, 4.00),
    "anthropic/claude-sonnet-4-20250514": (3.00, 15.00),
    "anthropic/claude-sonnet-4.5": (3.00, 15.00),
    "anthropic/claude-sonnet-4-6": (3.00, 15.00),
    "anthropic/claude-opus-4-20250514": (15.00, 75.00),
    "anthropic/claude-opus-4.6": (15.00, 75.00),
    "anthropic/claude-opus-4-6": (15.00, 75.00),

    # OpenAI
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),

    # DeepSeek
    "deepseek-chat": (0.27, 1.10),

    # Google Gemini
    "gemini-2.5-flash": (0.15, 0.60),
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-3-flash-preview": (0.0, 0.0),

    # MiniMax
    "MiniMax-M1": (0.15, 0.60),
    "MiniMax-M2.5": (0.30, 1.20),
    "MiniMax-M2.5-highspeed": (0.60, 2.40),

    # Groq whisper (per-minute pricing mapped to approximate per-1M-token)
    "whisper-large-v3": (0.0, 0.0),
}


class CostLogger:
    """Logs LLM call costs and routing decisions to SQLite."""

    def __init__(self, db_path: str | Path):
        self._db_path = str(db_path)

    def calculate_cost(
        self, model: str, tokens_in: int, tokens_out: int
    ) -> float:
        """Calculate cost in USD for a given call."""
        # Strip common prefixes for lookup
        clean = model
        for prefix in ("openrouter/", "openai/", "minimax/", "deepseek/", "gemini/"):
            if clean.startswith(prefix):
                clean = clean[len(prefix):]

        price_in, price_out = _PRICING.get(clean, (0.0, 0.0))
        if price_in or price_out:
            return (tokens_in * price_in + tokens_out * price_out) / 1_000_000
        # Fallback to litellm's pricing database
        try:
            from litellm import cost_per_token
            cost_in, cost_out = cost_per_token(
                model=model, prompt_tokens=tokens_in, completion_tokens=tokens_out,
            )
            return cost_in + cost_out
        except Exception:
            return 0.0

    async def log_call(
        self,
        model: str,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float | None = None,
        thread_id: str | None = None,
        task_type: str | None = None,
    ) -> None:
        """Insert a row into cost_log."""
        if cost_usd is None:
            cost_usd = self.calculate_cost(model, tokens_in, tokens_out)

        try:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    """INSERT INTO cost_log
                       (model, tokens_input, tokens_output, cost_usd, task_type, thread_id)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (model, tokens_in, tokens_out, cost_usd, task_type, thread_id),
                )
                await db.commit()
        except Exception as e:
            logger.warning(f"Failed to log cost: {e}")

    async def log_route(
        self,
        input_length: int,
        has_images: bool,
        routed_to: str,
        provider: str,
        model_used: str,
        route_reason: str,
        success: bool = True,
        latency_ms: int = 0,
        failure_reason: str | None = None,
        cost_usd: float = 0.0,
        thread_id: str | None = None,
    ) -> None:
        """Insert a row into routing_log."""
        try:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    """INSERT INTO routing_log
                       (input_length, has_images, routed_to, provider, model_used,
                        route_reason, success, latency_ms, failure_reason, cost_usd, thread_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        input_length,
                        has_images,
                        routed_to,
                        provider,
                        model_used,
                        route_reason,
                        success,
                        latency_ms,
                        failure_reason,
                        cost_usd,
                        thread_id,
                    ),
                )
                await db.commit()
        except Exception as e:
            logger.warning(f"Failed to log route: {e}")
