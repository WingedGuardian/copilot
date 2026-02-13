"""Approval interceptor: orchestrates the full approval flow."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from loguru import logger

from nanobot.bus.events import OutboundMessage
from nanobot.copilot.approval.parser import ApprovalResponse, NLApprovalParser

if TYPE_CHECKING:
    from nanobot.bus.queue import MessageBus
    from nanobot.copilot.approval.patterns import RulesEngine
    from nanobot.copilot.approval.queue import ApprovalQueue
    from nanobot.copilot.metacognition.lessons import LessonManager


@dataclass
class ApprovalDecision:
    """Result of an approval check."""

    approved: bool = False
    denied: bool = False
    reason: str = ""
    modified_args: dict[str, Any] | None = None
    reroute_model: str = ""  # If set, re-route the turn to this model tier

    @property
    def modified(self) -> bool:
        return self.modified_args is not None


class ApprovalInterceptor:
    """Orchestrates the full approval flow: check rules, ask user, parse response."""

    def __init__(
        self,
        bus: MessageBus,
        rules_engine: RulesEngine,
        queue: ApprovalQueue,
        parser: NLApprovalParser,
        lesson_manager: LessonManager | None = None,
        approval_channel: str = "whatsapp",
        approval_chat_id: str = "",
        timeout: float = 300.0,
    ):
        self._bus = bus
        self._rules = rules_engine
        self._queue = queue
        self._parser = parser
        self._lesson_manager = lesson_manager
        self._channel = approval_channel
        self._chat_id = approval_chat_id
        self._timeout = timeout

    def set_route_context(self, target: str = "", reason: str = "") -> None:
        """Set routing context on the rules engine for conditional approval."""
        self._rules.set_route_context(target=target, reason=reason)

    async def check(self, tool_call: Any, msg: Any) -> ApprovalDecision:
        """Check if a tool call requires approval and handle the full flow.

        Returns ApprovalDecision indicating whether to proceed, deny, or modify.
        """
        tool_name = tool_call.name
        tool_args = tool_call.arguments

        # Check rules engine
        required = await self._rules.check(tool_name, tool_args)
        if required is None:
            return ApprovalDecision(approved=True)

        # Build summary
        args_brief = json.dumps(tool_args, ensure_ascii=False)[:200]
        summary = f"{tool_name}: {args_brief}"

        # Determine chat_id for approval request
        chat_id = self._chat_id or getattr(msg, "chat_id", "")

        # Create queue entry
        session_key = getattr(msg, "session_key", f"{self._channel}:{chat_id}")
        pending = self._queue.create_request(
            session_key=session_key,
            tool_name=tool_name,
            tool_args=tool_args,
            summary=summary,
            timeout=self._timeout,
        )

        # Send approval request to user
        if required.reroute_on_deny:
            # Consent-style prompt (e.g. local web search consent)
            approval_msg = (
                f"[Consent Needed]\n"
                f"{required.reason}\n"
                f"Reply: yes / no"
            )
        else:
            approval_msg = (
                f"[Approval Needed]\n"
                f"Tool: {tool_name}\n"
                f"Args: {args_brief}\n"
                f"Reply: approve / deny / modify"
            )
        await self._bus.publish_outbound(OutboundMessage(
            channel=self._channel,
            chat_id=chat_id,
            content=approval_msg,
        ))

        # Wait for response
        try:
            await asyncio.wait_for(pending.event.wait(), timeout=self._timeout)
        except asyncio.TimeoutError:
            self._queue.cleanup_expired()
            if self._lesson_manager:
                await self._lesson_manager.create_lesson(
                    trigger_pattern=f"tool:{tool_name}",
                    lesson_text=f"Approval timed out for {tool_name}. User may be unavailable.",
                    source="timeout",
                    category="tool_use",
                    confidence=0.3,
                )
            return ApprovalDecision(denied=True, reason="Approval timed out")

        # Process response
        response = pending.response
        if response is None:
            return ApprovalDecision(denied=True, reason="No response received")

        if response.intent == "approve":
            return ApprovalDecision(approved=True, reason=response.reason)

        if response.intent == "modify":
            # Treat as approve for now (full modification support is Phase 5)
            return ApprovalDecision(
                approved=True,
                reason=response.reason,
                modified_args=response.modified_args,
            )

        # Denied
        reroute = required.reroute_on_deny if required.reroute_on_deny else ""
        if self._lesson_manager:
            await self._lesson_manager.create_lesson(
                trigger_pattern=f"tool:{tool_name}",
                lesson_text=f"User denied {tool_name}: {response.reason}",
                source="denial",
                category="tool_use",
                confidence=0.6,
            )
        return ApprovalDecision(
            denied=True, reason=response.reason, reroute_model=reroute
        )

    def has_pending(self, session_key: str) -> bool:
        """Check if there's a pending approval for this session."""
        return self._queue.has_pending(session_key)

    async def handle_response(self, msg: Any) -> OutboundMessage:
        """Handle a user message that's a response to a pending approval.

        Returns an OutboundMessage confirming the action.
        """
        session_key = msg.session_key
        pending = self._queue.get_pending(session_key)

        if pending is None:
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content="No pending approval to respond to.",
            )

        # Parse the response
        response = self._parser.parse(msg.content)

        if response.intent == "unclear":
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content="I didn't understand. Reply: approve / deny / cancel",
            )

        # Resolve the pending approval
        self._queue.resolve(session_key, response)

        # Check for dynamic rule creation
        new_rule = self._parser.detect_rule_creation(msg.content)
        if new_rule:
            await self._rules.add_rule(
                pattern=pending.tool_name,
                condition="",
                action="auto_approve",
            )
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=f"{'Approved' if response.intent == 'approve' else 'Denied'}. "
                        f"Also added auto-approve rule for {pending.tool_name}.",
            )

        status = "Approved. Proceeding..." if response.intent in ("approve", "modify") else "Denied."
        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=status,
        )
