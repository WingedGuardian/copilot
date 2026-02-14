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
    is_local: bool = False  # True for LM Studio / local models (tools stripped)


class CircuitBreaker:
    """Per-provider circuit breaker: opens after repeated failures, auto-resets after cooldown."""

    def __init__(self, failure_threshold: int = 3, window_s: float = 300.0, cooldown_s: float = 300.0):
        self._failure_threshold = failure_threshold
        self._window_s = window_s
        self._cooldown_s = cooldown_s
        self._states: dict[str, dict] = {}  # provider_name -> {failures: [...timestamps], state, opened_at}

    def _get(self, name: str) -> dict:
        if name not in self._states:
            self._states[name] = {"failures": [], "state": "closed", "opened_at": 0.0}
        return self._states[name]

    def is_open(self, name: str) -> bool:
        """Check if circuit is open (should skip provider)."""
        s = self._get(name)
        if s["state"] == "closed":
            return False
        if s["state"] == "open":
            # Check if cooldown elapsed -> half-open
            if time.time() - s["opened_at"] >= self._cooldown_s:
                s["state"] = "half-open"
                logger.info(f"CircuitBreaker: {name} -> half-open (probe allowed)")
                return False
            return True
        # half-open: allow one probe
        return False

    def record_success(self, name: str) -> None:
        """Record a successful call — reset circuit."""
        s = self._get(name)
        s["failures"] = []
        if s["state"] != "closed":
            logger.info(f"CircuitBreaker: {name} -> closed (recovered)")
        s["state"] = "closed"
        s["opened_at"] = 0.0

    def record_failure(self, name: str) -> None:
        """Record a failure — may trip the circuit."""
        s = self._get(name)
        now = time.time()
        # Prune old failures outside window
        s["failures"] = [t for t in s["failures"] if now - t < self._window_s]
        s["failures"].append(now)

        if s["state"] == "half-open":
            # Probe failed -> back to open
            s["state"] = "open"
            s["opened_at"] = now
            logger.warning(f"CircuitBreaker: {name} -> open (probe failed)")
            from nanobot.copilot.alerting.bus import get_alert_bus
            import asyncio; asyncio.ensure_future(get_alert_bus().alert("llm", "medium", f"LLM provider '{name}' circuit opened", "provider_failed"))
        elif len(s["failures"]) >= self._failure_threshold:
            s["state"] = "open"
            s["opened_at"] = now
            logger.warning(f"CircuitBreaker: {name} -> open ({len(s['failures'])} failures in {self._window_s}s)")


class FailoverChain:
    """Try providers in order until one succeeds."""

    def __init__(self) -> None:
        self._breaker = CircuitBreaker()

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
            # Skip if circuit is open
            if self._breaker.is_open(tier.name):
                logger.info(f"CircuitBreaker: skipping {tier.name} (circuit open)")
                continue

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
                self._breaker.record_success(tier.name)
                return response, tier, latency_ms

            except Exception as e:
                latency_ms = int((time.monotonic() - start) * 1000)
                last_error = e
                self._breaker.record_failure(tier.name)
                logger.warning(
                    f"Provider {tier.name} ({tier.model}) failed in {latency_ms}ms: {e}"
                )
                continue

        raise RuntimeError(
            f"All providers failed. Last error: {last_error}"
        )
