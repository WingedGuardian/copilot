"""Failover chain for LLM providers."""

import time
from dataclasses import dataclass
from typing import Any

from loguru import logger

from nanobot.providers.base import LLMProvider, LLMResponse


@dataclass
class ProviderTier:
    """A single tier in the failover chain."""

    name: str              # e.g. "lm_studio", "openrouter"
    provider: LLMProvider
    model: str


class FailoverChain:
    """Try providers in order until one succeeds."""

    async def try_providers(
        self,
        chain: list[ProviderTier],
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> tuple[LLMResponse, ProviderTier, int]:
        """Attempt each provider in sequence.

        Returns:
            Tuple of (response, tier_that_succeeded, latency_ms).

        Raises:
            RuntimeError: If all providers fail.
        """
        last_error: Exception | None = None

        for tier in chain:
            start = time.monotonic()
            try:
                response = await tier.provider.chat(
                    messages=messages,
                    tools=tools,
                    model=tier.model,
                    **kwargs,
                )
                latency_ms = int((time.monotonic() - start) * 1000)

                # LiteLLMProvider returns errors as content instead of raising.
                # Treat "Error calling LLM:" responses as failures so we
                # continue down the chain.
                if (
                    response.content
                    and response.content.startswith("Error calling LLM:")
                    and response.finish_reason == "error"
                ):
                    raise RuntimeError(response.content)

                response.model_used = tier.model
                return response, tier, latency_ms

            except Exception as e:
                latency_ms = int((time.monotonic() - start) * 1000)
                last_error = e
                logger.warning(
                    f"Provider {tier.name} ({tier.model}) failed in {latency_ms}ms: {e}"
                )
                continue

        raise RuntimeError(
            f"All providers failed. Last error: {last_error}"
        )
