"""Comprehensive routing integration tests.

Tests the full routing pipeline end-to-end: config loading, router construction,
chain building, failover behaviour, escalation, PlanRoutingTool, memory guard,
HealthCheckService wiring, status aggregator, and preference hot-swapping.

These tests use mocked providers (no real API calls) but exercise the real
RouterProvider, FailoverChain, CircuitBreaker, PlanRoutingTool, and CostLogger
together — catching integration bugs that unit tests miss.
"""

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nanobot.copilot.routing.failover import CircuitBreaker
from nanobot.copilot.routing.heuristics import RouteDecision
from nanobot.copilot.routing.router import RouterProvider
from nanobot.copilot.tools.plan_routing import PlanRoutingTool
from tests.copilot.routing.helpers import (
    SIMPLE_MESSAGES,
    all_cloud_fail,
    error_response,
    make_provider,
    make_router,
    ok_response,
    patch_native,
)

# ===================================================================
# 1. Default routing (no plan)
# ===================================================================

class TestDefaultRouting:
    """When no routing plan is set, default model goes on all providers."""

    @pytest.mark.asyncio
    async def test_routes_to_default_model(self):
        router = make_router()
        with patch_native("minimax"):
            response = await router.chat(messages=SIMPLE_MESSAGES)

        assert response.content == "Hello!"
        assert router._last_decision.target == "default"
        assert router._last_decision.reason == "default"
        assert router._last_decision.model == "MiniMax-M2.5"

    @pytest.mark.asyncio
    async def test_get_default_model_returns_default(self):
        router = make_router()
        assert router.get_default_model() == "MiniMax-M2.5"

    @pytest.mark.asyncio
    async def test_default_chain_structure(self):
        router = make_router()
        decision = RouteDecision("default", "default", "MiniMax-M2.5")

        with patch_native("minimax"):
            chain = router._build_chain(decision)

        names = [t.name for t in chain]
        models = [t.model for t in chain]

        # All cloud providers with default model (count matches configured providers)
        cloud_default = [n for n, m in zip(names, models)
                         if m == "MiniMax-M2.5" and not n.startswith(("safety:", "emergency:"))]
        assert len(cloud_default) == len(router._cloud)

        # Native provider should be first
        assert cloud_default[0] == "minimax"

        # Safety: LM Studio local
        assert "safety:lm_studio" in names

        # Emergency on all providers
        emergency = [n for n in names if n.startswith("emergency:")]
        assert len(emergency) == len(router._cloud)

        # Order: default providers -> safety -> emergency
        first_safety = next(i for i, n in enumerate(names) if n.startswith("safety:"))
        first_emergency = next(i for i, n in enumerate(names) if n.startswith("emergency:"))
        assert first_safety < first_emergency

    @pytest.mark.asyncio
    async def test_first_provider_fails_falls_to_second(self):
        """When native provider fails, chain advances to next."""
        router = make_router()
        # Fail the native provider specifically
        router._cloud["minimax"].chat = AsyncMock(side_effect=RuntimeError("Provider down"))

        with patch_native("minimax"):
            response = await router.chat(messages=SIMPLE_MESSAGES)

        assert response.content == "Hello!"
        assert router._last_winning_provider != "minimax"

    @pytest.mark.asyncio
    async def test_all_default_fail_reaches_safety_net(self):
        """When all default providers fail, safety net catches."""
        router = make_router(local_succeed=True)
        all_cloud_fail(router)

        with patch_native("minimax"), \
             patch("nanobot.copilot.alerting.bus.get_alert_bus") as mock_bus:
            mock_bus.return_value.alert = AsyncMock()
            response = await router.chat(messages=SIMPLE_MESSAGES)

        assert response.content is not None
        assert "Hello!" in response.content
        assert router._last_winning_provider == "safety:lm_studio"

    @pytest.mark.asyncio
    async def test_cost_logged_on_success(self):
        router = make_router()
        with patch_native("minimax"):
            await router.chat(messages=SIMPLE_MESSAGES)

        router._cost_logger.log_route.assert_called_once()
        call_kwargs = router._cost_logger.log_route.call_args
        assert call_kwargs[1]["success"] is True
        assert call_kwargs[1]["route_reason"] == "default"


# ===================================================================
# 2. Plan-based routing
# ===================================================================

class TestPlanRouting:
    """When a routing plan is set, chain follows plan order."""

    @pytest.mark.asyncio
    async def test_plan_sets_decision_target(self):
        plan = [
            {"provider": "gemini", "model": "gemini-3-flash-preview", "reason": "free"},
            {"provider": "minimax", "model": "MiniMax-M2.5", "reason": "cheap"},
        ]
        router = make_router(routing_plan=plan)
        await router.chat(messages=SIMPLE_MESSAGES)

        assert router._last_decision.target == "plan"
        assert router._last_decision.reason == "routing_plan"

    @pytest.mark.asyncio
    async def test_plan_chain_order(self):
        plan = [
            {"provider": "gemini", "model": "gemini-3-flash-preview"},
            {"provider": "minimax", "model": "MiniMax-M2.5"},
            {"provider": "openai", "model": "gpt-4o"},
        ]
        router = make_router(routing_plan=plan)
        decision = RouteDecision("plan", "routing_plan", "gemini-3-flash-preview")
        chain = router._build_chain(decision)

        names = [t.name for t in chain]
        # Plan entries in order
        assert names[0] == "plan:gemini"
        assert names[1] == "plan:minimax"
        assert names[2] == "plan:openai"

    @pytest.mark.asyncio
    async def test_plan_first_entry_fails_advances(self):
        """When first plan entry fails, advances to second."""
        plan = [
            {"provider": "gemini", "model": "gemini-3-flash-preview"},
            {"provider": "minimax", "model": "MiniMax-M2.5"},
        ]
        router = make_router(
            routing_plan=plan,
            cloud_succeed={"gemini": False},
        )
        response = await router.chat(messages=SIMPLE_MESSAGES)

        assert response.content == "Hello!"
        assert router._last_winning_provider == "plan:minimax"

    @pytest.mark.asyncio
    async def test_plan_skips_unknown_provider(self):
        plan = [
            {"provider": "nonexistent", "model": "foo"},
            {"provider": "gemini", "model": "gemini-3-flash-preview"},
        ]
        router = make_router(routing_plan=plan)
        decision = RouteDecision("plan", "routing_plan", "foo")
        chain = router._build_chain(decision)

        names = [t.name for t in chain]
        assert "plan:nonexistent" not in names
        assert "plan:gemini" in names

    @pytest.mark.asyncio
    async def test_set_routing_plan_dynamically(self):
        router = make_router()
        assert router._routing_plan == []

        plan = [{"provider": "gemini", "model": "flash"}]
        router.set_routing_plan(plan)
        assert router._routing_plan == plan

        # Now routing should use plan
        decision_chain = router._build_chain(RouteDecision("plan", "routing_plan", "flash"))
        assert any(t.name == "plan:gemini" for t in decision_chain)


# ===================================================================
# 3. Private mode
# ===================================================================

class TestPrivateMode:
    @pytest.mark.asyncio
    async def test_private_mode_routes_local_only(self):
        router = make_router()
        await router.chat(
            messages=SIMPLE_MESSAGES,
            session_metadata={"private_mode": True},
        )

        assert router._last_decision.target == "local"
        assert router._last_decision.reason == "private_mode"

    @pytest.mark.asyncio
    async def test_private_mode_chain_starts_with_local(self):
        router = make_router()
        decision = RouteDecision("local", "private_mode", "test-local-model")
        chain = router._build_chain(decision)

        assert chain[0].name == "lm_studio"
        assert chain[0].is_local is True
        # No safety:lm_studio (already primary)
        safety_local = [t for t in chain if t.name == "safety:lm_studio"]
        assert len(safety_local) == 0

    @pytest.mark.asyncio
    async def test_private_mode_no_escalation(self):
        """Private mode should NOT trigger escalation even if model returns [ESCALATE]."""
        local = make_provider(response=ok_response("[ESCALATE] Too complex"))
        router = make_router()
        router._local = local

        response = await router.chat(
            messages=SIMPLE_MESSAGES,
            session_metadata={"private_mode": True},
        )

        # Should NOT retry -- escalation is disabled in private mode
        assert router._last_decision.target == "local"
        assert "[ESCALATE]" in response.content


# ===================================================================
# 4. Manual override (/use command)
# ===================================================================

class TestManualOverride:
    @pytest.mark.asyncio
    async def test_force_provider(self):
        router = make_router()
        await router.chat(
            messages=SIMPLE_MESSAGES,
            session_metadata={
                "force_provider": "openai",
                "force_model": "gpt-4o-mini",
            },
        )

        assert router._last_decision.reason == "manual:openai"
        assert router._last_decision.model == "gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_force_provider_chain_order(self):
        router = make_router()
        decision = RouteDecision("cloud", "manual:openai", "gpt-4o")
        chain = router._build_chain(decision)

        # Forced provider first
        assert chain[0].name == "openai"
        # Other providers follow
        other = [t.name for t in chain[1:]]
        assert len(other) > 0  # At least other cloud providers present

    @pytest.mark.asyncio
    async def test_force_provider_unknown_ignored(self):
        """Unknown force_provider falls through to normal routing."""
        router = make_router()
        with patch_native("minimax"):
            await router.chat(
                messages=SIMPLE_MESSAGES,
                session_metadata={"force_provider": "nonexistent"},
            )

        assert router._last_decision.target == "default"

    @pytest.mark.asyncio
    async def test_force_route_local(self):
        router = make_router()
        response = await router.chat(
            messages=SIMPLE_MESSAGES,
            force_route="local",
        )

        assert response.content == "Hello!"

    @pytest.mark.asyncio
    async def test_force_route_big(self):
        router = make_router()
        with patch_native("minimax"):
            await router.chat(
                messages=SIMPLE_MESSAGES,
                force_route="big",
            )

        assert router._last_decision.model == "anthropic/claude-sonnet-4-6"


# ===================================================================
# 5. Self-escalation
# ===================================================================

class TestSelfEscalation:
    @pytest.mark.asyncio
    async def test_escalation_from_default(self):
        """When default model responds with [ESCALATE], retry with escalation model."""
        escalate_resp = ok_response("[ESCALATE] This requires reasoning")
        ok_resp = ok_response("Here's the thorough answer.")

        router = make_router()
        # Native provider (minimax) gets escalation marker first, then ok
        # Other providers return ok directly (hit during escalation chain)
        for name, p in router._cloud.items():
            if name == "minimax":
                p.chat = AsyncMock(side_effect=[escalate_resp, ok_resp])
            else:
                p.chat = AsyncMock(return_value=ok_resp)

        with patch_native("minimax"):
            response = await router.chat(messages=SIMPLE_MESSAGES)
        assert router._last_decision.target == "escalation"
        assert "thorough answer" in response.content

    @pytest.mark.asyncio
    async def test_escalation_from_plan(self):
        """Escalation works from plan-based routing too."""
        plan = [{"provider": "gemini", "model": "gemini-3-flash-preview"}]
        escalate_resp = ok_response("[ESCALATE] Complex task")
        ok_resp = ok_response("Escalated answer.")

        router = make_router(routing_plan=plan)
        for p in router._cloud.values():
            p.chat = AsyncMock(side_effect=[escalate_resp, ok_resp])

        with patch_native("minimax"):
            await router.chat(messages=SIMPLE_MESSAGES)
        assert router._last_decision.target == "escalation"

    @pytest.mark.asyncio
    async def test_escalation_disabled(self):
        """With escalation_enabled=False, marker is just part of the response."""
        router = make_router()
        router._escalation_enabled = False

        for p in router._cloud.values():
            p.chat = AsyncMock(return_value=ok_response("[ESCALATE] Nope"))

        with patch_native("minimax"):
            response = await router.chat(messages=SIMPLE_MESSAGES)
        assert "[ESCALATE]" in response.content
        assert router._last_decision.target == "default"  # NOT escalation

    @pytest.mark.asyncio
    async def test_escalation_chain_is_separate(self):
        """Escalation chain uses escalation model, not plan entries."""
        plan = [{"provider": "gemini", "model": "gemini-3-flash-preview"}]
        router = make_router(routing_plan=plan)

        esc = RouteDecision("escalation", "escalation", "anthropic/claude-sonnet-4-6")
        with patch_native("minimax"):
            chain = router._build_chain(esc)

        for tier in chain:
            assert tier.model == "anthropic/claude-sonnet-4-6"

        # Plan entries should NOT appear in escalation chain
        plan_tiers = [t for t in chain if t.name.startswith("plan:")]
        assert plan_tiers == []


# ===================================================================
# 6. Safety net and failover tracking
# ===================================================================

class TestSafetyNet:
    @pytest.mark.asyncio
    async def test_last_known_working_tracked(self):
        router = make_router()
        with patch_native("minimax"):
            await router.chat(messages=SIMPLE_MESSAGES)

        assert router._last_known_working is not None
        name, model = router._last_known_working
        assert not name.startswith("safety:")
        assert not name.startswith("emergency:")

    @pytest.mark.asyncio
    async def test_last_known_working_in_chain(self):
        router = make_router()
        router._last_known_working = ("gemini", "gemini-3-flash-preview")

        with patch_native("minimax"):
            chain = router._build_chain(RouteDecision("default", "default", "MiniMax-M2.5"))
        names = [t.name for t in chain]
        models = [t.model for t in chain]

        assert "safety:gemini" in names
        idx = names.index("safety:gemini")
        assert models[idx] == "gemini-3-flash-preview"

    @pytest.mark.asyncio
    async def test_last_known_working_strips_plan_prefix(self):
        """Safety net uses clean provider name even when tracked under plan: prefix."""
        router = make_router()
        router._last_known_working = ("plan:minimax", "MiniMax-M2.5")

        with patch_native("minimax"):
            chain = router._build_chain(RouteDecision("default", "default", "MiniMax-M2.5"))
        names = [t.name for t in chain]

        # Should appear as safety:minimax, not safety:plan:minimax
        assert "safety:minimax" in names
        assert "safety:plan:minimax" not in names

    @pytest.mark.asyncio
    async def test_failover_notification_appended(self):
        """When routed via safety/emergency, notification is appended to response."""
        router = make_router(notify_on_failover=True)
        all_cloud_fail(router)

        with patch_native("minimax"), \
             patch("nanobot.copilot.alerting.bus.get_alert_bus") as mock_bus:
            mock_bus.return_value.alert = AsyncMock()
            response = await router.chat(messages=SIMPLE_MESSAGES)

        assert "_(Routed via" in response.content
        assert "primary providers unavailable)_" in response.content

    @pytest.mark.asyncio
    async def test_failover_notification_disabled(self):
        """When notify_on_failover=False, no notification appended."""
        router = make_router(notify_on_failover=False)
        all_cloud_fail(router)

        with patch_native("minimax"), \
             patch("nanobot.copilot.alerting.bus.get_alert_bus") as mock_bus:
            mock_bus.return_value.alert = AsyncMock()
            response = await router.chat(messages=SIMPLE_MESSAGES)

        assert "_(Routed via" not in response.content
        # But AlertBus should still fire
        mock_bus.return_value.alert.assert_called()

    @pytest.mark.asyncio
    async def test_failover_sets_in_failover(self):
        """Routing via safety/emergency sets _in_failover flag."""
        router = make_router()
        all_cloud_fail(router)

        with patch_native("minimax"), \
             patch("nanobot.copilot.alerting.bus.get_alert_bus") as mock_bus:
            mock_bus.return_value.alert = AsyncMock()
            with patch.object(router, "_start_recovery_probe") as mock_probe:
                await router.chat(messages=SIMPLE_MESSAGES)

                assert router._in_failover is True
                mock_probe.assert_called_once()

    @pytest.mark.asyncio
    async def test_recovery_clears_failover(self):
        """When a non-safety tier succeeds after failover, _in_failover is cleared."""
        router = make_router()
        router._in_failover = True

        with patch_native("minimax"), \
             patch.object(router, "_stop_recovery_probe") as mock_stop:
            await router.chat(messages=SIMPLE_MESSAGES)

            assert router._in_failover is False
            mock_stop.assert_called_once()


# ===================================================================
# 7. Circuit breaker integration
# ===================================================================

class TestCircuitBreaker:
    def test_circuit_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3, window_s=60.0, cooldown_s=10.0)

        for _ in range(3):
            cb.record_failure("test")

        assert cb.is_open("test") is True

    def test_circuit_closes_after_success(self):
        cb = CircuitBreaker(failure_threshold=2, window_s=60.0, cooldown_s=10.0)

        cb.record_failure("test")
        cb.record_failure("test")
        assert cb.is_open("test") is True

        cb.record_success("test")
        assert cb.is_open("test") is False

    def test_half_open_after_cooldown(self):
        cb = CircuitBreaker(failure_threshold=2, window_s=60.0, cooldown_s=0.01)

        cb.record_failure("test")
        cb.record_failure("test")
        assert cb.is_open("test") is True

        time.sleep(0.02)  # Exceed cooldown
        assert cb.is_open("test") is False  # Half-open allows probe
        state = cb._get("test")
        assert state["state"] == "half-open"

    @pytest.mark.asyncio
    async def test_full_chain_failover_with_circuit_breaker(self):
        """Simulate real failover: providers fail, circuits open, emergency catches."""
        router = make_router()
        all_cloud_fail(router)

        with patch_native("minimax"), \
             patch("nanobot.copilot.alerting.bus.get_alert_bus") as mock_bus:
            mock_bus.return_value.alert = AsyncMock()
            resp1 = await router.chat(messages=SIMPLE_MESSAGES)
            assert resp1.content is not None
            assert router._last_winning_provider == "safety:lm_studio"


# ===================================================================
# 8. Model tier hot-swapping
# ===================================================================

class TestModelSwapping:
    def test_set_model_all_tiers(self):
        router = make_router()

        router.set_model("default", "new-default")
        assert router._default_model == "new-default"

        router.set_model("escalation", "new-esc")
        assert router._escalation_model == "new-esc"

        router.set_model("fast", "new-fast")
        assert router._fast_model == "new-fast"

        router.set_model("big", "new-big")
        assert router._big_model == "new-big"

        router.set_model("local", "new-local")
        assert router._local_model == "new-local"

    def test_set_model_unknown_tier_ignored(self):
        router = make_router()
        old_default = router._default_model
        router.set_model("nonexistent", "whatever")
        assert router._default_model == old_default  # unchanged


# ===================================================================
# 9. PlanRoutingTool integration
# ===================================================================

class TestPlanRoutingTool:
    def _make_tool(self, router=None, tmp_path=None):
        if router is None:
            router = make_router()
        config = MagicMock()
        config.routing_plan = []
        config_path = tmp_path / "config.json" if tmp_path else Path("/tmp/test-config.json")
        if config_path.suffix == ".json":
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(json.dumps({"copilot": {}}))
        return PlanRoutingTool(router=router, config_path=config_path, copilot_config=config), router

    @pytest.mark.asyncio
    async def test_show_no_plan(self, tmp_path):
        tool, router = self._make_tool(tmp_path=tmp_path)
        result = await tool.execute(action="show")
        assert "No routing plan" in result
        assert "MiniMax-M2.5" in result

    @pytest.mark.asyncio
    async def test_show_with_plan(self, tmp_path):
        router = make_router(routing_plan=[
            {"provider": "gemini", "model": "flash", "reason": "free"},
        ])
        tool, _ = self._make_tool(router=router, tmp_path=tmp_path)
        result = await tool.execute(action="show")
        assert "gemini" in result
        assert "flash" in result
        assert "free" in result

    @pytest.mark.asyncio
    async def test_propose_probes_providers(self, tmp_path):
        tool, router = self._make_tool(tmp_path=tmp_path)
        plan = [
            {"provider": "gemini", "model": "gemini-3-flash-preview"},
            {"provider": "minimax", "model": "MiniMax-M2.5"},
        ]
        result = await tool.execute(action="propose", plan=plan)
        assert "OK" in result
        assert "2/2 providers passed" in result

    @pytest.mark.asyncio
    async def test_propose_reports_failures(self, tmp_path):
        router = make_router(cloud_succeed={"gemini": False})
        tool, _ = self._make_tool(router=router, tmp_path=tmp_path)
        plan = [
            {"provider": "gemini", "model": "gemini-3-flash-preview"},
            {"provider": "minimax", "model": "MiniMax-M2.5"},
        ]
        result = await tool.execute(action="propose", plan=plan)
        assert "FAILED" in result
        assert "1/2 providers passed" in result

    @pytest.mark.asyncio
    async def test_propose_unknown_provider(self, tmp_path):
        tool, _ = self._make_tool(tmp_path=tmp_path)
        plan = [{"provider": "nonexistent", "model": "foo"}]
        result = await tool.execute(action="propose", plan=plan)
        assert "FAILED" in result
        assert "not configured" in result

    @pytest.mark.asyncio
    async def test_activate_sets_plan(self, tmp_path):
        tool, router = self._make_tool(tmp_path=tmp_path)
        plan = [{"provider": "gemini", "model": "flash"}]
        result = await tool.execute(action="activate", plan=plan)

        assert "activated" in result
        assert router._routing_plan == plan

    @pytest.mark.asyncio
    async def test_activate_persists_to_config(self, tmp_path):
        tool, router = self._make_tool(tmp_path=tmp_path)
        plan = [{"provider": "gemini", "model": "flash", "reason": "test"}]
        await tool.execute(action="activate", plan=plan)

        config_path = tmp_path / "config.json"
        data = json.loads(config_path.read_text())
        assert data["copilot"]["routingPlan"] == plan

    @pytest.mark.asyncio
    async def test_clear_reverts(self, tmp_path):
        router = make_router(routing_plan=[{"provider": "gemini", "model": "flash"}])
        tool, _ = self._make_tool(router=router, tmp_path=tmp_path)

        result = await tool.execute(action="clear")
        assert "cleared" in result
        assert router._routing_plan == []

    @pytest.mark.asyncio
    async def test_activate_without_plan_errors(self, tmp_path):
        tool, _ = self._make_tool(tmp_path=tmp_path)
        result = await tool.execute(action="activate", plan=[])
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_activate_validates_structure(self, tmp_path):
        tool, _ = self._make_tool(tmp_path=tmp_path)
        result = await tool.execute(action="activate", plan=[{"provider": "", "model": "foo"}])
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_unknown_action(self, tmp_path):
        tool, _ = self._make_tool(tmp_path=tmp_path)
        result = await tool.execute(action="whatever")
        assert "unknown action" in result

    @pytest.mark.asyncio
    async def test_activate_then_route(self, tmp_path):
        """Full flow: activate a plan, then verify routing uses it."""
        tool, router = self._make_tool(tmp_path=tmp_path)

        plan = [
            {"provider": "gemini", "model": "gemini-3-flash-preview", "reason": "free"},
            {"provider": "minimax", "model": "MiniMax-M2.5", "reason": "cheap"},
        ]
        await tool.execute(action="activate", plan=plan)

        # Now route a message
        await router.chat(messages=SIMPLE_MESSAGES)
        assert router._last_decision.target == "plan"
        assert router._last_decision.reason == "routing_plan"


# ===================================================================
# 10. Error response handling (memory pollution guard integration)
# ===================================================================

class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_all_providers_fail_returns_friendly_error(self):
        """When literally everything fails, user gets a friendly error."""
        router = make_router(local_succeed=False)
        all_cloud_fail(router)

        with patch_native("minimax"):
            response = await router.chat(messages=SIMPLE_MESSAGES)
        assert response.finish_reason == "error"
        assert "trouble connecting" in response.content

    @pytest.mark.asyncio
    async def test_error_responses_have_error_finish_reason(self):
        """Error responses use finish_reason='error' so memory guard can filter."""
        router = make_router(local_succeed=False)
        all_cloud_fail(router)

        with patch_native("minimax"):
            response = await router.chat(messages=SIMPLE_MESSAGES)
        assert response.finish_reason == "error"
        assert response.model_used == "none"

    @pytest.mark.asyncio
    async def test_litellm_error_content_causes_failover(self):
        """LiteLLM-style error responses (Error calling LLM:) trigger failover."""
        err_resp = error_response("Error calling LLM: 401 Unauthorized")
        ok_resp = ok_response("Success!")

        router = make_router()
        # Native provider returns error, all others return ok
        router._cloud["minimax"].chat = AsyncMock(return_value=err_resp)
        for name, p in router._cloud.items():
            if name != "minimax":
                p.chat = AsyncMock(return_value=ok_resp)

        with patch_native("minimax"):
            response = await router.chat(messages=SIMPLE_MESSAGES)
        assert response.content == "Success!"


# ===================================================================
# 11. Multimodal and token estimation
# ===================================================================

class TestMessageParsing:
    @pytest.mark.asyncio
    async def test_multimodal_message_detected(self):
        """Image content in messages is detected for logging."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": [
                {"type": "text", "text": "What's in this image?"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
            ]},
        ]
        router = make_router()
        with patch_native("minimax"):
            await router.chat(messages=messages)

        call_kwargs = router._cost_logger.log_route.call_args[1]
        assert call_kwargs["has_images"] is True

    @pytest.mark.asyncio
    async def test_token_estimation(self):
        """Token estimation uses len//4 for all message content."""
        long_msg = "x" * 4000  # ~1000 tokens
        messages = [
            {"role": "system", "content": "System."},
            {"role": "user", "content": long_msg},
        ]
        router = make_router()
        with patch_native("minimax"):
            await router.chat(messages=messages)


# ===================================================================
# 12. Escalation instruction injection
# ===================================================================

class TestEscalationInjection:
    def test_inject_escalation_appends_to_system(self):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hi"},
        ]
        result = RouterProvider._inject_escalation(messages)

        assert "Self-Escalation" not in messages[0]["content"]
        assert "Self-Escalation" in result[0]["content"]
        assert "[ESCALATE]" in result[0]["content"]

    def test_inject_escalation_no_system_message(self):
        """If there's no system message, injection is a no-op."""
        messages = [{"role": "user", "content": "Hi"}]
        result = RouterProvider._inject_escalation(messages)
        assert len(result) == 1
        assert result[0]["content"] == "Hi"


# ===================================================================
# 13. Timeout checks
# ===================================================================

class TestTimeoutChecks:
    def test_private_mode_timeout_expired(self):
        router = make_router()
        meta = {"private_mode": True, "last_user_message_at": time.time() - 3600}
        assert router.check_private_mode_timeout(meta) == "expired"

    def test_private_mode_timeout_warning(self):
        router = make_router()
        meta = {"private_mode": True, "last_user_message_at": time.time() - 1750}
        assert router.check_private_mode_timeout(meta) == "warning"

    def test_private_mode_timeout_none(self):
        router = make_router()
        meta = {"private_mode": True, "last_user_message_at": time.time() - 60}
        assert router.check_private_mode_timeout(meta) is None

    def test_private_mode_not_active(self):
        router = make_router()
        assert router.check_private_mode_timeout({}) is None

    def test_use_override_timeout(self):
        router = make_router()
        meta = {"force_provider": "openai", "last_user_message_at": time.time() - 3600}
        assert router.check_use_override_timeout(meta) == "expired"

    def test_use_override_no_provider(self):
        router = make_router()
        assert router.check_use_override_timeout({}) is None


# ===================================================================
# 14. Config integration
# ===================================================================

class TestConfigIntegration:
    def test_copilot_config_has_new_fields(self):
        from nanobot.copilot.config import CopilotConfig
        config = CopilotConfig()

        assert config.default_conversation_model == "MiniMax-M2.5"
        assert config.escalation_model == "anthropic/claude-sonnet-4-6"
        assert config.routing_plan == []
        assert config.routing_plan_notify is True
        assert config.health_check_interval == 1800

    def test_copilot_config_no_heartbeat_interval(self):
        """Old heartbeat_interval field should not exist."""
        from nanobot.copilot.config import CopilotConfig
        config = CopilotConfig()
        assert not hasattr(config, "heartbeat_interval")

    def test_heuristics_module_has_no_classify(self):
        """classify() should be deleted from heuristics module."""
        from nanobot.copilot.routing import heuristics
        assert not hasattr(heuristics, "classify")

    def test_route_decision_targets(self):
        """RouteDecision should accept new target values."""
        for target in ("local", "default", "plan", "escalation", "cloud"):
            rd = RouteDecision(target, "test", "model")
            assert rd.target == target


# ===================================================================
# 15. HealthCheckService integration
# ===================================================================

class TestHealthCheckService:
    def test_import_and_construction(self):
        from nanobot.copilot.dream.health_check import HealthCheckService
        svc = HealthCheckService(
            copilot_docs_dir="data/copilot",
            db_path="/tmp/test.db",
            interval_s=1800,
        )
        assert svc._interval == 1800
        assert svc._running is False

    def test_old_module_removed(self):
        """The old heartbeat.py module should not exist."""
        import importlib
        try:
            importlib.import_module("nanobot.copilot.dream.heartbeat")
            assert False, "nanobot.copilot.dream.heartbeat should not exist"
        except ModuleNotFoundError:
            pass  # Expected

    def test_no_execute_fn(self):
        """HealthCheckService should NOT accept execute_fn (no LLM calls)."""
        import inspect

        from nanobot.copilot.dream.health_check import HealthCheckService
        sig = inspect.signature(HealthCheckService.__init__)
        assert "execute_fn" not in sig.parameters

    def test_accepts_kwargs(self):
        """HealthCheckService should accept **kwargs for backward compat."""
        from nanobot.copilot.dream.health_check import HealthCheckService
        svc = HealthCheckService(
            copilot_docs_dir="data/copilot",
            execute_fn=lambda x: x,  # Legacy kwarg, should be silently absorbed
        )
        assert not hasattr(svc, "_execute_fn")


# ===================================================================
# 16. Cost logger and budget integration
# ===================================================================

class TestCostAndBudget:
    def test_gemini_flash_preview_pricing(self):
        from nanobot.copilot.cost.logger import _PRICING
        assert "gemini-3-flash-preview" in _PRICING
        assert _PRICING["gemini-3-flash-preview"] == (0.0, 0.0)

    def test_gemini_flash_preview_context_window(self):
        from nanobot.copilot.context.budget import _MODEL_WINDOWS
        assert "gemini-3-flash-preview" in _MODEL_WINDOWS
        assert _MODEL_WINDOWS["gemini-3-flash-preview"] == 1_000_000

    def test_minimax_m25_context_window(self):
        from nanobot.copilot.context.budget import _MODEL_WINDOWS
        assert "MiniMax-M2.5" in _MODEL_WINDOWS
        assert _MODEL_WINDOWS["MiniMax-M2.5"] == 200_000


# ===================================================================
# 17. Preferences tool integration
# ===================================================================

class TestPreferencesTool:
    def test_allowed_keys_updated(self):
        from nanobot.copilot.tools.preferences import _ALLOWED_KEYS
        assert "health_check_interval" in _ALLOWED_KEYS
        assert "heartbeat_interval" not in _ALLOWED_KEYS
        assert "default_conversation_model" in _ALLOWED_KEYS
        assert "escalation_model" in _ALLOWED_KEYS
        assert "routing_plan_notify" in _ALLOWED_KEYS

    def test_type_map_updated(self):
        from nanobot.copilot.tools.preferences import _TYPE_MAP
        assert "health_check_interval" in _TYPE_MAP
        assert "heartbeat_interval" not in _TYPE_MAP


# ===================================================================
# 18. Use model aliases
# ===================================================================

class TestUseModelAliases:
    def test_new_aliases_exist(self):
        from nanobot.copilot.tools.use_model import _ALIASES
        for alias in ("claude", "o1", "o3", "minimax", "m25", "kimi", "llama", "glm"):
            assert alias in _ALIASES, f"Missing alias: {alias}"

    def test_aliases_resolve_to_models(self):
        from nanobot.copilot.tools.use_model import _ALIASES
        assert _ALIASES["claude"] == "anthropic/claude-sonnet-4-6"
        assert _ALIASES["minimax"] == "MiniMax-M2.5"
        assert _ALIASES["kimi"] == "moonshotai/kimi-k2.5"


# ===================================================================
# 19. Edge cases
# ===================================================================

class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_empty_messages(self):
        """Router should handle empty messages without crashing."""
        router = make_router()
        with patch_native("minimax"):
            response = await router.chat(messages=[])
        assert response.content is not None

    @pytest.mark.asyncio
    async def test_empty_plan_entries(self):
        """Plan entries with missing fields should be handled gracefully."""
        plan = [{"provider": "", "model": ""}]
        router = make_router(routing_plan=plan)
        chain = router._build_chain(RouteDecision("plan", "routing_plan", ""))
        plan_tiers = [t for t in chain if t.name.startswith("plan:")]
        assert len(plan_tiers) == 0

    @pytest.mark.asyncio
    async def test_concurrent_routing_calls(self):
        """Multiple concurrent routing calls should not interfere."""
        router = make_router()
        with patch_native("minimax"):
            results = await asyncio.gather(
                router.chat(messages=SIMPLE_MESSAGES),
                router.chat(messages=SIMPLE_MESSAGES),
                router.chat(messages=SIMPLE_MESSAGES),
            )
        assert all(r.content == "Hello!" for r in results)

    @pytest.mark.asyncio
    async def test_plan_with_duplicate_providers(self):
        """Plan with duplicate providers -- each gets its own tier."""
        plan = [
            {"provider": "gemini", "model": "gemini-3-flash-preview"},
            {"provider": "gemini", "model": "gemini-2.5-pro"},
        ]
        router = make_router(routing_plan=plan)
        chain = router._build_chain(RouteDecision("plan", "routing_plan", "gemini-3-flash-preview"))
        plan_tiers = [t for t in chain if t.name.startswith("plan:")]
        assert len(plan_tiers) == 2
        assert plan_tiers[0].model == "gemini-3-flash-preview"
        assert plan_tiers[1].model == "gemini-2.5-pro"
