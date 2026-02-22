"""Test Router V2 -- plan-based routing, escalation, memory guard."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nanobot.providers.base import LLMResponse
from tests.copilot.routing.helpers import make_router


def _ok_resp(content="Hello!", model="MiniMax-M2.5"):
    return LLMResponse(
        content=content,
        finish_reason="stop",
        model_used=model,
        usage={"prompt_tokens": 10, "completion_tokens": 5},
    )


def _error_resp():
    return LLMResponse(
        content="Error calling LLM: connection failed",
        finish_reason="error",
        model_used="none",
        usage={},
    )


@pytest.mark.asyncio
async def test_default_routing_no_plan():
    """Without a plan, uses default model on all cloud providers."""
    router = make_router()
    messages = [{"role": "user", "content": "hello"}]

    with patch.object(router._failover, 'try_providers', new_callable=AsyncMock) as mock_try:
        from nanobot.copilot.routing.failover import ProviderTier
        tier = ProviderTier("minimax", MagicMock(), "MiniMax-M2.5")
        mock_try.return_value = (_ok_resp(), tier, 100)

        response = await router.chat(messages=messages)

    assert response.content == "Hello!"
    assert router._last_decision.target == "default"
    assert router._last_decision.reason == "default"


@pytest.mark.asyncio
async def test_plan_routing():
    """With a plan, routes via plan entries."""
    plan = [
        {"provider": "gemini", "model": "gemini-3-flash-preview", "reason": "free"},
        {"provider": "minimax", "model": "MiniMax-M2.5", "reason": "cheap"},
    ]
    router = make_router(routing_plan=plan)
    messages = [{"role": "user", "content": "hello"}]

    with patch.object(router._failover, 'try_providers', new_callable=AsyncMock) as mock_try:
        from nanobot.copilot.routing.failover import ProviderTier
        tier = ProviderTier("plan:gemini", MagicMock(), "gemini-3-flash-preview")
        mock_try.return_value = (_ok_resp("Hi!", "gemini-3-flash-preview"), tier, 50)

        await router.chat(messages=messages)

    assert router._last_decision.target == "plan"
    assert router._last_decision.reason == "routing_plan"


@pytest.mark.asyncio
async def test_escalation_retries_with_escalation_model():
    """[ESCALATE] marker triggers retry with escalation model."""
    router = make_router()
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "explain quantum computing"},
    ]

    from nanobot.copilot.routing.failover import ProviderTier

    escalate_resp = _ok_resp("[ESCALATE] This needs a stronger model")
    ok_resp_val = _ok_resp("Quantum computing uses qubits...", "anthropic/claude-sonnet-4-6")

    call_count = 0

    async def mock_try(chain, messages, tools=None, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            tier = ProviderTier("minimax", MagicMock(), "MiniMax-M2.5")
            return (escalate_resp, tier, 100)
        else:
            tier = ProviderTier("openai", MagicMock(), "anthropic/claude-sonnet-4-6")
            return (ok_resp_val, tier, 200)

    with patch.object(router._failover, 'try_providers', side_effect=mock_try):
        response = await router.chat(messages=messages)

    assert "qubits" in response.content
    assert call_count == 2


@pytest.mark.asyncio
async def test_private_mode_routes_local():
    """Private mode forces local routing."""
    router = make_router()
    messages = [{"role": "user", "content": "secret stuff"}]
    meta = {"private_mode": True}

    with patch.object(router._failover, 'try_providers', new_callable=AsyncMock) as mock_try:
        from nanobot.copilot.routing.failover import ProviderTier
        tier = ProviderTier("lm_studio", MagicMock(), "local-model", is_local=True)
        mock_try.return_value = (_ok_resp("OK"), tier, 50)

        await router.chat(messages=messages, session_metadata=meta)

    assert router._last_decision.target == "local"
    assert router._last_decision.reason == "private_mode"


@pytest.mark.asyncio
async def test_failover_notification():
    """When routing via safety/emergency tier, notification is appended."""
    router = make_router()
    router._notify_on_failover = True
    messages = [{"role": "user", "content": "hello"}]

    with patch.object(router._failover, 'try_providers', new_callable=AsyncMock) as mock_try:
        from nanobot.copilot.routing.failover import ProviderTier
        tier = ProviderTier("emergency:openai", MagicMock(), "openai/gpt-4o-mini")
        mock_try.return_value = (_ok_resp("Hi"), tier, 100)

        with patch("nanobot.copilot.alerting.bus.get_alert_bus") as mock_bus:
            mock_bus.return_value.alert = AsyncMock()
            response = await router.chat(messages=messages)

    assert "Routed via emergency:openai" in response.content
    assert router._in_failover is True


@pytest.mark.asyncio
async def test_last_known_working_tracked():
    """Successful calls on plan/default tiers update last_known_working."""
    router = make_router()
    messages = [{"role": "user", "content": "hello"}]

    with patch.object(router._failover, 'try_providers', new_callable=AsyncMock) as mock_try:
        from nanobot.copilot.routing.failover import ProviderTier
        tier = ProviderTier("minimax", MagicMock(), "MiniMax-M2.5")
        mock_try.return_value = (_ok_resp(), tier, 100)

        await router.chat(messages=messages)

    assert router._last_known_working == ("minimax", "MiniMax-M2.5")


def test_get_default_model():
    """get_default_model returns the default conversation model."""
    router = make_router()
    assert router.get_default_model() == "MiniMax-M2.5"
