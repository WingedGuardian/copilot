"""Shared fixtures and helpers for routing tests.

Provides provider-agnostic test utilities that don't hardcode
specific provider names, counts, or ordering.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from nanobot.copilot.routing.router import RouterProvider
from nanobot.providers.base import LLMResponse

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "MiniMax-M2.5"
ESCALATION_MODEL = "anthropic/claude-sonnet-4-6"
EMERGENCY_MODEL = "openai/gpt-4o-mini"
LOCAL_MODEL = "test-local-model"
DEFAULT_CLOUD_NAMES = ["openrouter", "openai", "gemini", "minimax"]

SIMPLE_MESSAGES = [
    {"role": "system", "content": "You are helpful."},
    {"role": "user", "content": "Hello, how are you?"},
]


# ---------------------------------------------------------------------------
# Response factories
# ---------------------------------------------------------------------------

def ok_response(content: str = "Hello!", tokens_in: int = 10, tokens_out: int = 5) -> LLMResponse:
    return LLMResponse(
        content=content,
        finish_reason="stop",
        usage={"prompt_tokens": tokens_in, "completion_tokens": tokens_out},
    )


def error_response(msg: str = "Error calling LLM: connection refused") -> LLMResponse:
    return LLMResponse(content=msg, finish_reason="error", usage={})


# ---------------------------------------------------------------------------
# Provider / Router factories
# ---------------------------------------------------------------------------

def make_provider(*, succeed: bool = True, response: LLMResponse | None = None) -> MagicMock:
    """Create a mock LLMProvider that either succeeds or raises."""
    p = MagicMock()
    p.api_base = "http://mock:1234"
    if succeed:
        p.chat = AsyncMock(return_value=response or ok_response())
    else:
        p.chat = AsyncMock(side_effect=RuntimeError("Provider down"))
    return p


def make_router(
    *,
    cloud_names: list[str] | None = None,
    routing_plan: list[dict] | None = None,
    provider_models: dict[str, str] | None = None,
    cloud_succeed: dict[str, bool] | None = None,
    cloud_responses: dict[str, LLMResponse] | None = None,
    local_succeed: bool = True,
    notify_on_failover: bool = True,
) -> RouterProvider:
    """Build a RouterProvider with controllable mock providers.

    cloud_names: list of cloud provider names (default: 4 standard names).
                 Tests should NOT assume any specific count.
    """
    cloud_names = cloud_names or DEFAULT_CLOUD_NAMES
    cloud_succeed = cloud_succeed or {}
    cloud_responses = cloud_responses or {}

    cloud = {}
    for name in cloud_names:
        succeed = cloud_succeed.get(name, True)
        resp = cloud_responses.get(name)
        cloud[name] = make_provider(succeed=succeed, response=resp)

    local = make_provider(succeed=local_succeed)
    cost_logger = MagicMock()
    cost_logger.log_route = AsyncMock()
    cost_logger.log_call = AsyncMock()
    cost_logger.calculate_cost = MagicMock(return_value=0.001)

    return RouterProvider(
        local_provider=local,
        cloud_providers=cloud,
        cost_logger=cost_logger,
        local_model=LOCAL_MODEL,
        fast_model="test-fast-model",
        big_model="test-big-model",
        default_model=DEFAULT_MODEL,
        escalation_model=ESCALATION_MODEL,
        emergency_cloud_model=EMERGENCY_MODEL,
        provider_models=provider_models or {},
        routing_plan=routing_plan,
        notify_on_failover=notify_on_failover,
    )


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def all_cloud_fail(router: RouterProvider) -> None:
    """Set ALL cloud providers to raise on chat(), regardless of count."""
    for p in router._cloud.values():
        p.chat = AsyncMock(side_effect=RuntimeError("Provider down"))


def patch_native(provider_name: str | None):
    """Context manager: mock find_by_model() to return the given provider as native.

    Usage:
        with patch_native("minimax"):
            response = await router.chat(...)

    If provider_name is None, find_by_model returns None (no native preference).
    """
    if provider_name is None:
        return patch("nanobot.providers.registry.find_by_model", return_value=None)
    mock_spec = MagicMock()
    mock_spec.name = provider_name
    return patch("nanobot.providers.registry.find_by_model", return_value=mock_spec)
