"""CLI commands for nanobot."""

import asyncio
import os
import signal
from pathlib import Path
import select
import sys

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout

from nanobot import __version__, __logo__

app = typer.Typer(
    name="nanobot",
    help=f"{__logo__} nanobot - Personal AI Assistant",
    no_args_is_help=True,
)

console = Console()
EXIT_COMMANDS = {"exit", "quit", "/exit", "/quit", ":q"}

# ---------------------------------------------------------------------------
# CLI input: prompt_toolkit for editing, paste, history, and display
# ---------------------------------------------------------------------------

_PROMPT_SESSION: PromptSession | None = None
_SAVED_TERM_ATTRS = None  # original termios settings, restored on exit


def _flush_pending_tty_input() -> None:
    """Drop unread keypresses typed while the model was generating output."""
    try:
        fd = sys.stdin.fileno()
        if not os.isatty(fd):
            return
    except Exception:
        return

    try:
        import termios
        termios.tcflush(fd, termios.TCIFLUSH)
        return
    except Exception:
        pass

    try:
        while True:
            ready, _, _ = select.select([fd], [], [], 0)
            if not ready:
                break
            if not os.read(fd, 4096):
                break
    except Exception:
        return


def _restore_terminal() -> None:
    """Restore terminal to its original state (echo, line buffering, etc.)."""
    if _SAVED_TERM_ATTRS is None:
        return
    try:
        import termios
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, _SAVED_TERM_ATTRS)
    except Exception:
        pass


def _init_prompt_session() -> None:
    """Create the prompt_toolkit session with persistent file history."""
    global _PROMPT_SESSION, _SAVED_TERM_ATTRS

    # Save terminal state so we can restore it on exit
    try:
        import termios
        _SAVED_TERM_ATTRS = termios.tcgetattr(sys.stdin.fileno())
    except Exception:
        pass

    history_file = Path.home() / ".nanobot" / "history" / "cli_history"
    history_file.parent.mkdir(parents=True, exist_ok=True)

    _PROMPT_SESSION = PromptSession(
        history=FileHistory(str(history_file)),
        enable_open_in_editor=False,
        multiline=False,   # Enter submits (single line mode)
    )


def _print_agent_response(response: str, render_markdown: bool) -> None:
    """Render assistant response with consistent terminal styling."""
    content = response or ""
    body = Markdown(content) if render_markdown else Text(content)
    console.print()
    console.print(f"[cyan]{__logo__} nanobot[/cyan]")
    console.print(body)
    console.print()


def _is_exit_command(command: str) -> bool:
    """Return True when input should end interactive chat."""
    return command.lower() in EXIT_COMMANDS


async def _read_interactive_input_async() -> str:
    """Read user input using prompt_toolkit (handles paste, history, display).

    prompt_toolkit natively handles:
    - Multiline paste (bracketed paste mode)
    - History navigation (up/down arrows)
    - Clean display (no ghost characters or artifacts)
    """
    if _PROMPT_SESSION is None:
        raise RuntimeError("Call _init_prompt_session() first")
    try:
        with patch_stdout():
            return await _PROMPT_SESSION.prompt_async(
                HTML("<b fg='ansiblue'>You:</b> "),
            )
    except EOFError as exc:
        raise KeyboardInterrupt from exc



def version_callback(value: bool):
    if value:
        console.print(f"{__logo__} nanobot v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None, "--version", "-v", callback=version_callback, is_eager=True
    ),
):
    """nanobot - Personal AI Assistant."""
    pass


# ============================================================================
# Onboard / Setup
# ============================================================================


@app.command()
def onboard():
    """Initialize nanobot configuration and workspace."""
    from nanobot.config.loader import get_config_path, load_config, save_config
    from nanobot.config.schema import Config
    from nanobot.utils.helpers import get_workspace_path
    
    config_path = get_config_path()
    
    if config_path.exists():
        # Load existing config — Pydantic fills in defaults for any new fields
        config = load_config()
        save_config(config)
        console.print(f"[green]✓[/green] Config refreshed at {config_path} (existing values preserved)")
    else:
        config = Config()
        save_config(config)
        console.print(f"[green]✓[/green] Created config at {config_path}")
    
    # Create workspace
    workspace = get_workspace_path()
    console.print(f"[green]✓[/green] Created workspace at {workspace}")
    
    # Create default bootstrap files
    _create_workspace_templates(workspace)
    
    console.print(f"\n{__logo__} nanobot is ready!")
    console.print("\nNext steps:")
    console.print("  1. Add your API key to [cyan]~/.nanobot/config.json[/cyan]")
    console.print("     Get one at: https://openrouter.ai/keys")
    console.print("  2. Chat: [cyan]nanobot agent -m \"Hello!\"[/cyan]")
    console.print("\n[dim]Want Telegram/WhatsApp? See: https://github.com/HKUDS/nanobot#-chat-apps[/dim]")




def _create_workspace_templates(workspace: Path):
    """Create default workspace template files."""
    templates = {
        "AGENTS.md": """# Agent Instructions

You are a helpful AI assistant. Be concise, accurate, and friendly.

## Guidelines

- Always explain what you're doing before taking actions
- Ask for clarification when the request is ambiguous
- Use tools to help accomplish tasks
- Remember important information in memory/MEMORY.md; past events are logged in memory/HISTORY.md
""",
        "SOUL.md": """# Soul

I am nanobot, a lightweight AI assistant.

## Personality

- Helpful and friendly
- Concise and to the point
- Curious and eager to learn

## Values

- Accuracy over speed
- User privacy and safety
- Transparency in actions
""",
        "USER.md": """# User

Information about the user goes here.

## Preferences

- Communication style: (casual/formal)
- Timezone: (your timezone)
- Language: (your preferred language)
""",
    }
    
    for filename, content in templates.items():
        file_path = workspace / filename
        if not file_path.exists():
            file_path.write_text(content)
            console.print(f"  [dim]Created {filename}[/dim]")
    
    # Create memory directory and MEMORY.md
    memory_dir = workspace / "memory"
    memory_dir.mkdir(exist_ok=True)
    memory_file = memory_dir / "MEMORY.md"
    if not memory_file.exists():
        memory_file.write_text("""# Long-term Memory

This file stores important information that should persist across sessions.

## User Information

(Important facts about the user)

## Preferences

(User preferences learned over time)

## Important Notes

(Things to remember)
""")
        console.print("  [dim]Created memory/MEMORY.md[/dim]")
    
    history_file = memory_dir / "HISTORY.md"
    if not history_file.exists():
        history_file.write_text("")
        console.print("  [dim]Created memory/HISTORY.md[/dim]")

    # Create skills directory for custom user skills
    skills_dir = workspace / "skills"
    skills_dir.mkdir(exist_ok=True)


def _make_provider(config, cost_logger=None):
    """Create LLM provider from config.

    When ``config.copilot.enabled`` is True and a *cost_logger* is supplied,
    returns a ``RouterProvider`` that routes to local/cloud models
    automatically.  Otherwise returns a plain ``LiteLLMProvider``.
    """
    from nanobot.providers.litellm_provider import LiteLLMProvider

    p = config.get_provider()
    model = config.agents.defaults.model
    if not (p and p.api_key) and not model.startswith("bedrock/"):
        console.print("[red]Error: No API key configured.[/red]")
        console.print("Set one in ~/.nanobot/config.json under providers section")
        raise typer.Exit(1)

    base_provider = LiteLLMProvider(
        api_key=p.api_key if p else None,
        api_base=config.get_api_base(),
        default_model=model,
        extra_headers=p.extra_headers if p else None,
        provider_name=config.get_provider_name(),
    )

    if not config.copilot.enabled or cost_logger is None:
        return base_provider

    # --- Copilot routing ---
    from nanobot.copilot.routing.router import RouterProvider

    # Build cloud providers from ALL configured providers with API keys.
    # Gateways (OpenRouter, AiHubMix) go first — they can route any model.
    # Direct providers (OpenAI, Anthropic) follow as fallbacks.
    from nanobot.providers.registry import find_by_name as _find_by_name
    _gateways: dict[str, LiteLLMProvider] = {}
    _directs: dict[str, LiteLLMProvider] = {}
    for name in type(config.providers).model_fields:
        if name in ("vllm", "custom"):
            continue  # local / special
        pcfg = getattr(config.providers, name)
        if not pcfg.api_key:
            continue
        spec = _find_by_name(name)
        api_base = pcfg.api_base or (spec.default_api_base if spec else None) or None
        provider = LiteLLMProvider(
            api_key=pcfg.api_key,
            api_base=api_base,
            default_model=model,
            extra_headers=pcfg.extra_headers,
            provider_name=name,
        )
        if spec and spec.is_gateway:
            _gateways[name] = provider
        else:
            _directs[name] = provider
    cloud_providers: dict[str, LiteLLMProvider] = {**_gateways, **_directs}

    # Local provider — always LM Studio via vllm config
    vllm_cfg = config.providers.vllm
    if vllm_cfg.api_key or vllm_cfg.api_base:
        local_provider = LiteLLMProvider(
            api_key=vllm_cfg.api_key or "lm-studio",
            api_base=vllm_cfg.api_base,
            default_model=config.copilot.local_model,
            provider_name="vllm",
        )
    else:
        # No local LLM configured — use base_provider as fallback
        local_provider = base_provider

    copilot = config.copilot
    return RouterProvider(
        local_provider=local_provider,
        cloud_providers=cloud_providers,
        cost_logger=cost_logger,
        local_model=copilot.local_model,
        fast_model=copilot.fast_model,
        big_model=copilot.big_model,
        emergency_cloud_model=copilot.emergency_cloud_model,
        escalation_enabled=copilot.escalation_enabled,
        escalation_marker=copilot.escalation_marker,
    )


def _register_copilot_tools(agent, config):
    """Register Phase 5 copilot tools (git, browser, aws, document, n8n)."""
    tool_names = []

    try:
        from nanobot.copilot.tools.git import GitTool
        agent.tools.register(GitTool(default_repo=str(config.workspace_path)))
        tool_names.append("git")
    except Exception:
        pass

    try:
        from nanobot.copilot.tools.document import DocumentTool
        agent.tools.register(DocumentTool())
        tool_names.append("document")
    except Exception:
        pass

    try:
        from nanobot.copilot.tools.browser import BrowserTool
        agent.tools.register(BrowserTool(headless=config.copilot.browser_headless))
        tool_names.append("browser")
    except Exception:
        pass

    try:
        from nanobot.copilot.tools.aws import AWSTool
        agent.tools.register(AWSTool(
            region=config.copilot.aws_region,
            profile=config.copilot.aws_profile,
        ))
        tool_names.append("aws")
    except Exception:
        pass

    try:
        from nanobot.copilot.tools.n8n import N8NTool
        agent.tools.register(N8NTool(base_url=config.copilot.n8n_url))
        tool_names.append("n8n")
    except Exception:
        pass

    if tool_names:
        console.print(f"[green]v[/green] Copilot tools: {', '.join(tool_names)}")


# ============================================================================
# Gateway / Server
# ============================================================================


@app.command()
def gateway(
    port: int = typer.Option(18790, "--port", "-p", help="Gateway port"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Start the nanobot gateway."""
    from nanobot.config.loader import load_config, get_data_dir
    from nanobot.bus.queue import MessageBus
    from nanobot.agent.loop import AgentLoop
    from nanobot.channels.manager import ChannelManager
    from nanobot.session.manager import SessionManager
    from nanobot.cron.service import CronService
    from nanobot.cron.types import CronJob
    from nanobot.heartbeat.service import HeartbeatService
    import os, signal
    from pathlib import Path as _Path

    if verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG)

    # Singleton: kill any existing gateway before starting (prevents duplicate responses)
    # Uses both port-based detection (most reliable) and PID file (backup).
    # Port check catches orphans even when PID file is missing or stale.
    import fcntl, subprocess, time as _time
    pid_file = _Path("/tmp/nanobot-gateway.pid")

    def _kill_existing_gateway():
        my_pid = os.getpid()
        killed = []

        # Port-based detection: find anything on our gateway port
        try:
            result = subprocess.run(
                ["lsof", "-ti", f"tcp:{port}"],
                capture_output=True, text=True, timeout=5,
            )
            for pid_str in result.stdout.strip().split("\n"):
                pid_str = pid_str.strip()
                if pid_str and int(pid_str) != my_pid:
                    try:
                        os.kill(int(pid_str), signal.SIGTERM)
                        killed.append(pid_str)
                    except (ProcessLookupError, PermissionError):
                        pass
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass  # lsof not available or timed out

        # PID file: catch processes that haven't bound the port yet
        if pid_file.exists():
            try:
                old_pid = int(pid_file.read_text().strip())
                if old_pid != my_pid and str(old_pid) not in killed:
                    try:
                        os.kill(old_pid, signal.SIGTERM)
                        killed.append(str(old_pid))
                    except (ProcessLookupError, PermissionError):
                        pass
            except (ValueError, OSError):
                pass

        if killed:
            console.print(f"[yellow]Stopped previous gateway (pid {', '.join(killed)})[/yellow]")
            _time.sleep(2)  # Let old process clean up

    _kill_existing_gateway()

    # Acquire flock with retry (old process may need a moment to release)
    _pid_fd = open(pid_file, "w")
    _pid_fd.write(str(os.getpid()))
    _pid_fd.flush()
    for _attempt in range(3):
        try:
            fcntl.flock(_pid_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError:
            if _attempt < 2:
                _time.sleep(2)
            else:
                console.print(f"[red]Cannot acquire gateway lock after 3 attempts. Check for orphan processes.[/red]")
                raise typer.Exit(1)
    # Keep _pid_fd open — lock held for process lifetime. Don't delete file on exit.

    # Persistent log file (rotated, 7-day retention)
    from loguru import logger as _loguru
    _log_path = _Path.home() / ".nanobot" / "logs" / "gateway.log"
    _log_path.parent.mkdir(parents=True, exist_ok=True)
    _loguru.add(
        str(_log_path),
        rotation="10 MB",
        retention="7 days",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
    )

    console.print(f"{__logo__} Starting nanobot gateway on port {port}...")

    config = load_config()
    bus = MessageBus()

    # --- Copilot: initialise cost logger if enabled ---
    cost_logger = None
    if config.copilot.enabled:
        import asyncio as _aio
        from nanobot.copilot.cost.db import ensure_tables, migrate_alerts, migrate_routing_preferences, migrate_heartbeat_events, migrate_alert_resolution
        from nanobot.copilot.cost.logger import CostLogger
        from pathlib import Path

        db_path = Path(config.copilot.db_path)
        _aio.run(ensure_tables(db_path))
        _aio.run(migrate_alerts(db_path))
        _aio.run(migrate_routing_preferences(db_path))
        _aio.run(migrate_heartbeat_events(db_path))
        _aio.run(migrate_alert_resolution(db_path))
        cost_logger = CostLogger(db_path)
        console.print("[green]✓[/green] Copilot enabled (routing + cost tracking)")
        # Normalize monitor_chat_id for WhatsApp (must be JID format)
        if config.copilot.monitor_chat_id and config.copilot.monitor_channel == "whatsapp":
            if "@" not in config.copilot.monitor_chat_id:
                config.copilot.monitor_chat_id += "@s.whatsapp.net"
        # Auto-derive monitor_chat_id from whatsapp.allow_from if not set
        if not config.copilot.monitor_chat_id and config.copilot.monitor_channel == "whatsapp":
            if config.whatsapp.allow_from:
                config.copilot.monitor_chat_id = config.whatsapp.allow_from[0] + "@s.whatsapp.net"
                console.print(f"[green]✓[/green] monitor_chat_id auto-set from whatsapp.allow_from")
        if not config.copilot.monitor_chat_id:
            console.print("[yellow]Warning: copilot.monitor_chat_id is empty — alerts/dream reports won't be delivered[/yellow]")

    # --- Copilot: initialise alert bus if enabled ---
    alert_bus = None
    if config.copilot.enabled:
        from nanobot.copilot.alerting.bus import init_alert_bus

        async def _alert_deliver(content):
            from nanobot.bus.events import OutboundMessage
            await bus.publish_outbound(OutboundMessage(
                channel=config.copilot.monitor_channel,
                chat_id=config.copilot.monitor_chat_id,
                content=content,
            ))

        alert_bus = init_alert_bus(
            db_path=str(db_path),
            deliver_fn=_alert_deliver,
            dedup_hours=config.copilot.alert_dedup_hours,
        )
        console.print("[green]v[/green] Alert bus enabled")

    provider = _make_provider(config, cost_logger=cost_logger)
    session_manager = SessionManager(config.workspace_path)
    
    # Create cron service first (callback set after agent creation)
    cron_store_path = get_data_dir() / "cron" / "jobs.json"
    cron = CronService(cron_store_path)
    
    # --- Copilot: initialise background extractor if enabled ---
    extractor = None
    if config.copilot.enabled:
        from nanobot.copilot.extraction.background import BackgroundExtractor

        # Reuse the local provider (vllm) for extraction when available
        local_extractor_provider = None
        vllm_cfg = config.providers.vllm
        if vllm_cfg.api_key or vllm_cfg.api_base:
            from nanobot.providers.litellm_provider import LiteLLMProvider
            local_extractor_provider = LiteLLMProvider(
                api_key=vllm_cfg.api_key or "lm-studio",
                api_base=vllm_cfg.api_base,
                default_model=config.copilot.resolved_extraction_local_model,
                provider_name="vllm",
            )

        # Cloud fallback for extraction: reuse the main cloud provider
        cloud_extractor_provider = None
        cloud_p = config.get_provider()
        if cloud_p and cloud_p.api_key:
            from nanobot.providers.litellm_provider import LiteLLMProvider as _LEP
            cloud_extractor_provider = _LEP(
                api_key=cloud_p.api_key,
                api_base=config.get_api_base(),
                default_model=config.copilot.resolved_extraction_cloud_model,
                extra_headers=cloud_p.extra_headers,
                provider_name=config.get_provider_name(),
            )

        extractor = BackgroundExtractor(
            local_provider=local_extractor_provider,
            fallback_provider=cloud_extractor_provider,
            cost_logger=cost_logger,
            local_model=config.copilot.resolved_extraction_local_model,
            fallback_model=config.copilot.resolved_extraction_cloud_model,
        )

        # Persist extraction results into session metadata
        async def _persist_extraction(session_key, result):
            session = session_manager.get_or_create(session_key)
            extractions = session.metadata.get("extractions", [])
            extractions.append(result.model_dump())
            session.metadata["extractions"] = extractions[-1000:]
            session_manager.save(session)

        extractor.on_result = _persist_extraction
        console.print("[green]✓[/green] Background extraction enabled")

    # --- Copilot: extended context builder ---
    extended_context = None
    if config.copilot.enabled:
        from nanobot.agent.context import ContextBuilder
        from nanobot.copilot.context.extended import ExtendedContextBuilder
        from nanobot.copilot.context.budget import TokenBudget

        extended_context = ExtendedContextBuilder(
            base=ContextBuilder(config.workspace_path),
            budget=TokenBudget(),
            context_budget=config.copilot.context_budget,
            continuation_threshold=config.copilot.continuation_threshold,
        )
        console.print("[green]✓[/green] Extended context builder enabled")

    # --- Copilot: thread tracker ---
    thread_tracker = None
    if config.copilot.enabled:
        from nanobot.copilot.threading.tracker import ThreadTracker
        thread_tracker = ThreadTracker()

    # --- Copilot: Phase 3 components ---
    lesson_manager = None
    satisfaction_detector = None
    cost_alerter = None

    if config.copilot.enabled:
        import asyncio as _aio
        from nanobot.copilot.cost.db import migrate_phase3

        db_path = Path(config.copilot.db_path)
        _aio.run(migrate_phase3(db_path))

        from nanobot.copilot.metacognition.lessons import LessonManager
        lesson_manager = LessonManager(db_path)

        from nanobot.copilot.metacognition.detector import SatisfactionDetector
        satisfaction_detector = SatisfactionDetector(lesson_manager)

        console.print("[green]v[/green] Metacognition enabled")

        # Chain satisfaction detector onto extraction callback
        if extractor:
            _orig = extractor.on_result
            async def _persist_and_detect(session_key, result):
                if _orig:
                    await _orig(session_key, result)
                await satisfaction_detector.on_extraction_result(session_key, result)
            extractor.on_result = _persist_and_detect

        # Cost alerter
        from nanobot.copilot.cost.alerting import CostAlerter
        cost_alerter = CostAlerter(
            db_path, bus,
            config.copilot.daily_cost_alert,
            config.copilot.per_call_cost_alert,
            config.copilot.monitor_channel,
            config.copilot.monitor_chat_id,
        )

    # --- Copilot: Phase 4 — Memory ---
    memory_manager = None
    if config.copilot.enabled:
        import asyncio as _aio
        from nanobot.copilot.cost.db import migrate_phase4
        db_path = Path(config.copilot.db_path)
        _aio.run(migrate_phase4(db_path))

        try:
            from nanobot.copilot.memory.embedder import Embedder
            from nanobot.copilot.memory.manager import MemoryManager

            embedder = Embedder(
                api_base=(config.providers.vllm.api_base or "http://192.168.50.100:1234/v1"),
                model=config.copilot.embedding_local_model,
                dimensions=config.copilot.embedding_local_dimensions,
                cloud_api_key=config.copilot.cloud_embedding_api_key or None,
                cloud_api_base=config.copilot.cloud_embedding_api_base or None,
                cloud_model=config.copilot.cloud_embedding_model,
                cloud_dimensions=config.copilot.cloud_embedding_dimensions,
            )
            memory_manager = MemoryManager(
                embedder=embedder,
                qdrant_url=config.copilot.qdrant_url,
                redis_url=config.copilot.redis_url,
                db_path=db_path,
                dimensions=config.copilot.embedding_local_dimensions,
            )
            for _mem_attempt in range(3):
                try:
                    _aio.run(memory_manager.initialize())
                    break
                except Exception as _mem_err:
                    if _mem_attempt < 2:
                        console.print(f"[yellow]Memory init attempt {_mem_attempt + 1} failed, retrying...[/yellow]")
                        import time as _t; _t.sleep(2)
                    else:
                        raise _mem_err
            console.print("[green]v[/green] Memory system enabled (Qdrant + Redis + SQLite)")
        except Exception as e:
            console.print(f"[yellow]Warning: Memory init failed (degraded): {e}[/yellow]")
            memory_manager = None

        # Chain extractions into memory
        if extractor and memory_manager:
            _orig_ext = extractor.on_result
            async def _persist_extract_and_memorize(session_key, result):
                if _orig_ext:
                    await _orig_ext(session_key, result)
                data = result.model_dump() if hasattr(result, 'model_dump') else result
                await memory_manager.remember_extractions(data, session_key)
            extractor.on_result = _persist_extract_and_memorize

    # --- Copilot: SLM deferred work queue ---
    slm_queue = None
    slm_drainer = None
    if config.copilot.enabled and config.copilot.slm_queue_enabled and extractor and memory_manager:
        import asyncio as _aio_q
        from nanobot.copilot.db import SqlitePool
        from nanobot.copilot.slm_queue.manager import SlmWorkQueue
        from nanobot.copilot.slm_queue.drainer import SlmQueueDrainer

        _slm_pool = SqlitePool(config.copilot.db_path)
        _aio_q.run(_slm_pool.start())
        slm_queue = SlmWorkQueue(_slm_pool, size_limit=config.copilot.slm_queue_size_limit)
        _aio_q.run(slm_queue.initialize())

        # Wire queue into extractor and memory manager
        extractor._slm_queue = slm_queue
        if memory_manager:
            memory_manager._slm_queue = slm_queue

        # LM Studio base URL for health probes
        _lm_url = (config.providers.vllm.api_base or "http://192.168.50.100:1234").rstrip("/v1").rstrip("/")

        slm_drainer = SlmQueueDrainer(
            queue=slm_queue,
            extractor=extractor,
            memory_manager=memory_manager,
            lm_studio_url=_lm_url,
            rate_per_minute=config.copilot.slm_drain_rate,
        )
        console.print("[green]✓[/green] SLM work queue enabled")

    # --- Copilot: extended context with identity docs + memory ---
    if extended_context and config.copilot.enabled:
        extended_context._docs_dir = Path(config.copilot.copilot_docs_dir)
        if memory_manager:
            extended_context._memory_manager = memory_manager

    # Create agent with cron service
    agent = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.agents.defaults.model,
        max_iterations=config.agents.defaults.max_tool_iterations,
        memory_window=config.agents.defaults.memory_window,
        llm_timeout=config.agents.defaults.llm_timeout,
        brave_api_key=config.tools.web.search.api_key or None,
        exec_config=config.tools.exec,
        cron_service=cron,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        session_manager=session_manager,
        extended_context=extended_context,
        extractor=extractor,
        thread_tracker=thread_tracker,
        lesson_manager=lesson_manager,
        satisfaction_detector=satisfaction_detector,
        memory_manager=memory_manager,
        copilot_config=config.copilot if config.copilot.enabled else None,
    )

    # Register file-based secrets for leak detection
    for pname in config.providers.model_fields:
        pcfg = getattr(config.providers, pname, None)
        if pcfg:
            key = getattr(pcfg, "api_key", "") or ""
            if key and len(key) >= 8:
                agent.secrets.register(f"provider:{pname}", key)
    brave_key = config.tools.web.search.api_key or ""
    if brave_key and len(brave_key) >= 8:
        agent.secrets.register("brave_api_key", brave_key)

    # --- Copilot: Phase 4 — register memory + recall tools ---
    if memory_manager:
        from nanobot.copilot.memory.tool import MemoryTool
        agent.tools.register(MemoryTool(memory_manager))

    if config.copilot.enabled:
        from nanobot.copilot.tools.recall import RecallMessagesTool
        agent.tools.register(RecallMessagesTool(session_manager))

    # --- Copilot: Phase 5 — register copilot tools ---
    if config.copilot.enabled:
        _register_copilot_tools(agent, config)

    # --- Copilot: set_preference tool ---
    pref_tool = None
    if config.copilot.enabled:
        from nanobot.copilot.tools.preferences import SetPreferenceTool
        from nanobot.config.loader import get_config_path

        reschedule_cbs: dict = {}
        # Heartbeat reschedule uses a late-binding closure so it works
        # even though copilot_heartbeat is created later in this function.
        def _restart_heartbeat(val):
            if copilot_heartbeat is not None:
                copilot_heartbeat._interval_s = int(val)
        reschedule_cbs["heartbeat_interval"] = _restart_heartbeat

        pref_tool = SetPreferenceTool(
            config_path=get_config_path(),
            copilot_config=config.copilot,
            router=provider if hasattr(provider, 'set_model') else None,
            reschedule_callbacks=reschedule_cbs,
        )
        agent.tools.register(pref_tool)
        console.print("[green]v[/green] Preference tool enabled")

    # --- Copilot: Phase 6 — status dashboard ---
    status_aggregator = None
    if config.copilot.enabled:
        try:
            from nanobot.copilot.status.aggregator import StatusAggregator
            from nanobot.copilot.status.tool import StatusTool

            status_aggregator = StatusAggregator(
                db_path=str(db_path),
                lm_studio_url=config.providers.vllm.api_base or "http://192.168.50.100:1234",
                qdrant_url=config.copilot.qdrant_url,
                redis_url=config.copilot.redis_url,
                memory_manager=memory_manager,
                router=provider if hasattr(provider, '_fast_model') else None,
            )
            agent.tools.register(StatusTool(status_aggregator))
            console.print("[green]v[/green] Status dashboard enabled")

            from nanobot.copilot.tools.ops_log import OpsLogTool
            agent.tools.register(OpsLogTool(db_path=str(db_path)))
            console.print("[green]v[/green] Ops log tool enabled")

            from nanobot.copilot.tools.use_model import UseModelTool
            _timeout_min = (config.copilot.use_override_timeout or 1800) // 60
            agent.tools.register(UseModelTool(session_manager, timeout_minutes=_timeout_min))
            console.print("[green]v[/green] Model override tool enabled")
        except Exception as e:
            console.print(f"[yellow]Warning: Status init failed: {e}[/yellow]")

    # --- Copilot: Phase 7 — task queue ---
    task_worker = None
    if config.copilot.enabled:
        try:
            from nanobot.copilot.cost.db import migrate_phase7
            _aio.run(migrate_phase7(db_path))

            from nanobot.copilot.tasks.manager import TaskManager
            from nanobot.copilot.tasks.tool import TaskTool
            from nanobot.copilot.tasks.worker import TaskWorker
            from nanobot.copilot.tasks.prompts import build_decomposition_prompt

            task_manager = TaskManager(db_path)
            agent.tools.register(TaskTool(task_manager))
            agent._task_manager = task_manager

            _task_model = config.copilot.resolved_task_model or None
            _decomp_model = config.copilot.resolved_decomposition_model
            _monitor_ch = config.copilot.monitor_channel
            _monitor_cid = config.copilot.monitor_chat_id

            async def _decompose_task(description: str) -> str:
                pool_path = Path(config.copilot.copilot_docs_dir) / "models.md"
                model_pool = pool_path.read_text() if pool_path.exists() else None
                prompt = build_decomposition_prompt(description, model_pool=model_pool)
                return await agent.process_direct(
                    prompt, session_key="task:decompose", model=_decomp_model,
                )

            async def _notify_task_progress(message: str) -> None:
                if _monitor_cid:
                    from nanobot.bus.events import OutboundMessage
                    await bus.publish_outbound(OutboundMessage(
                        channel=_monitor_ch, chat_id=_monitor_cid, content=message,
                    ))

            async def _execute_step(desc: str, sk: str, ch: str, tool_type: str, recommended_model: str = "") -> str:
                model = recommended_model or _task_model
                return await agent.process_direct(
                    desc, session_key=sk, channel=ch, model=model,
                )

            task_worker = TaskWorker(
                task_manager=task_manager,
                execute_fn=_execute_step,
                decompose_fn=_decompose_task,
                notify_fn=_notify_task_progress,
                interval_s=config.copilot.task_worker_interval,
            )

            # Increase subagent iteration limit for task execution
            agent.subagents.max_iterations = 50

            console.print("[green]v[/green] Task queue enabled (with decomposition)")
        except Exception as e:
            console.print(f"[yellow]Warning: Task queue init failed: {e}[/yellow]")

    # Set cron callback (needs agent)
    async def on_cron_job(job: CronJob) -> str | None:
        """Execute a cron job through the agent."""
        response = await agent.process_direct(
            job.payload.message,
            session_key=f"cron:{job.id}",
            channel=job.payload.channel or "cli",
            chat_id=job.payload.to or "direct",
        )
        if job.payload.deliver and job.payload.to:
            from nanobot.bus.events import OutboundMessage
            await bus.publish_outbound(OutboundMessage(
                channel=job.payload.channel or "cli",
                chat_id=job.payload.to,
                content=response or ""
            ))
        return response
    cron.on_job = on_cron_job
    
    # Create heartbeat service
    async def on_heartbeat(prompt: str) -> str:
        """Execute heartbeat through the agent."""
        return await agent.process_direct(prompt, session_key="heartbeat")

    heartbeat = HeartbeatService(
        workspace=config.workspace_path,
        on_heartbeat=on_heartbeat,
        interval_s=2 * 60 * 60,  # 2 hours — injection prompt for v2 LLM calls
        enabled=True
    )

    # --- Copilot: Phase 8 — dream cycle + monitor + copilot heartbeat ---
    dream_cycle = None
    monitor_service = None
    copilot_heartbeat = None

    if config.copilot.enabled:
        import asyncio as _aio
        from nanobot.copilot.cost.db import migrate_phase8
        db_path = Path(config.copilot.db_path)
        _aio.run(migrate_phase8(db_path))

        try:
            from nanobot.copilot.dream.cycle import DreamCycle
            from nanobot.copilot.dream.monitor import MonitorService
            from nanobot.copilot.dream.heartbeat import CopilotHeartbeatService

            async def _deliver_msg(channel, chat_id, content):
                from nanobot.bus.events import OutboundMessage
                await bus.publish_outbound(OutboundMessage(
                    channel=channel, chat_id=chat_id, content=content,
                ))

            _dream_model = config.copilot.resolved_dream_model or None
            dream_cycle = DreamCycle(
                db_path=str(db_path),
                memory_manager=memory_manager,
                status_aggregator=status_aggregator,
                execute_fn=lambda prompt: agent.process_direct(
                    prompt, session_key="dream", model=_dream_model,
                ),
                backup_dir=config.copilot.backup_dir,
                deliver_fn=_deliver_msg,
                delivery_channel=config.copilot.monitor_channel,
                delivery_chat_id=config.copilot.monitor_chat_id,
                docs_dir=config.copilot.copilot_docs_dir,
                emergency_cloud_model=config.copilot.emergency_cloud_model,
            )

            if slm_queue:
                dream_cycle._slm_queue = slm_queue
            if slm_queue and status_aggregator:
                status_aggregator._slm_queue = slm_queue
            if status_aggregator:
                status_aggregator._heartbeat = heartbeat

            monitor_service = MonitorService(
                status_aggregator=status_aggregator,
                deliver_fn=_deliver_msg,
                delivery_channel=config.copilot.monitor_channel,
                delivery_chat_id=config.copilot.monitor_chat_id,
                interval_s=config.copilot.monitor_interval,
                silent_subsystems={"LM Studio"},
            )

            _hb_model = config.copilot.resolved_heartbeat_model or None
            copilot_heartbeat = CopilotHeartbeatService(
                copilot_docs_dir=config.copilot.copilot_docs_dir,
                execute_fn=lambda prompt: agent.process_direct(
                    prompt, session_key="copilot_heartbeat", model=_hb_model,
                ),
                deliver_fn=_deliver_msg,
                delivery_channel=config.copilot.monitor_channel,
                delivery_chat_id=config.copilot.monitor_chat_id,
                db_path=str(db_path),
                interval_s=config.copilot.heartbeat_interval,
                qdrant_url=config.copilot.qdrant_url,
                redis_url=config.copilot.redis_url,
            )
            console.print("[green]v[/green] Dream cycle + monitor + heartbeat enabled")
        except Exception as e:
            console.print(f"[yellow]Warning: Dream/monitor init failed: {e}[/yellow]")
    
    # --- Copilot: voice transcriber ---
    voice_transcriber = None
    if config.copilot.enabled:
        from nanobot.copilot.voice.transcriber import VoiceTranscriber
        groq_key = config.providers.groq.api_key or None
        voice_transcriber = VoiceTranscriber(groq_api_key=groq_key)
        console.print("[green]✓[/green] Voice transcription enabled")

    # Create channel manager
    channels = ChannelManager(
        config, bus, session_manager=session_manager,
        voice_transcriber=voice_transcriber,
    )
    
    if channels.enabled_channels:
        console.print(f"[green]✓[/green] Channels enabled: {', '.join(channels.enabled_channels)}")
    else:
        console.print("[yellow]Warning: No channels enabled[/yellow]")
    
    cron_status = cron.status()
    if cron_status["jobs"] > 0:
        console.print(f"[green]✓[/green] Cron: {cron_status['jobs']} scheduled jobs")
    
    hb_interval = config.copilot.heartbeat_interval // 60 if config.copilot.enabled else 0
    console.print(f"[green]✓[/green] Heartbeat: health every {hb_interval}m, HEARTBEAT.md every 2h")

    # --- Process Supervisor ---
    from nanobot.copilot.dream.supervisor import ProcessSupervisor
    supervisor = ProcessSupervisor(check_interval=30.0, max_restarts=5)

    async def run():
        try:
            await cron.start()
            # Register services with supervisor — it calls start() for us
            supervisor.register("heartbeat", heartbeat.start, lambda: heartbeat._task)
            if task_worker:
                supervisor.register("task_worker", task_worker.start, lambda: task_worker._task)
            if monitor_service:
                supervisor.register("monitor", monitor_service.start, lambda: monitor_service._task)
            if copilot_heartbeat:
                supervisor.register("copilot_heartbeat", copilot_heartbeat.start, lambda: copilot_heartbeat._task)
            if slm_drainer:
                supervisor.register("slm_drainer", slm_drainer.start, lambda: slm_drainer._task)
            await supervisor.start()
            console.print("[green]v[/green] Process supervisor started")

            # Schedule dream cycle via croniter
            dream_task = None
            _dream_cancel_event = asyncio.Event()
            if dream_cycle:
                import time as _time
                from croniter import croniter as _croniter

                async def _dream_scheduler():
                    from loguru import logger as _dream_log
                    while True:
                        # Re-read cron expr each iteration (supports runtime changes)
                        cron_it = _croniter(config.copilot.dream_cron_expr, _time.time())
                        delay = cron_it.get_next() - _time.time()
                        if delay > 0:
                            try:
                                await asyncio.wait_for(_dream_cancel_event.wait(), timeout=delay)
                                _dream_cancel_event.clear()
                                continue  # Cancelled — re-read cron expr
                            except asyncio.TimeoutError:
                                pass  # Normal wake-up
                        try:
                            report = await dream_cycle.run()
                            _dream_log.info(f"Dream cycle complete: {report.to_summary()}")
                        except Exception as exc:
                            _dream_log.error(f"Dream cycle failed: {exc}")

                dream_task = asyncio.create_task(_dream_scheduler(), name="dream_scheduler")
                from loguru import logger as _log
                _log.info(f"Dream cycle scheduled: {config.copilot.dream_cron_expr}")

                # Wire reschedule callback for set_preference tool
                if config.copilot.enabled and pref_tool is not None:
                    def _reschedule_dream(val):
                        _dream_cancel_event.set()  # Wake scheduler to re-read cron
                    pref_tool._reschedule["dream_cron_expr"] = _reschedule_dream

            # Weekly review scheduler
            weekly_task = None
            _weekly_cancel_event = asyncio.Event()
            if dream_cycle:
                async def _weekly_scheduler():
                    from loguru import logger as _weekly_log
                    while True:
                        cron_it = _croniter(config.copilot.weekly_review_cron_expr, _time.time())
                        delay = cron_it.get_next() - _time.time()
                        if delay > 0:
                            try:
                                await asyncio.wait_for(_weekly_cancel_event.wait(), timeout=delay)
                                _weekly_cancel_event.clear()
                                continue
                            except asyncio.TimeoutError:
                                pass
                        try:
                            result = await dream_cycle.run_weekly()
                            _weekly_log.info("Weekly review complete")
                        except Exception as exc:
                            _weekly_log.error(f"Weekly review failed: {exc}")

                weekly_task = asyncio.create_task(_weekly_scheduler(), name="weekly_review")
                _log.info(f"Weekly review scheduled: {config.copilot.weekly_review_cron_expr}")

                if config.copilot.enabled and pref_tool is not None:
                    def _reschedule_weekly(val):
                        _weekly_cancel_event.set()
                    pref_tool._reschedule["weekly_review_cron_expr"] = _reschedule_weekly

            # Signal handling: SIGTERM/SIGINT trigger graceful shutdown
            shutdown_event = asyncio.Event()
            loop = asyncio.get_event_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, shutdown_event.set)

            done, pending = await asyncio.wait(
                [
                    asyncio.create_task(agent.run(), name="agent"),
                    asyncio.create_task(channels.start_all(), name="channels"),
                    asyncio.create_task(shutdown_event.wait(), name="shutdown"),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
        except KeyboardInterrupt:
            pass  # Handled by signal handler above
        finally:
            console.print("\nShutting down...")
            await supervisor.stop()
            if slm_drainer:
                await slm_drainer.stop()
            if copilot_heartbeat:
                copilot_heartbeat.stop()
            if monitor_service:
                monitor_service.stop()
            if task_worker:
                task_worker.stop()
            heartbeat.stop()
            cron.stop()
            await agent.stop()
            await channels.stop_all()

    asyncio.run(run())




# ============================================================================
# Agent Commands
# ============================================================================


@app.command()
def agent(
    message: str = typer.Option(None, "--message", "-m", help="Message to send to the agent"),
    session_id: str = typer.Option("cli:direct", "--session", "-s", help="Session ID"),
    markdown: bool = typer.Option(True, "--markdown/--no-markdown", help="Render assistant output as Markdown"),
    logs: bool = typer.Option(False, "--logs/--no-logs", help="Show nanobot runtime logs during chat"),
):
    """Interact with the agent directly."""
    from nanobot.config.loader import load_config
    from nanobot.bus.queue import MessageBus
    from nanobot.agent.loop import AgentLoop
    from loguru import logger
    
    config = load_config()
    
    bus = MessageBus()
    provider = _make_provider(config)

    if logs:
        logger.enable("nanobot")
    else:
        logger.disable("nanobot")
    
    agent_loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.agents.defaults.model,
        max_iterations=config.agents.defaults.max_tool_iterations,
        memory_window=config.agents.defaults.memory_window,
        llm_timeout=config.agents.defaults.llm_timeout,
        brave_api_key=config.tools.web.search.api_key or None,
        exec_config=config.tools.exec,
        restrict_to_workspace=config.tools.restrict_to_workspace,
    )
    
    # Show spinner when logs are off (no output to miss); skip when logs are on
    def _thinking_ctx():
        if logs:
            from contextlib import nullcontext
            return nullcontext()
        # Animated spinner is safe to use with prompt_toolkit input handling
        return console.status("[dim]nanobot is thinking...[/dim]", spinner="dots")

    if message:
        # Single message mode
        async def run_once():
            with _thinking_ctx():
                response = await agent_loop.process_direct(message, session_id)
            _print_agent_response(response, render_markdown=markdown)
        
        asyncio.run(run_once())
    else:
        # Interactive mode
        _init_prompt_session()
        console.print(f"{__logo__} Interactive mode (type [bold]exit[/bold] or [bold]Ctrl+C[/bold] to quit)\n")

        def _exit_on_sigint(signum, frame):
            _restore_terminal()
            console.print("\nGoodbye!")
            os._exit(0)

        signal.signal(signal.SIGINT, _exit_on_sigint)
        
        async def run_interactive():
            while True:
                try:
                    _flush_pending_tty_input()
                    user_input = await _read_interactive_input_async()
                    command = user_input.strip()
                    if not command:
                        continue

                    if _is_exit_command(command):
                        _restore_terminal()
                        console.print("\nGoodbye!")
                        break
                    
                    with _thinking_ctx():
                        response = await agent_loop.process_direct(user_input, session_id)
                    _print_agent_response(response, render_markdown=markdown)
                except KeyboardInterrupt:
                    _restore_terminal()
                    console.print("\nGoodbye!")
                    break
                except EOFError:
                    _restore_terminal()
                    console.print("\nGoodbye!")
                    break
        
        asyncio.run(run_interactive())


# ============================================================================
# Channel Commands
# ============================================================================


channels_app = typer.Typer(help="Manage channels")
app.add_typer(channels_app, name="channels")


@channels_app.command("status")
def channels_status():
    """Show channel status."""
    from nanobot.config.loader import load_config

    config = load_config()

    table = Table(title="Channel Status")
    table.add_column("Channel", style="cyan")
    table.add_column("Enabled", style="green")
    table.add_column("Configuration", style="yellow")

    # WhatsApp
    wa = config.channels.whatsapp
    table.add_row(
        "WhatsApp",
        "✓" if wa.enabled else "✗",
        wa.bridge_url
    )

    dc = config.channels.discord
    table.add_row(
        "Discord",
        "✓" if dc.enabled else "✗",
        dc.gateway_url
    )

    # Feishu
    fs = config.channels.feishu
    fs_config = f"app_id: {fs.app_id[:10]}..." if fs.app_id else "[dim]not configured[/dim]"
    table.add_row(
        "Feishu",
        "✓" if fs.enabled else "✗",
        fs_config
    )

    # Mochat
    mc = config.channels.mochat
    mc_base = mc.base_url or "[dim]not configured[/dim]"
    table.add_row(
        "Mochat",
        "✓" if mc.enabled else "✗",
        mc_base
    )
    
    # Telegram
    tg = config.channels.telegram
    tg_config = f"token: {tg.token[:10]}..." if tg.token else "[dim]not configured[/dim]"
    table.add_row(
        "Telegram",
        "✓" if tg.enabled else "✗",
        tg_config
    )

    # Slack
    slack = config.channels.slack
    slack_config = "socket" if slack.app_token and slack.bot_token else "[dim]not configured[/dim]"
    table.add_row(
        "Slack",
        "✓" if slack.enabled else "✗",
        slack_config
    )

    console.print(table)


def _get_bridge_dir() -> Path:
    """Get the bridge directory, setting it up if needed."""
    import shutil
    import subprocess
    
    # User's bridge location
    user_bridge = Path.home() / ".nanobot" / "bridge"
    
    # Check if already built
    if (user_bridge / "dist" / "index.js").exists():
        return user_bridge
    
    # Check for npm
    if not shutil.which("npm"):
        console.print("[red]npm not found. Please install Node.js >= 18.[/red]")
        raise typer.Exit(1)
    
    # Find source bridge: first check package data, then source dir
    pkg_bridge = Path(__file__).parent.parent / "bridge"  # nanobot/bridge (installed)
    src_bridge = Path(__file__).parent.parent.parent / "bridge"  # repo root/bridge (dev)
    
    source = None
    if (pkg_bridge / "package.json").exists():
        source = pkg_bridge
    elif (src_bridge / "package.json").exists():
        source = src_bridge
    
    if not source:
        console.print("[red]Bridge source not found.[/red]")
        console.print("Try reinstalling: pip install --force-reinstall nanobot")
        raise typer.Exit(1)
    
    console.print(f"{__logo__} Setting up bridge...")
    
    # Copy to user directory
    user_bridge.parent.mkdir(parents=True, exist_ok=True)
    if user_bridge.exists():
        shutil.rmtree(user_bridge)
    shutil.copytree(source, user_bridge, ignore=shutil.ignore_patterns("node_modules", "dist"))
    
    # Install and build
    try:
        console.print("  Installing dependencies...")
        subprocess.run(["npm", "install"], cwd=user_bridge, check=True, capture_output=True)
        
        console.print("  Building...")
        subprocess.run(["npm", "run", "build"], cwd=user_bridge, check=True, capture_output=True)
        
        console.print("[green]✓[/green] Bridge ready\n")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Build failed: {e}[/red]")
        if e.stderr:
            console.print(f"[dim]{e.stderr.decode()[:500]}[/dim]")
        raise typer.Exit(1)
    
    return user_bridge


@channels_app.command("login")
def channels_login():
    """Link device via QR code."""
    import subprocess
    from nanobot.config.loader import load_config
    
    config = load_config()
    bridge_dir = _get_bridge_dir()
    
    console.print(f"{__logo__} Starting bridge...")
    console.print("Scan the QR code to connect.\n")
    
    env = {**os.environ}
    if config.channels.whatsapp.bridge_token:
        env["BRIDGE_TOKEN"] = config.channels.whatsapp.bridge_token
    
    try:
        subprocess.run(["npm", "start"], cwd=bridge_dir, check=True, env=env)
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Bridge failed: {e}[/red]")
    except FileNotFoundError:
        console.print("[red]npm not found. Please install Node.js.[/red]")


# ============================================================================
# Cron Commands
# ============================================================================

cron_app = typer.Typer(help="Manage scheduled tasks")
app.add_typer(cron_app, name="cron")


@cron_app.command("list")
def cron_list(
    all: bool = typer.Option(False, "--all", "-a", help="Include disabled jobs"),
):
    """List scheduled jobs."""
    from nanobot.config.loader import get_data_dir
    from nanobot.cron.service import CronService
    
    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)
    
    jobs = service.list_jobs(include_disabled=all)
    
    if not jobs:
        console.print("No scheduled jobs.")
        return
    
    table = Table(title="Scheduled Jobs")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Schedule")
    table.add_column("Status")
    table.add_column("Next Run")
    
    import time
    for job in jobs:
        # Format schedule
        if job.schedule.kind == "every":
            sched = f"every {(job.schedule.every_ms or 0) // 1000}s"
        elif job.schedule.kind == "cron":
            sched = job.schedule.expr or ""
        else:
            sched = "one-time"
        
        # Format next run
        next_run = ""
        if job.state.next_run_at_ms:
            next_time = time.strftime("%Y-%m-%d %H:%M", time.localtime(job.state.next_run_at_ms / 1000))
            next_run = next_time
        
        status = "[green]enabled[/green]" if job.enabled else "[dim]disabled[/dim]"
        
        table.add_row(job.id, job.name, sched, status, next_run)
    
    console.print(table)


@cron_app.command("add")
def cron_add(
    name: str = typer.Option(..., "--name", "-n", help="Job name"),
    message: str = typer.Option(..., "--message", "-m", help="Message for agent"),
    every: int = typer.Option(None, "--every", "-e", help="Run every N seconds"),
    cron_expr: str = typer.Option(None, "--cron", "-c", help="Cron expression (e.g. '0 9 * * *')"),
    at: str = typer.Option(None, "--at", help="Run once at time (ISO format)"),
    deliver: bool = typer.Option(False, "--deliver", "-d", help="Deliver response to channel"),
    to: str = typer.Option(None, "--to", help="Recipient for delivery"),
    channel: str = typer.Option(None, "--channel", help="Channel for delivery (e.g. 'telegram', 'whatsapp')"),
):
    """Add a scheduled job."""
    from nanobot.config.loader import get_data_dir
    from nanobot.cron.service import CronService
    from nanobot.cron.types import CronSchedule
    
    # Determine schedule type
    if every:
        schedule = CronSchedule(kind="every", every_ms=every * 1000)
    elif cron_expr:
        schedule = CronSchedule(kind="cron", expr=cron_expr)
    elif at:
        import datetime
        dt = datetime.datetime.fromisoformat(at)
        schedule = CronSchedule(kind="at", at_ms=int(dt.timestamp() * 1000))
    else:
        console.print("[red]Error: Must specify --every, --cron, or --at[/red]")
        raise typer.Exit(1)
    
    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)
    
    job = service.add_job(
        name=name,
        schedule=schedule,
        message=message,
        deliver=deliver,
        to=to,
        channel=channel,
    )
    
    console.print(f"[green]✓[/green] Added job '{job.name}' ({job.id})")


@cron_app.command("remove")
def cron_remove(
    job_id: str = typer.Argument(..., help="Job ID to remove"),
):
    """Remove a scheduled job."""
    from nanobot.config.loader import get_data_dir
    from nanobot.cron.service import CronService
    
    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)
    
    if service.remove_job(job_id):
        console.print(f"[green]✓[/green] Removed job {job_id}")
    else:
        console.print(f"[red]Job {job_id} not found[/red]")


@cron_app.command("enable")
def cron_enable(
    job_id: str = typer.Argument(..., help="Job ID"),
    disable: bool = typer.Option(False, "--disable", help="Disable instead of enable"),
):
    """Enable or disable a job."""
    from nanobot.config.loader import get_data_dir
    from nanobot.cron.service import CronService
    
    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)
    
    job = service.enable_job(job_id, enabled=not disable)
    if job:
        status = "disabled" if disable else "enabled"
        console.print(f"[green]✓[/green] Job '{job.name}' {status}")
    else:
        console.print(f"[red]Job {job_id} not found[/red]")


@cron_app.command("run")
def cron_run(
    job_id: str = typer.Argument(..., help="Job ID to run"),
    force: bool = typer.Option(False, "--force", "-f", help="Run even if disabled"),
):
    """Manually run a job."""
    from nanobot.config.loader import get_data_dir
    from nanobot.cron.service import CronService
    
    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)
    
    async def run():
        return await service.run_job(job_id, force=force)
    
    if asyncio.run(run()):
        console.print(f"[green]✓[/green] Job executed")
    else:
        console.print(f"[red]Failed to run job {job_id}[/red]")


# ============================================================================
# Status Commands
# ============================================================================


@app.command()
def status():
    """Show nanobot status."""
    from nanobot.config.loader import load_config, get_config_path

    config_path = get_config_path()
    config = load_config()
    workspace = config.workspace_path

    console.print(f"{__logo__} nanobot Status\n")

    console.print(f"Config: {config_path} {'[green]✓[/green]' if config_path.exists() else '[red]✗[/red]'}")
    console.print(f"Workspace: {workspace} {'[green]✓[/green]' if workspace.exists() else '[red]✗[/red]'}")

    if config_path.exists():
        from nanobot.providers.registry import PROVIDERS

        console.print(f"Model: {config.agents.defaults.model}")
        
        # Check API keys from registry
        for spec in PROVIDERS:
            p = getattr(config.providers, spec.name, None)
            if p is None:
                continue
            if spec.is_local:
                # Local deployments show api_base instead of api_key
                if p.api_base:
                    console.print(f"{spec.label}: [green]✓ {p.api_base}[/green]")
                else:
                    console.print(f"{spec.label}: [dim]not set[/dim]")
            else:
                has_key = bool(p.api_key)
                console.print(f"{spec.label}: {'[green]✓[/green]' if has_key else '[dim]not set[/dim]'}")


if __name__ == "__main__":
    app()
