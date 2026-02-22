"""Test PlanRoutingTool — propose/activate/show/clear."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from nanobot.copilot.tools.plan_routing import PlanRoutingTool
from nanobot.providers.base import LLMResponse


def _make_tool(routing_plan=None, tmp_path=None):
    """Create a PlanRoutingTool with mocks."""
    router = MagicMock()
    router._routing_plan = routing_plan or []
    router._cloud = {
        "gemini": MagicMock(),
        "minimax": MagicMock(),
        "openai": MagicMock(),
    }
    router._default_model = "MiniMax-M2.5"
    router._escalation_model = "anthropic/claude-sonnet-4-6"
    router._emergency_cloud_model = "openai/gpt-4o-mini"
    router._last_known_working = None
    router.set_routing_plan = MagicMock()

    config_path = (tmp_path / "config.json") if tmp_path else Path("/tmp/test_config.json")
    copilot = MagicMock()
    copilot.routing_plan = routing_plan or []

    return PlanRoutingTool(router=router, config_path=config_path, copilot_config=copilot)


@pytest.mark.asyncio
async def test_show_no_plan():
    """Show with no plan returns default info."""
    tool = _make_tool()
    result = await tool.execute(action="show")
    assert "No routing plan" in result
    assert "MiniMax-M2.5" in result


@pytest.mark.asyncio
async def test_show_with_plan():
    """Show with a plan lists entries."""
    plan = [
        {"provider": "gemini", "model": "flash", "reason": "free"},
        {"provider": "minimax", "model": "M2.5", "reason": "cheap"},
    ]
    tool = _make_tool(routing_plan=plan)
    result = await tool.execute(action="show")
    assert "gemini" in result
    assert "minimax" in result
    assert "free" in result


@pytest.mark.asyncio
async def test_propose_validates_entries():
    """Propose sends API probes and reports results."""
    tool = _make_tool()
    # Mock the cloud provider's chat method
    ok_resp = LLMResponse(content="hi", finish_reason="stop", model_used="test", usage={})

    for name, provider in tool._router._cloud.items():
        provider.chat = AsyncMock(return_value=ok_resp)

    plan = [
        {"provider": "gemini", "model": "gemini-3-flash-preview"},
        {"provider": "minimax", "model": "MiniMax-M2.5"},
    ]
    result = await tool.execute(action="propose", plan=plan)
    assert "OK" in result
    assert "2/2" in result


@pytest.mark.asyncio
async def test_propose_reports_failed():
    """Propose reports failed probes accurately."""
    tool = _make_tool()
    # One succeeds, one fails
    ok_resp = LLMResponse(content="hi", finish_reason="stop", model_used="test", usage={})
    tool._router._cloud["gemini"].chat = AsyncMock(return_value=ok_resp)
    tool._router._cloud["minimax"].chat = AsyncMock(side_effect=Exception("Connection refused"))

    plan = [
        {"provider": "gemini", "model": "flash"},
        {"provider": "minimax", "model": "M2.5"},
    ]
    result = await tool.execute(action="propose", plan=plan)
    assert "1/2" in result
    assert "FAILED" in result
    assert "Connection refused" in result


@pytest.mark.asyncio
async def test_propose_unknown_provider():
    """Propose rejects unknown providers."""
    tool = _make_tool()
    plan = [{"provider": "nonexistent", "model": "foo"}]
    result = await tool.execute(action="propose", plan=plan)
    assert "FAILED" in result
    assert "not configured" in result


@pytest.mark.asyncio
async def test_activate_persists(tmp_path):
    """Activate sets the plan on the router and persists."""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"copilot": {}}))

    tool = _make_tool(tmp_path=tmp_path)
    tool._config_path = config_file

    plan = [{"provider": "gemini", "model": "flash", "reason": "free"}]
    result = await tool.execute(action="activate", plan=plan)

    assert "activated" in result
    tool._router.set_routing_plan.assert_called_once_with(plan)

    # Check persisted
    data = json.loads(config_file.read_text())
    assert data["copilot"]["routingPlan"] == plan


@pytest.mark.asyncio
async def test_clear_reverts(tmp_path):
    """Clear removes the plan."""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"copilot": {"routingPlan": [{"provider": "x", "model": "y"}]}}))

    tool = _make_tool(routing_plan=[{"provider": "x", "model": "y"}], tmp_path=tmp_path)
    tool._config_path = config_file

    result = await tool.execute(action="clear")
    assert "cleared" in result
    tool._router.set_routing_plan.assert_called_once_with([])


@pytest.mark.asyncio
async def test_activate_requires_plan():
    """Activate without plan returns error."""
    tool = _make_tool()
    result = await tool.execute(action="activate")
    assert "Error" in result
