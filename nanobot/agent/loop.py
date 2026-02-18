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
from nanobot.agent.memory import MemoryStore
from nanobot.agent.subagent import SubagentManager
from nanobot.session.manager import SessionManager


# Short model names → full litellm identifiers
MODEL_ALIASES: dict[str, str] = {
    "haiku": "anthropic/claude-haiku-4-5",
    "sonnet": "anthropic/claude-sonnet-4-6",
    "opus": "anthropic/claude-opus-4-6",
    "claude": "anthropic/claude-sonnet-4-6",
    "gpt4": "openai/gpt-4o",
    "gpt4o": "openai/gpt-4o",
    "gpt4mini": "openai/gpt-4o-mini",
    "o1": "openai/o1",
    "o3": "openai/o3-mini",
    "gemini": "google/gemini-2.5-flash",
    "flash": "google/gemini-2.5-flash",
    "deepseek": "deepseek/deepseek-chat",
    "r1": "deepseek/deepseek-r1",
}

# Error response prefixes (used for is_error tagging)
_ERROR_PREFIXES = (
    "I'm having trouble connecting",
    "I'm sorry, the response timed out",
)


# ---------------------------------------------------------------------------
# /help command helpers
# ---------------------------------------------------------------------------

_HELP_COMMANDS = (
    "/new — Start a new conversation\n"
    "/status — System health, costs, routing, memory\n"
    "/tasks — List active tasks with status\n"
    "/task <id> — Detailed task view\n"
    "/cancel <id> — Cancel a running task\n"
    "/onboard — Start the getting-to-know-you interview\n"
    "/profile — Show your current profile\n"
    "/use <provider> [fast|<model>] — Switch LLM provider\n"
    "/use auto — Return to automatic routing\n"
    "/private — Local-only mode\n"
    "/help [topic] — This help (topics: routing, policy, memory, tasks, models, alerts)"
)


def _load_help_section(topic: str, docs_dir: str | None) -> str | None:
    """Load a ## section from help.md by topic name."""
    if not docs_dir:
        return None
    help_path = Path(docs_dir) / "help.md"
    try:
        content = help_path.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError):
        return None
    import re
    pattern = rf"^## {re.escape(topic)}\s*\n(.*?)(?=^## |\Z)"
    match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else None


def _list_help_topics(docs_dir: str | None) -> list[str]:
    """List available ## topics from help.md."""
    if not docs_dir:
        return []
    help_path = Path(docs_dir) / "help.md"
    try:
        content = help_path.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError):
        return []
    import re
    return re.findall(r"^## (\w+)", content, re.MULTILINE)


def _generate_tips(copilot_config, session_meta: dict) -> list[str]:
    """Generate dynamic tips based on config and session state."""
    if not copilot_config:
        return []
    tips = []
    if session_meta.get("force_provider"):
        provider = session_meta["force_provider"]
        tips.append(f"  \u26a0\ufe0f Manual routing active ({provider}) — `/use auto` to revert")
    if session_meta.get("private_mode"):
        tips.append("  \U0001f512 Private mode active — all requests stay local")
    if hasattr(copilot_config, "dream_cron_expr"):
        tips.append(f"  \U0001f4a4 Dream cycle: {copilot_config.dream_cron_expr}")
    if hasattr(copilot_config, "heartbeat_interval"):
        hrs = copilot_config.heartbeat_interval / 3600
        tips.append(f"  \U0001f493 Heartbeat: every {hrs:.0f}h")
    return tips[:5]


def _build_help_response(
    topic: str | None,
    copilot_config,
    session_meta: dict,
    help_md_dir: str | None,
) -> str:
    """Build /help response. Static commands + dynamic tips + topic drill-down."""
    docs_dir = help_md_dir or (copilot_config.copilot_docs_dir if copilot_config else None)

    # --- Topic drill-down ---
    if topic:
        section = _load_help_section(topic, docs_dir)
        if section:
            return f"**{topic.title()}**\n\n{section}"
        available = _list_help_topics(docs_dir)
        topics_str = ", ".join(available) if available else "routing, policy, memory, tasks, models, alerts"
        return f"Topic '{topic}' not found. Available topics: {topics_str}"

    # --- Summary mode ---
    parts = ["\U0001f408 **nanobot help**\n", "**Commands:**\n" + _HELP_COMMANDS]

    tips = _generate_tips(copilot_config, session_meta)
    if tips:
        parts.append("\n**Tips:**\n" + "\n".join(tips))

    parts.append("\nType `/help <topic>` for details. Topics: routing, policy, memory, tasks, models, alerts")
    return "\n".join(parts)


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
        memory_window: int = 50,
        brave_api_key: str | None = None,
        exec_config: "ExecToolConfig | None" = None,
        cron_service: "CronService | None" = None,
        restrict_to_workspace: bool = False,
        session_manager: SessionManager | None = None,
        # --- Copilot extensions (None = disabled) ---
        extended_context: "ExtendedContextBuilder | None" = None,
        extractor: "BackgroundExtractor | None" = None,
        thread_tracker: "ThreadTracker | None" = None,
        lesson_manager: "LessonManager | None" = None,
        satisfaction_detector: "SatisfactionDetector | None" = None,
        memory_manager: "MemoryManager | None" = None,
        copilot_config: "CopilotConfig | None" = None,
        llm_timeout: int = 120,
        max_turn_time: int = 300,
    ):
        from nanobot.config.schema import ExecToolConfig
        from nanobot.cron.service import CronService
        self._llm_timeout = llm_timeout
        self._max_turn_time = max_turn_time
        self._tracked_tasks: set[asyncio.Task] = set()
        self.bus = bus
        self.provider = provider
        self.workspace = workspace
        self.model = model or provider.get_default_model()
        self.max_iterations = max_iterations
        self.memory_window = memory_window
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
        self._lesson_manager = lesson_manager
        self._satisfaction_detector = satisfaction_detector
        self._memory_manager = memory_manager
        self._copilot_config = copilot_config
        self._task_manager = None  # Set externally when copilot task queue is enabled

        self._running = False
        # Phase 4: Message UX
        self._processing_sessions: dict[str, float] = {}  # session_key -> start_time
        self._notified_sessions: set[str] = set()  # sessions already notified about queue
        self._ack_delay: float = 2.0
        self._coalesce_window: float = 0.5
        self._register_default_tools()

    def _track_task(self, coro, name: str = "unnamed") -> asyncio.Task:
        """Create a tracked task that logs exceptions on completion."""
        task = asyncio.create_task(coro, name=name)
        self._tracked_tasks.add(task)
        def _done(t: asyncio.Task):
            self._tracked_tasks.discard(t)
            if not t.cancelled() and t.exception():
                logger.error(f"Background task '{t.get_name()}' failed: {t.exception()}")
                try:
                    from nanobot.copilot.alerting.bus import get_alert_bus
                    asyncio.ensure_future(get_alert_bus().alert(
                        "agent", "medium", f"Background task '{t.get_name()}' failed: {t.exception()}", "task_failed"
                    ))
                except Exception:
                    pass
        task.add_done_callback(_done)
        return task
    
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
                
                # 4B: Message coalescing — wait briefly and combine messages from same session
                await asyncio.sleep(self._coalesce_window)
                extra_msgs = []
                while self.bus.inbound_size > 0:
                    try:
                        peek = await asyncio.wait_for(self.bus.consume_inbound(), timeout=0.05)
                        if peek.session_key == msg.session_key and not peek.media:
                            extra_msgs.append(peek)
                        else:
                            # Different session — put it back conceptually by re-publishing
                            await self.bus.publish_inbound(peek)
                            break
                    except asyncio.TimeoutError:
                        break
                if extra_msgs:
                    # Combine: latest message first, then earlier ones
                    combined = [m.content for m in reversed(extra_msgs)] + [msg.content]
                    msg.content = "\n---\n".join(combined)
                    logger.info(f"Coalesced {len(extra_msgs) + 1} messages for {msg.session_key}")

                # 4A: Delayed processing acknowledgment (WhatsApp uses native
                # composing presence instead of a text "..." message)
                ack_task = None

                # 4C: Queue notification — tell user if we're busy
                session_key = msg.session_key
                if session_key in self._processing_sessions and session_key not in self._notified_sessions:
                    if self.bus.inbound_size > 0:
                        self._notified_sessions.add(session_key)
                        await self.bus.publish_outbound(OutboundMessage(
                            channel=msg.channel, chat_id=msg.chat_id,
                            content="Got your message, finishing up current task first.",
                        ))

                # Process it
                try:
                    self._processing_sessions[session_key] = asyncio.get_event_loop().time()
                    response = await self._process_message(msg)
                    # Cancel ack if we responded fast enough
                    if ack_task and not ack_task.done():
                        ack_task.cancel()
                    if response:
                        await self.bus.publish_outbound(response)
                except Exception as e:
                    if ack_task and not ack_task.done():
                        ack_task.cancel()
                    logger.error(f"Error processing message: {e}")
                    from nanobot.copilot.alerting.bus import get_alert_bus
                    await get_alert_bus().alert("agent", "medium", f"Message processing error: {e}", "process_error")
                    # Send error response
                    await self.bus.publish_outbound(OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content=f"Sorry, I encountered an error: {str(e)}"
                    ))
                finally:
                    self._processing_sessions.pop(session_key, None)
                    self._notified_sessions.discard(session_key)
            except asyncio.TimeoutError:
                continue
    
    async def stop(self) -> None:
        """Stop the agent loop and cancel pending background tasks."""
        self._running = False
        if self._tracked_tasks:
            logger.info(f"Cancelling {len(self._tracked_tasks)} tracked tasks...")
            for task in self._tracked_tasks:
                task.cancel()
            await asyncio.gather(*self._tracked_tasks, return_exceptions=True)
            self._tracked_tasks.clear()
        logger.info("Agent loop stopped")
    
    async def _process_message(self, msg: InboundMessage, session_key: str | None = None) -> OutboundMessage | None:
        """
        Process a single inbound message.
        
        Args:
            msg: The inbound message to process.
            session_key: Override session key (used by process_direct).
        
        Returns:
            The response message, or None if no response needed.
        """
        # Handle system messages (subagent announces)
        # The chat_id contains the original "channel:chat_id" to route back to
        if msg.channel == "system":
            return await self._process_system_message(msg)
        
        preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
        logger.info(f"Processing message from {msg.channel}:{msg.sender_id}: {preview}")

        # Copilot: quick satisfaction check on user message
        if self._satisfaction_detector:
            signal = self._satisfaction_detector.detect_regex(msg.content)
            if signal:
                self._track_task(
                    self._satisfaction_detector.handle_signal(signal, msg.session_key),
                    name="satisfaction_signal",
                )

        # Get or create session
        key = session_key or msg.session_key
        session = self.sessions.get_or_create(key)

        # Handle slash commands
        cmd = msg.content.strip().lower()
        if cmd == "/new":
            await self._consolidate_memory(session, archive_all=True)
            session.clear()
            self.sessions.save(session)
            return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id,
                                  content="🐈 New session started. Memory consolidated.")
        if cmd == "/help" or cmd.startswith("/help "):
            topic = cmd[6:].strip() or None
            docs_dir = self._copilot_config.copilot_docs_dir if self._copilot_config else None
            content = _build_help_response(topic, self._copilot_config, session.metadata, docs_dir)
            return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, content=content)
        if cmd == "/status":
            status_tool = self.tools.get("status")
            if status_tool:
                result = await status_tool.execute(
                    session_metadata=session.metadata,
                    session=session,
                    session_manager=self.sessions,
                )
                return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, content=result)
            return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id,
                                  content="Status dashboard not available.")
        if cmd == "/onboard":
            session.metadata["onboarding_active"] = True
            session.clear()
            self.sessions.save(session)
            # Fall through to normal LLM processing — the injected prompt handles the rest
        elif cmd == "/profile":
            profile_path = self.workspace / "USER.md"
            if profile_path.exists():
                content = profile_path.read_text(encoding="utf-8")
                return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id,
                                      content=f"🐈 Your profile:\n\n{content}")
            return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id,
                                  content="🐈 No profile set yet. Send /onboard to get started.")
        elif cmd == "/tasks" and self._task_manager:
            tasks = await self._task_manager.list_tasks()
            if not tasks:
                return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, content="No tasks.")
            lines = [f"Tasks ({len(tasks)}):"]
            for t in tasks:
                progress = f"{t.steps_completed}/{t.step_count}" if t.step_count else "-"
                lines.append(f"  [{t.id}] {t.title} ({t.status}, {progress})")
            return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, content="\n".join(lines))
        elif cmd.startswith("/task ") and self._task_manager:
            task_id = cmd.split(None, 1)[1].strip()
            task = await self._task_manager.get_task(task_id)
            if not task:
                return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, content=f"Task {task_id} not found.")
            lines = [f"Task [{task.id}]: {task.title}", f"Status: {task.status} | Priority: P{task.priority}"]
            if task.description:
                lines.append(f"Description: {task.description}")
            if task.pending_questions:
                lines.append(f"Pending questions:\n{task.pending_questions}")
            if task.steps:
                lines.append(f"Steps ({task.steps_completed}/{task.step_count}):")
                for s in task.steps:
                    icon = {"completed": "done", "failed": "FAIL", "active": ">>", "pending": "  "}.get(s.status, "  ")
                    lines.append(f"  {icon} {s.step_index}. {s.description}")
            return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, content="\n".join(lines))
        elif cmd.startswith("/cancel ") and self._task_manager:
            task_id = cmd.split(None, 1)[1].strip()
            task = await self._task_manager.get_task(task_id)
            if not task:
                return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, content=f"Task {task_id} not found.")
            await self._task_manager.update_status(task_id, "failed")
            return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, content=f"Task [{task_id}] cancelled.")
        elif cmd == "/use" or cmd == "/model" or cmd.startswith("/use ") or cmd.startswith("/model "):
            parts = cmd.split(None, 2)  # /use provider [tier_or_model]
            args = parts[1:] if len(parts) > 1 else []
            if not args:
                router = self.provider
                cloud = getattr(router, '_cloud', {})
                provider_models = getattr(router, '_provider_models', {})
                lines = ["Usage: /use <provider> [model] or /use auto", ""]
                current = session.metadata.get("force_provider")
                if current:
                    lines.append(f"Current: {current}")
                lines.append("Available providers:")
                for name in cloud:
                    m = provider_models.get(name, "")
                    tag = f" → {m}" if m else ""
                    marker = " (active)" if name == current else ""
                    lines.append(f"  {name}{tag}{marker}")
                return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id,
                                      content="\n".join(lines))
            provider = args[0]
            if provider == "auto":
                session.deactivate_use_override()
                self.sessions.save(session)
                router = self.provider
                fast = getattr(router, '_fast_model', '?')
                big = getattr(router, '_big_model', '?')
                local = getattr(router, '_local_model', '?')
                primary = next(iter(getattr(router, '_cloud', {})), 'cloud')
                return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id,
                                      content=f"🐈 Switched to auto-routing.\n"
                                              f"  fast: {primary}/{fast}\n"
                                              f"  big: {primary}/{big}\n"
                                              f"  local: {local}")
            tier = "big"
            model = None
            if len(args) > 1:
                if args[1] == "fast":
                    tier = "fast"
                else:
                    raw = args[1]
                    model = MODEL_ALIASES.get(raw.lower(), raw)
                    if model == raw and "/" not in model:
                        valid = ", ".join(sorted(MODEL_ALIASES.keys()))
                        return OutboundMessage(
                            channel=msg.channel, chat_id=msg.chat_id,
                            content=f"Unknown model '{raw}'. Short names: {valid}\n"
                                    f"Or use full ID like 'anthropic/claude-haiku-4-5'.",
                        )
            # Resolve the actual model that will be used
            router = self.provider
            provider_models = getattr(router, '_provider_models', {})
            cloud = getattr(router, '_cloud', {})
            if provider not in cloud:
                known = ", ".join(sorted(cloud.keys())) or "none"
                return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id,
                                      content=f"Unknown provider '{provider}'. Available: {known}")
            if not model and provider in provider_models:
                model = provider_models[provider]
            session.activate_use_override(provider, tier, model)
            self.sessions.save(session)
            # Show what model will actually be used
            if model:
                desc = model
            elif provider in provider_models:
                desc = provider_models[provider]
            else:
                fallback = getattr(router, '_fast_model', '?') if tier == "fast" else getattr(router, '_big_model', '?')
                desc = f"{fallback} (no default_model set for {provider})"
            timeout_min = self._copilot_config.use_override_timeout // 60 if self._copilot_config else 30
            return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id,
                                  content=f"🐈 Routing to {provider} ({desc}). Auto-expires after {timeout_min}min idle. /use auto to revert.")

        # Consolidate memory before processing if session is too large
        if len(session.messages) > self.memory_window:
            await self._consolidate_memory(session)

        # Copilot: detect alert commands
        if self._copilot_config:
            from nanobot.copilot.alerting.commands import detect_alert_command
            alert_cmd = detect_alert_command(msg.content)
            if alert_cmd:
                from nanobot.copilot.alerting.bus import get_alert_bus
                ab = get_alert_bus()
                if alert_cmd == "less":
                    new_h = min(ab._dedup_seconds / 3600 * 2, 24.0)
                    ab.set_frequency(new_h)
                    return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id,
                                          content=f"Alerts set to every {new_h:.0f} hours.")
                elif alert_cmd == "more":
                    new_h = max(ab._dedup_seconds / 3600 / 2, 1.0)
                    ab.set_frequency(new_h)
                    return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id,
                                          content=f"Alerts set to every {new_h:.0f} hours.")
                elif alert_cmd == "mute":
                    import time as _time
                    mute_h = self._copilot_config.alert_mute_hours
                    ab.mute_until(_time.time() + mute_h * 3600)
                    return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id,
                                          content=f"Alerts muted for {mute_h:.0f} hours.")
                elif alert_cmd == "unmute":
                    ab.unmute()
                    return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id,
                                          content="Alerts resumed.")
                elif alert_cmd == "status":
                    cfg = ab.get_config()
                    status = f"Alert frequency: every {cfg['dedup_hours']}h"
                    if cfg["muted"]:
                        status += f" (muted)"
                    return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id,
                                          content=status)

        # Copilot: detect private mode commands and manage timeout
        private_cmd = SessionManager.detect_private_mode_command(msg.content)
        if private_cmd == "on":
            session.activate_private_mode()
            self.sessions.save(session)
            logger.info(f"Private mode activated for {key}")
        elif private_cmd == "off":
            session.deactivate_private_mode()
            self.sessions.save(session)
            logger.info(f"Private mode deactivated for {key}")
        elif private_cmd == "extend":
            session.touch_activity()
            self.sessions.save(session)
            logger.info(f"Private mode extended for {key}")

        if session.private_mode:
            # Check timeout BEFORE touching activity (otherwise elapsed is always ~0)
            if hasattr(self.provider, 'check_private_mode_timeout'):
                timeout_status = self.provider.check_private_mode_timeout(session.metadata)
                if timeout_status == "expired" and private_cmd != "extend":
                    session.deactivate_private_mode()
                    self.sessions.save(session)
                    await self.bus.publish_outbound(OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content="Private mode ended due to inactivity. Back to normal routing.",
                    ))
                elif timeout_status == "warning":
                    await self.bus.publish_outbound(OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content="Private mode ending in 2 minutes. Say 'stay private' to extend.",
                    ))
            session.touch_activity()

        # Check /use override timeout (check BEFORE touch_activity so elapsed reflects actual idle time)
        if session.metadata.get("force_provider") and hasattr(self.provider, 'check_use_override_timeout'):
            timeout_s = self._copilot_config.use_override_timeout if self._copilot_config else 3600
            use_status = self.provider.check_use_override_timeout(session.metadata, timeout_s)
            if use_status == "expired":
                old_provider = session.metadata.get("force_provider", "")
                session.deactivate_use_override()
                # Clear stale routing preferences so they don't re-activate the override
                session.metadata.pop("_routing_pref_cleared", None)
                self.sessions.save(session)
                self._track_task(
                    self._clear_routing_preferences(key),
                    name="clear_routing_prefs",
                )
                await self.bus.publish_outbound(OutboundMessage(
                    channel=msg.channel, chat_id=msg.chat_id,
                    content=f"Model override ({old_provider}) expired due to inactivity. Back to auto-routing.",
                ))
            elif use_status == "warning":
                await self.bus.publish_outbound(OutboundMessage(
                    channel=msg.channel, chat_id=msg.chat_id,
                    content="Model override expiring in 2 minutes. Send a message or /use <provider> to extend.",
                ))
            session.touch_activity()

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

        recall_tool = self.tools.get("recall_messages")
        if recall_tool:
            recall_tool._current_session_key = msg.session_key
        use_model_tool = self.tools.get("use_model")
        if use_model_tool:
            use_model_tool._current_session_key = msg.session_key

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
                _lim = self._copilot_config.lesson_injection_count if self._copilot_config else 3
                _min_conf = self._copilot_config.lesson_min_confidence if self._copilot_config else 0.30
                lessons_for_context = await self._lesson_manager.get_relevant_lessons(
                    msg.content, limit=_lim, min_confidence=_min_conf,
                )
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
        # Pass session metadata for onboarding prompt injection (base builder)
        # and for extended builder's extraction injection (copilot mode)
        build_kwargs["session_metadata"] = session.metadata
        if lessons_for_context and hasattr(self.context, '_base'):
            build_kwargs["lessons"] = lessons_for_context

        # Proactive episodic memory recall (cross-session, gracefully degrades)
        if self._memory_manager and hasattr(self.context, '_base'):
            try:
                memory_ctx = await asyncio.wait_for(
                    self._memory_manager.proactive_recall(
                        msg.content, session.key, limit=3
                    ),
                    timeout=2.0,
                )
                if memory_ctx:
                    build_kwargs["memory_context"] = memory_ctx
            except (asyncio.TimeoutError, Exception) as e:
                logger.debug(f"Proactive recall skipped: {e}")

        # Heartbeat event injection (news feed from background monitoring)
        if self._copilot_config and hasattr(self.context, '_base'):
            try:
                from nanobot.copilot.context.events import (
                    get_unacknowledged_events,
                    get_heartbeat_summary,
                )
                # Detailed events (fire-and-forget, marked as acknowledged)
                events_ctx = await get_unacknowledged_events(
                    self._copilot_config.db_path
                )
                # Always-on heartbeat status (~20 tokens)
                hb_summary = await get_heartbeat_summary(
                    self._copilot_config.db_path
                )
                parts = [p for p in (hb_summary, events_ctx) if p]
                if parts:
                    build_kwargs["recent_events"] = "\n".join(parts)
            except Exception as e:
                logger.debug(f"Event injection skipped: {e}")

        messages = self.context.build_messages(**build_kwargs)
        
        # Check routing preferences for conversation continuity
        if (
            self._copilot_config
            and not session.metadata.get("force_provider")
            and not session.private_mode
            and hasattr(self.provider, 'check_routing_preference')
        ):
            pref = await self.provider.check_routing_preference(
                msg.content, key, self._copilot_config.db_path,
            )
            if pref:
                session.activate_use_override(pref["provider"], pref["tier"], pref.get("model"))
                self.sessions.save(session)
                logger.info(f"Restored routing preference: {pref['provider']}")

        # Agent loop
        iteration = 0
        _turn_start = __import__('time').monotonic()
        final_content = None
        tools_used: list[str] = []
        is_router = hasattr(self.provider, 'last_decision')

        while iteration < self.max_iterations:
            iteration += 1
            # Wall-clock safety: prevent runaway turns
            if __import__('time').monotonic() - _turn_start > self._max_turn_time:
                logger.warning(f"Turn exceeded {self._max_turn_time}s wall-clock limit")
                from nanobot.copilot.alerting.bus import get_alert_bus
                await get_alert_bus().alert("agent", "medium", f"Turn exceeded {self._max_turn_time}s wall-clock limit", "turn_timeout")
                final_content = "I've been working on this for a while. Here's what I have so far — let me know if you'd like me to continue."
                break

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
            try:
                response = await asyncio.wait_for(self.provider.chat(**chat_kwargs), timeout=self._llm_timeout)
            except asyncio.TimeoutError:
                logger.warning(f"LLM call timed out after {self._llm_timeout}s in agent loop")
                from nanobot.copilot.alerting.bus import get_alert_bus
                await get_alert_bus().alert("llm", "medium", f"LLM call timed out ({self._llm_timeout}s) in agent loop", "llm_timeout")
                final_content = "I'm sorry, the response timed out. Please try again."
                break

            # Handle tool calls
            if response.has_tool_calls:
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
                for tool_call in response.tool_calls:
                    tools_used.append(tool_call.name)
                    args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
                    logger.info(f"Tool call: {tool_call.name}({args_str[:200]})")

                    result = await self.tools.execute(tool_call.name, tool_call.arguments)

                    # Copilot: audit logging
                    if self._copilot_config:
                        self._track_task(self._audit_log(
                            msg.session_key, tool_call.name, args_str[:500],
                            str(result)[:500],
                        ), name="audit_log")

                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result
                    )

                # Interleaved CoT: reflect before next action
                if iteration >= self.max_iterations - 3:
                    messages.append({"role": "user", "content": "Summarize your findings and respond to the user."})
                else:
                    messages.append({"role": "user", "content": "Reflect on the results and decide next steps."})
            else:
                # No tool calls, we're done
                final_content = response.content
                break

        if final_content is None:
            if iteration >= self.max_iterations:
                final_content = f"Reached {self.max_iterations} iterations without completion."
            else:
                final_content = "I've completed processing but have no response to give."
        
        # Log response preview
        preview = final_content[:120] + "..." if len(final_content) > 120 else final_content
        logger.info(f"Response to {msg.channel}:{msg.sender_id}: {preview}")
        
        # Save to session (include tool names so consolidation sees what happened)
        session.add_message("user", msg.content)
        is_error = final_content.startswith(_ERROR_PREFIXES)

        # Track which model handled this turn (for orientation hints on switches)
        if not is_error:
            session.metadata["last_model_used"] = self.model
        session.add_message("assistant", final_content,
                            tools_used=tools_used if tools_used else None,
                            **({"is_error": True} if is_error else {}))
        self.sessions.save(session)

        # Copilot: background extraction (async, never blocks response)
        if self._extractor:
            self._extractor.schedule_extraction(
                msg.content, final_content, session.key
            )

        # Copilot: store exchange in memory (async, never blocks response)
        if self._memory_manager:
            self._track_task(
                self._memory_manager.remember_exchange(msg.content, final_content, session.key),
                name="memory_remember_exchange",
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
        _turn_start = __import__('time').monotonic()
        final_content = None

        while iteration < self.max_iterations:
            iteration += 1
            # Wall-clock safety: prevent runaway turns
            if __import__('time').monotonic() - _turn_start > self._max_turn_time:
                logger.warning(f"Turn exceeded {self._max_turn_time}s wall-clock limit")
                from nanobot.copilot.alerting.bus import get_alert_bus
                await get_alert_bus().alert("agent", "medium", f"Turn exceeded {self._max_turn_time}s wall-clock limit", "turn_timeout")
                final_content = "I've been working on this for a while. Here's what I have so far — let me know if you'd like me to continue."
                break

            try:
                response = await asyncio.wait_for(
                    self.provider.chat(
                        messages=messages,
                        tools=self.tools.get_definitions(),
                        model=self.model
                    ),
                    timeout=self._llm_timeout,
                )
            except asyncio.TimeoutError:
                logger.warning(f"LLM call timed out after {self._llm_timeout}s in system message loop")
                from nanobot.copilot.alerting.bus import get_alert_bus
                await get_alert_bus().alert("llm", "medium", f"LLM call timed out ({self._llm_timeout}s) in system message loop", "llm_timeout")
                final_content = "I'm sorry, the response timed out. Please try again."
                break

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
                # Interleaved CoT: reflect before next action
                if iteration >= self.max_iterations - 3:
                    messages.append({"role": "user", "content": "Summarize your findings and respond to the user."})
                else:
                    messages.append({"role": "user", "content": "Reflect on the results and decide next steps."})
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
    
    async def _consolidate_memory(self, session, archive_all: bool = False) -> None:
        """Consolidate old messages into MEMORY.md + HISTORY.md, then trim session."""
        if not session.messages:
            return
        memory = MemoryStore(self.workspace)
        if archive_all:
            old_messages = session.messages
            keep_count = 0
        else:
            keep_count = min(10, max(2, self.memory_window // 2))
            old_messages = session.messages[:-keep_count]
        if not old_messages:
            return
        logger.info(f"Memory consolidation started: {len(session.messages)} messages, archiving {len(old_messages)}, keeping {keep_count}")

        # Format messages for LLM (include tool names when available)
        lines = []
        for m in old_messages:
            if not m.get("content"):
                continue
            tools = f" [tools: {', '.join(m['tools_used'])}]" if m.get("tools_used") else ""
            lines.append(f"[{m.get('timestamp', '?')[:16]}] {m['role'].upper()}{tools}: {m['content']}")
        conversation = "\n".join(lines)
        current_memory = memory.read_long_term()

        prompt = f"""You are a memory consolidation agent. Process this conversation and return a JSON object with exactly two keys:

1. "history_entry": A paragraph (2-5 sentences) summarizing the key events/decisions/topics. Start with a timestamp like [YYYY-MM-DD HH:MM]. Include enough detail to be useful when found by grep search later. This is append-only — all detail goes here.

2. "memory_update": The updated long-term memory. This file is injected into EVERY prompt, so it MUST stay under 400 tokens (~300 words). Rules:
   - ONLY keep: active goals, current project status, unresolved blockers, persistent user preferences not already in USER.md
   - REMOVE: resolved issues, stale status, completed tasks, anything already captured in SOUL.md/USER.md/AGENTS.md
   - Move removed detail into the history_entry so nothing is lost
   - If nothing changed, return the existing content unchanged
   - This is NOT a long-term store — it's a lean working-memory snapshot

## Current Long-term Memory
{current_memory or "(empty)"}

## Conversation to Process
{conversation}

Respond with ONLY valid JSON, no markdown fences."""

        try:
            response = await asyncio.wait_for(
                self.provider.chat(
                    messages=[
                        {"role": "system", "content": "You are a memory consolidation agent. Respond only with valid JSON."},
                        {"role": "user", "content": prompt},
                    ],
                    model=self.model,
                ),
                timeout=self._llm_timeout,
            )
            text = (response.content or "").strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            result = json.loads(text)

            if entry := result.get("history_entry"):
                memory.append_history(entry)
            if update := result.get("memory_update"):
                if update != current_memory:
                    memory.write_long_term(update)

            session.messages = session.messages[-keep_count:] if keep_count else []
            self.sessions.save(session)
            logger.info(f"Memory consolidation done, session trimmed to {len(session.messages)} messages")
        except asyncio.TimeoutError:
            logger.warning(f"Memory consolidation LLM call timed out after {self._llm_timeout}s")
            return
        except Exception as e:
            logger.error(f"Memory consolidation failed: {e}")

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
            session_key: Session identifier (overrides channel:chat_id for session lookup).
            channel: Source channel (for tool context routing).
            chat_id: Source chat ID (for tool context routing).
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
            response = await self._process_message(msg, session_key=session_key)
            return response.content if response else ""
        finally:
            if original_model is not None:
                self.model = original_model

    async def _clear_routing_preferences(self, session_key: str) -> None:
        """Clear stored routing preferences for a session (on override expiry)."""
        if not self._copilot_config:
            return
        try:
            import aiosqlite
            async with aiosqlite.connect(self._copilot_config.db_path) as db:
                await db.execute(
                    "DELETE FROM routing_preferences WHERE session_key = ?",
                    (session_key,),
                )
                await db.commit()
            logger.debug(f"Cleared routing preferences for {session_key}")
        except Exception as e:
            logger.warning(f"Clear routing preferences failed: {e}")

    async def _store_routing_preference(
        self, session_key: str, provider: str, tier: str, model: str | None, session,
    ) -> None:
        """Extract keywords from recent messages and store a routing preference."""
        if not self._copilot_config:
            return
        try:
            import aiosqlite
            # Extract keywords from last 5 user messages
            recent = [m["content"] for m in session.messages[-10:] if m.get("role") == "user"]
            text = " ".join(recent).lower()
            # Simple keyword extraction: words 4+ chars, top 10 by frequency
            from collections import Counter
            words = [w for w in text.split() if len(w) >= 4 and w.isalpha()]
            top = [w for w, _ in Counter(words).most_common(10)]
            if not top:
                return
            kw_str = ",".join(top)

            db_path = self._copilot_config.db_path
            async with aiosqlite.connect(db_path) as db:
                # Enforce max 20 preferences per session
                await db.execute(
                    """DELETE FROM routing_preferences WHERE id IN (
                        SELECT id FROM routing_preferences WHERE session_key = ?
                        ORDER BY last_matched DESC LIMIT -1 OFFSET 19
                    )""", (session_key,),
                )
                await db.execute(
                    """INSERT INTO routing_preferences (session_key, provider, tier, model, keywords)
                       VALUES (?, ?, ?, ?, ?)""",
                    (session_key, provider, tier, model, kw_str),
                )
                await db.commit()
            logger.debug(f"Stored routing preference: {provider}/{tier} keywords={kw_str[:60]}")
        except Exception as e:
            logger.warning(f"Store routing preference failed: {e}")

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
