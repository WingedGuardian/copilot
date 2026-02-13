"""Agent loop: the core processing engine."""

import asyncio
import json
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMProvider
from nanobot.agent.context import ContextBuilder
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.agent.tools.filesystem import ReadFileTool, WriteFileTool, EditFileTool, ListDirTool
from nanobot.agent.tools.shell import ExecTool
from nanobot.agent.safety.sanitizer import OutputSanitizer
from nanobot.agent.tools.secrets import SecretsProvider
from nanobot.agent.tools.web import WebSearchTool, WebFetchTool
from nanobot.agent.tools.message import MessageTool
from nanobot.agent.tools.spawn import SpawnTool
from nanobot.agent.tools.cron import CronTool
from nanobot.agent.subagent import SubagentManager
from nanobot.session.manager import SessionManager


class AgentLoop:
    """
    The agent loop is the core processing engine.
    
    It:
    1. Receives messages from the bus
    2. Builds context with history, memory, skills
    3. Calls the LLM
    4. Executes tool calls
    5. Sends responses back
    """
    
    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_iterations: int = 20,
        brave_api_key: str | None = None,
        exec_config: "ExecToolConfig | None" = None,
        cron_service: "CronService | None" = None,
        restrict_to_workspace: bool = False,
        session_manager: SessionManager | None = None,
        # --- Copilot extensions (None = disabled) ---
        extended_context: "ExtendedContextBuilder | None" = None,
        extractor: "BackgroundExtractor | None" = None,
        thread_tracker: "ThreadTracker | None" = None,
        approval_interceptor: "ApprovalInterceptor | None" = None,
        lesson_manager: "LessonManager | None" = None,
        satisfaction_detector: "SatisfactionDetector | None" = None,
        memory_manager: "MemoryManager | None" = None,
        copilot_config: "CopilotConfig | None" = None,
    ):
        from nanobot.config.schema import ExecToolConfig
        from nanobot.cron.service import CronService
        self.bus = bus
        self.provider = provider
        self.workspace = workspace
        self.model = model or provider.get_default_model()
        self.max_iterations = max_iterations
        self.brave_api_key = brave_api_key
        self.exec_config = exec_config or ExecToolConfig()
        self.cron_service = cron_service
        self.restrict_to_workspace = restrict_to_workspace
        self.secrets = SecretsProvider()
        self.sanitizer = OutputSanitizer(secrets=self.secrets)

        self.context = extended_context or ContextBuilder(workspace)
        self.sessions = session_manager or SessionManager(workspace)
        self.tools = ToolRegistry(sanitizer=self.sanitizer)
        self.subagents = SubagentManager(
            provider=provider,
            workspace=workspace,
            bus=bus,
            model=self.model,
            brave_api_key=brave_api_key,
            exec_config=self.exec_config,
            restrict_to_workspace=restrict_to_workspace,
        )
        
        # Copilot extensions
        self._extractor = extractor
        self._thread_tracker = thread_tracker
        self._approval_interceptor = approval_interceptor
        self._lesson_manager = lesson_manager
        self._satisfaction_detector = satisfaction_detector
        self._memory_manager = memory_manager
        self._copilot_config = copilot_config

        self._running = False
        self._register_default_tools()
    
    def _register_default_tools(self) -> None:
        """Register the default set of tools."""
        # File tools (restrict to workspace if configured)
        allowed_dir = self.workspace if self.restrict_to_workspace else None
        self.tools.register(ReadFileTool(allowed_dir=allowed_dir))
        self.tools.register(WriteFileTool(allowed_dir=allowed_dir))
        self.tools.register(EditFileTool(allowed_dir=allowed_dir))
        self.tools.register(ListDirTool(allowed_dir=allowed_dir))
        
        # Shell tool
        self.tools.register(ExecTool(
            working_dir=str(self.workspace),
            timeout=self.exec_config.timeout,
            restrict_to_workspace=self.restrict_to_workspace,
        ))
        
        # Web tools
        self.tools.register(WebSearchTool(api_key=self.brave_api_key, secrets=self.secrets))
        self.tools.register(WebFetchTool())
        
        # Message tool
        message_tool = MessageTool(send_callback=self.bus.publish_outbound)
        self.tools.register(message_tool)
        
        # Spawn tool (for subagents)
        spawn_tool = SpawnTool(manager=self.subagents)
        self.tools.register(spawn_tool)
        
        # Cron tool (for scheduling)
        if self.cron_service:
            self.tools.register(CronTool(self.cron_service))
    
    async def run(self) -> None:
        """Run the agent loop, processing messages from the bus."""
        self._running = True
        logger.info("Agent loop started")
        
        while self._running:
            try:
                # Wait for next message
                msg = await asyncio.wait_for(
                    self.bus.consume_inbound(),
                    timeout=1.0
                )
                
                # Process it
                try:
                    response = await self._process_message(msg)
                    if response:
                        await self.bus.publish_outbound(response)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    # Send error response
                    await self.bus.publish_outbound(OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content=f"Sorry, I encountered an error: {str(e)}"
                    ))
            except asyncio.TimeoutError:
                continue
    
    def stop(self) -> None:
        """Stop the agent loop."""
        self._running = False
        logger.info("Agent loop stopping")
    
    async def _process_message(self, msg: InboundMessage) -> OutboundMessage | None:
        """
        Process a single inbound message.
        
        Args:
            msg: The inbound message to process.
        
        Returns:
            The response message, or None if no response needed.
        """
        # Handle system messages (subagent announces)
        # The chat_id contains the original "channel:chat_id" to route back to
        if msg.channel == "system":
            return await self._process_system_message(msg)
        
        # Copilot: check if this is an approval response
        if self._approval_interceptor and self._approval_interceptor.has_pending(msg.session_key):
            return await self._approval_interceptor.handle_response(msg)

        preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
        logger.info(f"Processing message from {msg.channel}:{msg.sender_id}: {preview}")

        # Copilot: quick satisfaction check on user message
        if self._satisfaction_detector:
            signal = self._satisfaction_detector.detect_regex(msg.content)
            if signal:
                asyncio.create_task(
                    self._satisfaction_detector.handle_signal(signal, msg.session_key)
                )

        # Get or create session
        session = self.sessions.get_or_create(msg.session_key)
        
        # Update tool contexts
        message_tool = self.tools.get("message")
        if isinstance(message_tool, MessageTool):
            message_tool.set_context(msg.channel, msg.chat_id)
        
        spawn_tool = self.tools.get("spawn")
        if isinstance(spawn_tool, SpawnTool):
            spawn_tool.set_context(msg.channel, msg.chat_id)
        
        cron_tool = self.tools.get("cron")
        if isinstance(cron_tool, CronTool):
            cron_tool.set_context(msg.channel, msg.chat_id)
        
        # Copilot: thread tagging — detect explicit "> TopicName" prefix
        if self._thread_tracker:
            forced_id, forced_label = self._thread_tracker.check_message(msg.content)
            if forced_id:
                msg.content = self._thread_tracker.strip_topic_prefix(msg.content)
                if not msg.content:
                    msg.content = f"(Topic set to: {forced_label})"

        # Copilot: fetch relevant lessons for injection
        lessons_for_context = None
        if self._lesson_manager:
            try:
                lessons_for_context = await self._lesson_manager.get_relevant_lessons(msg.content)
                if lessons_for_context and self._satisfaction_detector:
                    self._satisfaction_detector.note_applied_lessons(
                        [l.id for l in lessons_for_context]
                    )
                    for l in lessons_for_context:
                        await self._lesson_manager.mark_applied(l.id)
            except Exception as e:
                logger.warning(f"Lesson fetch failed: {e}")

        # Build initial messages (use get_history for LLM-formatted messages)
        build_kwargs: dict = dict(
            history=session.get_history(),
            current_message=msg.content,
            media=msg.media if msg.media else None,
            channel=msg.channel,
            chat_id=msg.chat_id,
        )
        # Copilot: pass session metadata so extended builder can inject extractions
        if hasattr(self.context, '_base'):
            build_kwargs["session_metadata"] = session.metadata
        if lessons_for_context and hasattr(self.context, '_base'):
            build_kwargs["lessons"] = lessons_for_context
        messages = self.context.build_messages(**build_kwargs)
        
        # Agent loop
        iteration = 0
        final_content = None
        force_route = None  # Set when web search consent is denied → re-route
        is_router = hasattr(self.provider, 'last_decision')

        while iteration < self.max_iterations:
            iteration += 1

            # Copilot: check if context needs rebuilding before next LLM call
            if (
                iteration > 1
                and hasattr(self.context, 'needs_continuation')
                and self.context.needs_continuation(messages, self.model)
            ):
                messages = self.context.rebuild_from_extractions(
                    session, msg.content, channel=msg.channel, chat_id=msg.chat_id
                )

            # Call LLM — pass router-specific params when available
            chat_kwargs: dict[str, Any] = dict(
                messages=messages,
                tools=self.tools.get_definitions(),
                model=self.model,
            )
            if is_router:
                chat_kwargs["session_metadata"] = session.metadata
                if force_route:
                    chat_kwargs["force_route"] = force_route
                    force_route = None
            response = await self.provider.chat(**chat_kwargs)

            # Copilot: set route context on approval interceptor
            if self._approval_interceptor and is_router:
                last_decision = self.provider.last_decision
                if last_decision:
                    self._approval_interceptor.set_route_context(
                        target=last_decision.target,
                        reason=last_decision.reason,
                    )

            # Handle tool calls
            if response.has_tool_calls:
                # Snapshot messages before adding tool calls (for possible re-route)
                messages_snapshot = list(messages)

                # Add assistant message with tool calls
                tool_call_dicts = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments)  # Must be JSON string
                        }
                    }
                    for tc in response.tool_calls
                ]
                messages = self.context.add_assistant_message(
                    messages, response.content, tool_call_dicts,
                    reasoning_content=response.reasoning_content,
                )

                # Execute tools
                reroute_target = None
                for tool_call in response.tool_calls:
                    args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
                    logger.info(f"Tool call: {tool_call.name}({args_str[:200]})")

                    # Copilot: approval check before execution
                    if self._approval_interceptor:
                        decision = await self._approval_interceptor.check(tool_call, msg)
                        if decision.denied:
                            if decision.reroute_model:
                                # Consent denied with re-route — discard tool calls
                                reroute_target = decision.reroute_model
                                logger.info(
                                    f"Consent denied for {tool_call.name}, "
                                    f"re-routing to {reroute_target}"
                                )
                                break
                            result = f"Action denied by user: {decision.reason}"
                            messages = self.context.add_tool_result(
                                messages, tool_call.id, tool_call.name, result
                            )
                            continue
                        if decision.modified and decision.modified_args:
                            tool_call.arguments = decision.modified_args

                    result = await self.tools.execute(tool_call.name, tool_call.arguments)

                    # Copilot: audit logging
                    if self._copilot_config:
                        asyncio.ensure_future(self._audit_log(
                            msg.session_key, tool_call.name, args_str[:500],
                            str(result)[:500],
                        ))

                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result
                    )

                # Re-route: restore messages and re-run with forced route
                if reroute_target:
                    messages = messages_snapshot
                    force_route = reroute_target
                    continue
            else:
                # No tool calls, we're done
                final_content = response.content
                break

        if final_content is None:
            final_content = "I've completed processing but have no response to give."
        
        # Log response preview
        preview = final_content[:120] + "..." if len(final_content) > 120 else final_content
        logger.info(f"Response to {msg.channel}:{msg.sender_id}: {preview}")
        
        # Save to session
        session.add_message("user", msg.content)
        session.add_message("assistant", final_content)
        self.sessions.save(session)

        # Copilot: background extraction (async, never blocks response)
        if self._extractor:
            self._extractor.schedule_extraction(
                msg.content, final_content, session.key
            )

        # Copilot: store exchange in memory (async, never blocks response)
        if self._memory_manager:
            asyncio.create_task(
                self._memory_manager.remember_exchange(msg.content, final_content, session.key)
            )

        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=final_content,
            metadata=msg.metadata or {},  # Pass through for channel-specific needs (e.g. Slack thread_ts)
        )
    
    async def _process_system_message(self, msg: InboundMessage) -> OutboundMessage | None:
        """
        Process a system message (e.g., subagent announce).
        
        The chat_id field contains "original_channel:original_chat_id" to route
        the response back to the correct destination.
        """
        logger.info(f"Processing system message from {msg.sender_id}")
        
        # Parse origin from chat_id (format: "channel:chat_id")
        if ":" in msg.chat_id:
            parts = msg.chat_id.split(":", 1)
            origin_channel = parts[0]
            origin_chat_id = parts[1]
        else:
            # Fallback
            origin_channel = "cli"
            origin_chat_id = msg.chat_id
        
        # Use the origin session for context
        session_key = f"{origin_channel}:{origin_chat_id}"
        session = self.sessions.get_or_create(session_key)
        
        # Update tool contexts
        message_tool = self.tools.get("message")
        if isinstance(message_tool, MessageTool):
            message_tool.set_context(origin_channel, origin_chat_id)
        
        spawn_tool = self.tools.get("spawn")
        if isinstance(spawn_tool, SpawnTool):
            spawn_tool.set_context(origin_channel, origin_chat_id)
        
        cron_tool = self.tools.get("cron")
        if isinstance(cron_tool, CronTool):
            cron_tool.set_context(origin_channel, origin_chat_id)
        
        # Build messages with the announce content
        messages = self.context.build_messages(
            history=session.get_history(),
            current_message=msg.content,
            channel=origin_channel,
            chat_id=origin_chat_id,
        )
        
        # Agent loop (limited for announce handling)
        iteration = 0
        final_content = None
        
        while iteration < self.max_iterations:
            iteration += 1
            
            response = await self.provider.chat(
                messages=messages,
                tools=self.tools.get_definitions(),
                model=self.model
            )
            
            if response.has_tool_calls:
                tool_call_dicts = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments)
                        }
                    }
                    for tc in response.tool_calls
                ]
                messages = self.context.add_assistant_message(
                    messages, response.content, tool_call_dicts,
                    reasoning_content=response.reasoning_content,
                )
                
                for tool_call in response.tool_calls:
                    args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
                    logger.info(f"Tool call: {tool_call.name}({args_str[:200]})")
                    result = await self.tools.execute(tool_call.name, tool_call.arguments)
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result
                    )
            else:
                final_content = response.content
                break
        
        if final_content is None:
            final_content = "Background task completed."
        
        # Save to session (mark as system message in history)
        session.add_message("user", f"[System: {msg.sender_id}] {msg.content}")
        session.add_message("assistant", final_content)
        self.sessions.save(session)
        
        return OutboundMessage(
            channel=origin_channel,
            chat_id=origin_chat_id,
            content=final_content
        )
    
    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
        model: str | None = None,
    ) -> str:
        """
        Process a message directly (for CLI or cron usage).

        Args:
            content: The message content.
            session_key: Session identifier.
            channel: Source channel (for context).
            chat_id: Source chat ID (for context).
            model: Optional model override for this call only.

        Returns:
            The agent's response.
        """
        msg = InboundMessage(
            channel=channel,
            sender_id="user",
            chat_id=chat_id,
            content=content
        )

        # Temporarily swap model if override is provided
        original_model = None
        if model:
            original_model = self.model
            self.model = model
        try:
            response = await self._process_message(msg)
            return response.content if response else ""
        finally:
            if original_model is not None:
                self.model = original_model

    async def _audit_log(
        self,
        session_key: str,
        tool_name: str,
        tool_args_json: str,
        result_summary: str,
        approved_by: str | None = None,
    ) -> None:
        """Insert a row into tool_audit_log (fire-and-forget)."""
        try:
            import aiosqlite
            db_path = self._copilot_config.db_path
            async with aiosqlite.connect(db_path) as db:
                await db.execute(
                    """INSERT INTO tool_audit_log
                       (session_key, tool_name, tool_args_json, result_summary, approved_by)
                       VALUES (?, ?, ?, ?, ?)""",
                    (session_key, tool_name, tool_args_json, result_summary, approved_by),
                )
                await db.commit()
        except Exception as e:
            logger.warning(f"Audit log failed: {e}")
