"""Phase 2 tests: Provider & Infrastructure Resilience."""

import time
from unittest.mock import AsyncMock

import pytest

# ---------------------------------------------------------------------------
# 2A. Circuit Breaker
# ---------------------------------------------------------------------------

def test_circuit_breaker_starts_closed():
    """New provider should have closed circuit."""
    from nanobot.copilot.routing.failover import CircuitBreaker

    cb = CircuitBreaker()
    assert not cb.is_open("provider_a")


def test_circuit_breaker_opens_after_threshold():
    """Circuit should open after failure_threshold failures."""
    from nanobot.copilot.routing.failover import CircuitBreaker

    cb = CircuitBreaker(failure_threshold=3, window_s=60.0, cooldown_s=300.0)
    cb.record_failure("p")
    cb.record_failure("p")
    assert not cb.is_open("p")
    cb.record_failure("p")
    assert cb.is_open("p")


def test_circuit_breaker_resets_on_success():
    """Circuit should close after a successful call."""
    from nanobot.copilot.routing.failover import CircuitBreaker

    cb = CircuitBreaker(failure_threshold=2, cooldown_s=9999.0)
    cb.record_failure("p")
    cb.record_failure("p")
    assert cb.is_open("p")  # open, cooldown hasn't elapsed
    cb.record_success("p")
    assert not cb.is_open("p")  # closed after success


def test_circuit_breaker_half_open_probe_failure():
    """Half-open probe failure should re-open circuit."""
    from nanobot.copilot.routing.failover import CircuitBreaker

    cb = CircuitBreaker(failure_threshold=2, cooldown_s=0.0)
    cb.record_failure("p")
    cb.record_failure("p")
    # Force half-open by checking (cooldown=0)
    cb.is_open("p")  # transitions to half-open
    cb.record_failure("p")  # probe failed, back to open
    # Check internal state (is_open with cooldown=0 would immediately transition again)
    assert cb._get("p")["state"] == "open"
    assert cb._get("p")["opened_at"] > 0


@pytest.mark.asyncio
async def test_failover_skips_open_circuit():
    """FailoverChain should skip providers with open circuits."""
    from nanobot.copilot.routing.failover import FailoverChain, ProviderTier
    from nanobot.providers.base import LLMResponse

    chain = FailoverChain()
    # Manually open circuit for provider_a
    chain._breaker._states["bad"] = {"failures": [time.time()] * 5, "state": "open", "opened_at": time.time()}

    good_provider = AsyncMock()
    good_provider.chat = AsyncMock(return_value=LLMResponse(content="ok"))

    tiers = [
        ProviderTier(name="bad", provider=AsyncMock(), model="m"),
        ProviderTier(name="good", provider=good_provider, model="m"),
    ]

    resp, tier, _ = await chain.try_providers(tiers, messages=[])
    assert tier.name == "good"


# ---------------------------------------------------------------------------
# 2B. Channel Restart Supervisor
# ---------------------------------------------------------------------------

def test_channel_manager_has_supervisor():
    """ChannelManager should have _supervise_channels method."""
    from nanobot.channels.manager import ChannelManager

    assert hasattr(ChannelManager, '_supervise_channels')


# ---------------------------------------------------------------------------
# 2C. Redis — REMOVED (Redis killed in memory architecture redesign)
# ---------------------------------------------------------------------------
