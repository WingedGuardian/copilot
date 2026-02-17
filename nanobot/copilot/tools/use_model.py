"""Agent tool for temporary model routing overrides (equivalent to /use)."""

from __future__ import annotations

from typing import Any

from nanobot.agent.tools.base import Tool

# Short model names → full litellm identifiers (mirrors loop.py MODEL_ALIASES)
_ALIASES: dict[str, str] = {
    "haiku": "anthropic/claude-haiku-4.5",
    "sonnet": "anthropic/claude-sonnet-4-20250514",
    "opus": "anthropic/claude-opus-4-20250514",
    "gpt4": "openai/gpt-4o",
    "gpt4o": "openai/gpt-4o",
    "gpt4mini": "openai/gpt-4o-mini",
    "gemini": "google/gemini-2.0-flash",
    "flash": "google/gemini-2.0-flash",
    "deepseek": "deepseek/deepseek-chat",
    "r1": "deepseek/deepseek-reasoner",
}


class UseModelTool(Tool):
    """Temporarily route this session to a specific model.

    Works like the /use slash command but callable by the LLM.
    Override auto-expires after the configured idle timeout.
    """

    def __init__(self, session_manager, timeout_minutes: int = 30):
        self._sessions = session_manager
        self._timeout_min = timeout_minutes
        self._current_session_key: str = ""  # Set by loop before processing

    @property
    def name(self) -> str:
        return "use_model"

    @property
    def description(self) -> str:
        return (
            "Temporarily switch this session to a specific model. "
            "Pass 'auto' to revert to automatic routing. "
            f"Override expires after {self._timeout_min}min of inactivity. "
            f"Short names: {', '.join(sorted(_ALIASES.keys()))}. "
            "Or use full model ID like 'anthropic/claude-sonnet-4-20250514'."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "model": {
                    "type": "string",
                    "description": (
                        "Model to route to. Use a short name (sonnet, haiku, opus, gemini, etc.), "
                        "a full model ID (provider/model-name), or 'auto' to revert."
                    ),
                },
                "provider": {
                    "type": "string",
                    "description": "Provider to route through (openrouter, anthropic, openai, google, etc.). "
                                   "Defaults to 'openrouter' if not specified.",
                },
            },
            "required": ["model"],
        }

    async def execute(self, **kwargs: Any) -> str:
        raw_model = kwargs.get("model", "").strip()
        if not raw_model:
            return "Error: 'model' is required."

        # Get current session from loop-injected context
        session_key = self._current_session_key
        session = self._sessions.get_or_create(session_key) if session_key else None
        if not session:
            return "Error: no active session."

        # Handle 'auto' — revert to automatic routing
        if raw_model.lower() == "auto":
            session.deactivate_use_override()
            self._sessions.save(session)
            return "Switched to auto-routing."

        # Resolve model name
        resolved = _ALIASES.get(raw_model.lower())
        if resolved:
            model = resolved
            # Infer provider from full ID
            provider = kwargs.get("provider", "").strip() or resolved.split("/")[0]
        elif "/" in raw_model:
            model = raw_model
            provider = kwargs.get("provider", "").strip() or raw_model.split("/")[0]
        else:
            valid = ", ".join(sorted(_ALIASES.keys()))
            return f"Unknown model '{raw_model}'. Short names: {valid}. Or use full ID like 'anthropic/claude-sonnet-4-20250514'."

        # For non-direct providers, route through openrouter
        direct_providers = {"anthropic", "openai", "google", "deepseek", "groq"}
        if provider not in direct_providers:
            provider = "openrouter"

        session.activate_use_override(provider, "big", model)
        self._sessions.save(session)
        return f"Routing to {model} via {provider}. Expires after {self._timeout_min}min idle. Use 'auto' to revert."
