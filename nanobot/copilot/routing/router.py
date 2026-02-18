"""RouterProvider — drop-in replacement for LiteLLMProvider with intelligent routing."""

import time
from typing import Any

from loguru import logger

from nanobot.providers.base import LLMProvider, LLMResponse
from nanobot.copilot.cost.logger import CostLogger
from nanobot.copilot.routing.failover import FailoverChain, ProviderTier
from nanobot.copilot.routing.heuristics import RouteDecision, classify


# Instruction injected into the system prompt when routing to the local model.
# Tells the model it can request escalation to a more powerful model.
_ESCALATION_INSTRUCTION = (
    "\n\n---\n\n## Self-Escalation\n"
    "If this task is beyond your capabilities (complex reasoning, code generation, "
    "creative writing, multi-step analysis, or anything you are not confident about), "
    "begin your response with exactly `[ESCALATE]` followed by a brief reason. "
    "The system will automatically retry with a more powerful model.\n"
    "Only escalate when genuinely needed — most conversational and simple tasks "
    "are well within your abilities."
)


class RouterProvider(LLMProvider):
    """Routes each LLM call to the best provider/model based on heuristics.

    Implements the same ``LLMProvider`` interface so the ``AgentLoop`` never
    knows the difference.  Supports self-escalation: if the local model begins
    its response with ``[ESCALATE]``, the router retries with the big model.
    """

    def __init__(
        self,
        local_provider: LLMProvider,
        cloud_providers: dict[str, LLMProvider],
        cost_logger: CostLogger,
        *,
        local_model: str = "huihui-qwen3-30b-a3b-instruct-2507-abliterated-i1@q4_k_m",
        fast_model: str = "anthropic/claude-haiku-4-5",
        big_model: str = "anthropic/claude-sonnet-4-6",
        emergency_cloud_model: str = "openai/gpt-4o-mini",
        escalation_enabled: bool = True,
        escalation_marker: str = "[ESCALATE]",
    ):
        # RouterProvider doesn't need its own api_key/api_base
        super().__init__(api_key=None, api_base=None)

        self._local = local_provider
        self._cloud = cloud_providers  # keyed by name e.g. "openrouter", "venice"
        self._cost_logger = cost_logger
        self._failover = FailoverChain()

        self._local_model = local_model
        self._fast_model = fast_model
        self._big_model = big_model
        self._emergency_cloud_model = emergency_cloud_model
        self._escalation_enabled = escalation_enabled
        self._escalation_marker = escalation_marker
        self._private_mode_timeout = 1800  # 30 min default
        self._use_override_timeout = 1800  # 30 min default
        self._last_decision: RouteDecision | None = None

    def get_default_model(self) -> str:
        return self._local_model

    @property
    def last_decision(self) -> RouteDecision | None:
        """The routing decision from the most recent chat() call."""
        return self._last_decision

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        session_metadata: dict[str, Any] | None = None,
        force_route: str | None = None,
    ) -> LLMResponse:
        # --- Forced re-route (e.g. after web search consent denial) ---
        if force_route:
            model_map = {
                "local": self._local_model,
                "fast": self._fast_model,
                "big": self._big_model,
            }
            forced_model = model_map.get(force_route, self._fast_model)
            decision = RouteDecision(force_route, "consent_reroute", forced_model)
            self._last_decision = decision
            logger.info(f"Route: {force_route} (consent_reroute) → {forced_model}")

            chain = self._build_chain(decision)
            try:
                response, tier, latency_ms = await self._failover.try_providers(
                    chain=chain,
                    messages=messages,
                    tools=tools,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            except RuntimeError as e:
                logger.error(f"Forced re-route failed: {e}")
                return LLMResponse(
                    content="I'm having trouble connecting right now. Please try again.",
                    finish_reason="error",
                    model_used="none",
                )

            tokens_in = response.usage.get("prompt_tokens", 0)
            tokens_out = response.usage.get("completion_tokens", 0)
            cost = self._cost_logger.calculate_cost(tier.model, tokens_in, tokens_out)
            await self._cost_logger.log_route(
                input_length=0,
                has_images=False,
                routed_to=decision.target,
                provider=tier.name,
                model_used=tier.model,
                route_reason=decision.reason,
                success=True,
                latency_ms=latency_ms,
                cost_usd=cost,
            )
            if tokens_in or tokens_out:
                await self._cost_logger.log_call(
                    model=tier.model,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=cost,
                )
            return response

        # Extract last user message for classification
        message_text = ""
        has_images = False
        token_estimate = 0

        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    message_text = content
                elif isinstance(content, list):
                    # Multimodal content — check for images
                    parts = []
                    for part in content:
                        if isinstance(part, dict):
                            if part.get("type") == "text":
                                parts.append(part.get("text", ""))
                            elif part.get("type") == "image_url":
                                has_images = True
                    message_text = " ".join(parts)
                break

        # Rough token estimate for entire conversation
        for msg in messages:
            c = msg.get("content", "")
            if isinstance(c, str):
                token_estimate += len(c) // 4
            elif isinstance(c, list):
                for part in c:
                    if isinstance(part, dict) and part.get("type") == "text":
                        token_estimate += len(part.get("text", "")) // 4

        # Check session overrides
        meta = session_metadata or {}
        is_private = meta.get("private_mode", False)
        force_provider = meta.get("force_provider")

        if force_provider and force_provider in self._cloud:
            force_model = meta.get("force_model")
            if force_model:
                model_used = force_model
            else:
                force_tier = meta.get("force_tier", "big")
                model_used = self._fast_model if force_tier == "fast" else self._big_model
            decision = RouteDecision("cloud", f"manual:{force_provider}", model_used)
            logger.info(f"Route: {force_provider} (manual) → {model_used}")
        elif is_private:
            decision = RouteDecision("local", "private_mode", self._local_model)
            logger.info(f"Route: local (private_mode) → {self._local_model}")
        else:
            # Normal classify
            decision = classify(
                message_text=message_text,
                has_images=has_images,
                token_count=token_estimate,
                local_model=self._local_model,
                fast_model=self._fast_model,
                big_model=self._big_model,
            )

        self._last_decision = decision

        # Build failover chain based on decision
        chain = self._build_chain(decision)

        logger.info(
            f"Route: {decision.target} ({decision.reason}) → "
            f"{decision.model} | tokens≈{token_estimate} images={has_images}"
        )

        # If routing to local and escalation is enabled (and NOT in private mode),
        # inject the escalation instruction into a copy of the messages.
        call_messages = messages
        escalation_active = self._escalation_enabled and not is_private
        if decision.target == "local" and escalation_active:
            call_messages = self._inject_escalation(messages)

        # Execute with failover
        try:
            response, tier, latency_ms = await self._failover.try_providers(
                chain=chain,
                messages=call_messages,
                tools=tools,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except RuntimeError as e:
            # All providers failed — return friendly error
            logger.error(f"All providers failed: {e}")
            await self._cost_logger.log_route(
                input_length=len(message_text),
                has_images=has_images,
                routed_to=decision.target,
                provider="none",
                model_used=decision.model,
                route_reason=decision.reason,
                success=False,
                failure_reason=str(e),
            )
            return LLMResponse(
                content="I'm having trouble connecting to my language models right now. "
                "Please try again in a moment.",
                finish_reason="error",
                model_used="none",
            )

        # --- Self-escalation check ---
        # If the local model responded with the escalation marker, retry
        # with the big model using the *original* messages (no escalation
        # instruction — the big model doesn't need it).
        # Disabled during private mode.
        if (
            escalation_active
            and decision.target == "local"
            and response.content
            and response.content.strip().startswith(self._escalation_marker)
        ):
            reason_text = response.content.strip()[len(self._escalation_marker):].strip()
            logger.info(
                f"Self-escalation triggered: {reason_text[:120]} → retrying with big model"
            )

            big_chain = self._build_chain(
                RouteDecision("big", "escalation", self._big_model)
            )
            try:
                response, tier, latency_ms = await self._failover.try_providers(
                    chain=big_chain,
                    messages=messages,  # original messages, no escalation prompt
                    tools=tools,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                decision = RouteDecision("big", "escalation", self._big_model)
            except RuntimeError as e:
                logger.error(f"Escalation retry failed: {e}")
                # Fall through — return the original local response minus marker
                response.content = reason_text or response.content

        # Log routing decision
        tokens_in = response.usage.get("prompt_tokens", 0)
        tokens_out = response.usage.get("completion_tokens", 0)
        cost = self._cost_logger.calculate_cost(tier.model, tokens_in, tokens_out)

        await self._cost_logger.log_route(
            input_length=len(message_text),
            has_images=has_images,
            routed_to=decision.target,
            provider=tier.name,
            model_used=tier.model,
            route_reason=decision.reason,
            success=True,
            latency_ms=latency_ms,
            cost_usd=cost,
        )

        # Log cost
        if tokens_in or tokens_out:
            await self._cost_logger.log_call(
                model=tier.model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=cost,
            )

        return response

    def _build_chain(self, decision: RouteDecision) -> list[ProviderTier]:
        """Build the ordered failover chain for a routing decision.

        Chain: local → fast → big.
        If decision is big, start there: big → (no further fallback to weaker).
        If decision is fast, start there: fast → big.
        If decision is local, start there: local → fast → big.
        """
        chain: list[ProviderTier] = []

        # Manual provider override — put chosen provider first, others as fallback
        if decision.reason.startswith("manual:"):
            forced = decision.reason.split(":", 1)[1]
            if forced in self._cloud:
                chain.append(ProviderTier(forced, self._cloud[forced], decision.model))
            for name, provider in self._cloud.items():
                if name != forced:
                    chain.append(ProviderTier(name, provider, decision.model))
            return chain

        if decision.target == "local":
            chain.append(
                ProviderTier("lm_studio", self._local, self._local_model, is_local=True)
            )

        if decision.target in ("local", "fast"):
            for name, provider in self._cloud.items():
                chain.append(ProviderTier(name, provider, self._fast_model))

        # Big tier — always available as final fallback
        for name, provider in self._cloud.items():
            chain.append(ProviderTier(name, provider, self._big_model))

        # ── Emergency fallbacks ────────────────────────────────────────────
        # Only added when emergency model differs from configured ones.
        # Use "emergency:<name>" keys so they get independent circuit breaker
        # state — normal route failures don't block emergency routes.
        configured = {self._fast_model, self._big_model, self._local_model}
        if self._emergency_cloud_model and self._emergency_cloud_model not in configured:
            for name, provider in self._cloud.items():
                chain.append(ProviderTier(
                    f"emergency:{name}", provider, self._emergency_cloud_model
                ))
            logger.debug(f"Emergency cloud fallback added: {self._emergency_cloud_model}")

        # LM Studio — absolute last resort, regardless of primary decision
        if decision.target != "local":
            chain.append(ProviderTier(
                "emergency:lm_studio", self._local, self._local_model, is_local=True
            ))
            logger.debug("Emergency local fallback added: LM Studio")

        return chain

    def check_private_mode_timeout(
        self, session_metadata: dict[str, Any], timeout_seconds: int = 1800
    ) -> str | None:
        """Check if private mode should warn or expire.

        Returns:
            "warning" if within 2 min of timeout, "expired" if past timeout, None otherwise.
        """
        if not session_metadata.get("private_mode"):
            return None

        last_activity = session_metadata.get("last_user_message_at", 0)
        if not last_activity:
            return None

        elapsed = time.time() - last_activity
        if elapsed > timeout_seconds:
            return "expired"
        if elapsed > timeout_seconds - 120:  # Within 2 minutes of timeout
            return "warning"
        return None

    def check_use_override_timeout(
        self, session_metadata: dict[str, Any], timeout_seconds: int | None = None
    ) -> str | None:
        """Check if /use override should warn or expire.

        Returns "warning", "expired", or None.
        """
        if not session_metadata.get("force_provider"):
            return None
        last_activity = session_metadata.get("last_user_message_at", 0)
        if not last_activity:
            return None
        timeout = timeout_seconds or self._use_override_timeout
        elapsed = time.time() - last_activity
        if elapsed > timeout:
            return "expired"
        if elapsed > timeout - 120:
            return "warning"
        return None

    async def check_routing_preference(
        self, message_text: str, session_key: str, db_path: str
    ) -> dict | None:
        """Check if message matches a stored routing preference (conversation continuity).

        Returns {"provider": ..., "tier": ..., "model": ...} or None.
        """
        if not db_path or not message_text:
            return None
        try:
            import aiosqlite
            words = set(message_text.lower().split())
            async with aiosqlite.connect(db_path) as db:
                cur = await db.execute(
                    """SELECT id, provider, tier, model, keywords, confidence
                       FROM routing_preferences
                       WHERE session_key = ? AND confidence >= 0.3
                       ORDER BY last_matched DESC LIMIT 20""",
                    (session_key,),
                )
                rows = await cur.fetchall()

                best = None
                best_score = 0.0
                for row_id, provider, tier, model, kw_json, conf in rows:
                    kw = set(kw_json.split(",")) if kw_json else set()
                    overlap = len(words & kw)
                    if overlap >= 2:
                        score = overlap * conf
                        if score > best_score:
                            best_score = score
                            best = {"provider": provider, "tier": tier, "model": model, "id": row_id}

                if best:
                    await db.execute(
                        "UPDATE routing_preferences SET last_matched = CURRENT_TIMESTAMP WHERE id = ?",
                        (best["id"],),
                    )
                    await db.commit()
                logger.info(f"Routing preference matched: {best['provider']} (score={best_score:.1f})")
            return best
        except Exception as e:
            logger.warning(f"Routing preference check failed: {e}")
            return None

    def set_model(self, tier: str, model: str) -> None:
        """Hot-swap a model tier at runtime."""
        if tier == "fast":
            self._fast_model = model
        elif tier == "big":
            self._big_model = model
        elif tier == "local":
            self._local_model = model
        logger.info(f"Model updated: {tier} → {model}")

    @staticmethod
    def _inject_escalation(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return a shallow copy of *messages* with escalation instruction appended
        to the system message.  Never mutates the original list."""
        messages = [msg.copy() for msg in messages]
        for msg in messages:
            if msg.get("role") == "system":
                msg["content"] = msg["content"] + _ESCALATION_INSTRUCTION
                break
        return messages
