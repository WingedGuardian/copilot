"""Test V2 failover chain construction -- plan-based routing."""

from nanobot.copilot.routing.heuristics import RouteDecision
from tests.copilot.routing.helpers import make_router, patch_native


def test_no_plan_uses_default_on_all_providers():
    """Without a plan, default model goes on all cloud providers."""
    router = make_router()
    decision = RouteDecision("default", "default", "MiniMax-M2.5")

    with patch_native("minimax"):
        chain = router._build_chain(decision)

    names = [t.name for t in chain]
    models = [t.model for t in chain]

    # All cloud providers with default model (dynamic count)
    cloud_default = [(n, m) for n, m in zip(names, models) if m == "MiniMax-M2.5" and not n.startswith(("safety:", "emergency:"))]
    assert len(cloud_default) == len(router._cloud)

    # Native provider should be first
    assert cloud_default[0][0] == "minimax"

    # Safety net: LM Studio
    assert "safety:lm_studio" in names

    # Emergency fallbacks (dynamic count)
    emergency = [n for n in names if n.startswith("emergency:")]
    assert len(emergency) == len(router._cloud)


def test_plan_follows_plan_order():
    """With a plan, chain follows the plan entry order."""
    plan = [
        {"provider": "gemini", "model": "gemini-3-flash-preview", "reason": "free"},
        {"provider": "minimax", "model": "MiniMax-M2.5", "reason": "cheap"},
    ]
    router = make_router(routing_plan=plan)
    decision = RouteDecision("plan", "routing_plan", "gemini-3-flash-preview")
    chain = router._build_chain(decision)

    names = [t.name for t in chain]
    models = [t.model for t in chain]

    # First two should be plan entries
    assert names[0] == "plan:gemini"
    assert models[0] == "gemini-3-flash-preview"
    assert names[1] == "plan:minimax"
    assert models[1] == "MiniMax-M2.5"

    # Then safety net
    assert "safety:lm_studio" in names

    # Then emergency
    assert any(n.startswith("emergency:") for n in names)


def test_plan_skips_unknown_provider():
    """Plan entries with unknown providers are silently skipped."""
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


def test_manual_override_puts_provider_first():
    """Manual override puts the chosen provider first."""
    router = make_router()
    # Pick any provider from the router's cloud dict
    chosen = next(iter(router._cloud))
    decision = RouteDecision("cloud", f"manual:{chosen}", "gpt-4o")
    chain = router._build_chain(decision)

    assert chain[0].name == chosen
    assert chain[0].model == "gpt-4o"
    # Other providers follow as fallback
    other_names = [t.name for t in chain[1:]]
    assert len(other_names) > 0


def test_escalation_chain_uses_escalation_model():
    """Escalation builds a separate chain with escalation model."""
    router = make_router()
    decision = RouteDecision("escalation", "escalation", "anthropic/claude-sonnet-4-6")

    with patch_native("minimax"):
        chain = router._build_chain(decision)

    # All entries should use the escalation model
    for tier in chain:
        assert tier.model == "anthropic/claude-sonnet-4-6"


def test_local_chain_starts_with_lm_studio():
    """Local/private mode starts with LM Studio."""
    router = make_router()
    decision = RouteDecision("local", "private_mode", "some-local-model")
    chain = router._build_chain(decision)

    assert chain[0].name == "lm_studio"
    assert chain[0].is_local is True


def test_last_known_working_in_safety_net():
    """Last known working provider appears in safety net."""
    router = make_router()
    router._last_known_working = ("gemini", "gemini-3-flash-preview")
    decision = RouteDecision("default", "default", "MiniMax-M2.5")

    with patch_native("minimax"):
        chain = router._build_chain(decision)

    names = [t.name for t in chain]
    assert "safety:gemini" in names


def test_emergency_fallback_always_present():
    """Emergency fallback is always at the end."""
    router = make_router()
    decision = RouteDecision("default", "default", "MiniMax-M2.5")

    with patch_native("minimax"):
        chain = router._build_chain(decision)

    names = [t.name for t in chain]
    emergency = [n for n in names if n.startswith("emergency:")]
    assert len(emergency) > 0
    # Emergency should be at the end
    first_emergency_idx = names.index(emergency[0])
    non_emergency_after = [n for n in names[first_emergency_idx:] if not n.startswith("emergency:")]
    assert non_emergency_after == []


def test_set_model_updates_tiers():
    """set_model updates the correct tier."""
    router = make_router()
    router.set_model("default", "new-default")
    assert router._default_model == "new-default"

    router.set_model("escalation", "new-escalation")
    assert router._escalation_model == "new-escalation"

    router.set_model("fast", "new-fast")
    assert router._fast_model == "new-fast"


def test_set_routing_plan():
    """set_routing_plan updates the plan."""
    router = make_router()
    assert router._routing_plan == []

    plan = [{"provider": "gemini", "model": "flash"}]
    router.set_routing_plan(plan)
    assert router._routing_plan == plan
