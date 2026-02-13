"""Tests for local web search consent (Phase 3C)."""

import pytest

from nanobot.copilot.approval.patterns import (
    AUTO_APPROVE,
    ApprovalRequired,
    RulesEngine,
)


@pytest.fixture
def rules(tmp_path):
    """RulesEngine with a temporary DB (no tables needed for these tests)."""
    db = tmp_path / "test.db"
    db.touch()
    engine = RulesEngine(db)
    return engine


# --- Route context management ---


def test_set_and_clear_route_context(rules):
    """Route context can be set and cleared."""
    rules.set_route_context(target="local", reason="default")
    assert rules._route_context == {"target": "local", "reason": "default"}

    rules.clear_route_context()
    assert rules._route_context == {}


# --- web_search consent: auto-local default route ---


@pytest.mark.asyncio
async def test_web_search_auto_local_requires_consent(rules):
    """web_search on auto-local (reason=default) requires consent."""
    rules.set_route_context(target="local", reason="default")
    result = await rules.check("web_search", {"query": "latest news"})
    assert result is not None
    assert isinstance(result, ApprovalRequired)
    assert "latest news" in result.reason
    assert result.reroute_on_deny == "fast"


# --- web_search consent: private mode ---


@pytest.mark.asyncio
async def test_web_search_private_mode_auto_approved(rules):
    """web_search in private mode is auto-approved (no consent needed)."""
    rules.set_route_context(target="local", reason="private_mode")
    result = await rules.check("web_search", {"query": "test"})
    assert result is None


# --- web_search consent: user downgrade ---


@pytest.mark.asyncio
async def test_web_search_user_downgrade_auto_approved(rules):
    """web_search with user_downgrade is auto-approved."""
    rules.set_route_context(target="local", reason="user_downgrade")
    result = await rules.check("web_search", {"query": "test"})
    assert result is None


# --- web_search consent: cloud routes ---


@pytest.mark.asyncio
async def test_web_search_fast_route_auto_approved(rules):
    """web_search on fast route doesn't require consent."""
    rules.set_route_context(target="fast", reason="token_accumulation")
    result = await rules.check("web_search", {"query": "test"})
    assert result is None


@pytest.mark.asyncio
async def test_web_search_big_route_auto_approved(rules):
    """web_search on big route doesn't require consent."""
    rules.set_route_context(target="big", reason="images")
    result = await rules.check("web_search", {"query": "test"})
    assert result is None


# --- web_search consent: no route context (non-copilot mode) ---


@pytest.mark.asyncio
async def test_web_search_no_context_auto_approved(rules):
    """web_search without route context is auto-approved (backward compat)."""
    # No set_route_context called — simulates non-copilot (standalone) mode
    result = await rules.check("web_search", {"query": "test"})
    assert result is None


# --- Other tools unaffected ---


@pytest.mark.asyncio
async def test_other_auto_approve_tools_unaffected(rules):
    """Other AUTO_APPROVE tools don't gain consent requirements."""
    rules.set_route_context(target="local", reason="default")
    for tool in ("web_fetch", "read_file", "list_files", "memory_search"):
        result = await rules.check(tool, {})
        assert result is None, f"{tool} should be auto-approved"


# --- Long query truncation in reason ---


@pytest.mark.asyncio
async def test_consent_reason_truncates_long_query(rules):
    """Consent prompt truncates very long queries."""
    rules.set_route_context(target="local", reason="default")
    long_query = "x" * 200
    result = await rules.check("web_search", {"query": long_query})
    assert result is not None
    # Query in reason should be truncated to 100 chars
    assert len(result.reason) < 200


# --- RouterProvider force_route ---


@pytest.mark.asyncio
async def test_router_force_route():
    """RouterProvider.chat() with force_route skips heuristics."""
    from unittest.mock import AsyncMock, MagicMock

    from nanobot.copilot.routing.router import RouterProvider

    # Mock providers
    local = MagicMock()
    cloud = MagicMock()
    cost_logger = MagicMock()
    cost_logger.log_route = AsyncMock()
    cost_logger.log_call = AsyncMock()
    cost_logger.calculate_cost = MagicMock(return_value=0.0)

    router = RouterProvider(
        local_provider=local,
        cloud_providers={"openrouter": cloud},
        cost_logger=cost_logger,
    )

    # Mock the failover to return a response
    from nanobot.providers.base import LLMResponse
    from nanobot.copilot.routing.failover import ProviderTier

    mock_response = LLMResponse(
        content="Hello",
        usage={"prompt_tokens": 10, "completion_tokens": 5},
        model_used="anthropic/claude-3-haiku-20240307",
    )
    mock_tier = ProviderTier("openrouter", cloud, "anthropic/claude-3-haiku-20240307")
    router._failover.try_providers = AsyncMock(
        return_value=(mock_response, mock_tier, 100.0)
    )

    messages = [{"role": "user", "content": "hello"}]
    result = await router.chat(messages, force_route="fast")

    assert result.content == "Hello"
    # Verify the last_decision was set to the forced route
    assert router.last_decision.target == "fast"
    assert router.last_decision.reason == "consent_reroute"


@pytest.mark.asyncio
async def test_router_last_decision_tracks_normal_route():
    """RouterProvider tracks last_decision for normal routing."""
    from unittest.mock import AsyncMock, MagicMock

    from nanobot.copilot.routing.router import RouterProvider
    from nanobot.providers.base import LLMResponse
    from nanobot.copilot.routing.failover import ProviderTier

    local = MagicMock()
    cloud = MagicMock()
    cost_logger = MagicMock()
    cost_logger.log_route = AsyncMock()
    cost_logger.log_call = AsyncMock()
    cost_logger.calculate_cost = MagicMock(return_value=0.0)

    router = RouterProvider(
        local_provider=local,
        cloud_providers={"openrouter": cloud},
        cost_logger=cost_logger,
    )

    mock_response = LLMResponse(
        content="Hi",
        usage={"prompt_tokens": 10, "completion_tokens": 5},
        model_used="qwen2.5-14b-instruct",
    )
    mock_tier = ProviderTier("lm_studio", local, "qwen2.5-14b-instruct")
    router._failover.try_providers = AsyncMock(
        return_value=(mock_response, mock_tier, 50.0)
    )

    messages = [{"role": "system", "content": "You are helpful."}, {"role": "user", "content": "hello"}]
    await router.chat(messages)

    assert router.last_decision is not None
    assert router.last_decision.target == "local"
    assert router.last_decision.reason == "default"
