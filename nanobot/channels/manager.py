"""Channel manager for coordinating chat channels."""

from __future__ import annotations

import asyncio
import ctypes
import os
import signal
import shutil
import subprocess
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.config.schema import Config


class ChannelManager:
    """
    Manages chat channels and coordinates message routing.

    Responsibilities:
    - Initialize enabled channels (Telegram, WhatsApp, etc.)
    - Start/stop channels
    - Route outbound messages
    - Auto-start the WhatsApp bridge when needed
    """

    def __init__(
        self,
        config: Config,
        bus: MessageBus,
        session_manager: "SessionManager | None" = None,
        voice_transcriber: Any = None,
    ):
        self.config = config
        self.bus = bus
        self.session_manager = session_manager
        self._voice_transcriber = voice_transcriber
        self.channels: dict[str, BaseChannel] = {}
        self._dispatch_task: asyncio.Task | None = None
        self._channel_tasks: dict[str, asyncio.Task] = {}
        self._restart_counts: dict[str, int] = {}
        self._max_restarts: int = 5
        self._supervisor_task: asyncio.Task | None = None
        self._bridge_process: subprocess.Popen | None = None

        self._init_channels()
    
    def _init_channels(self) -> None:
        """Initialize channels based on config."""
        
        # Telegram channel
        if self.config.channels.telegram.enabled:
            try:
                from nanobot.channels.telegram import TelegramChannel
                self.channels["telegram"] = TelegramChannel(
                    self.config.channels.telegram,
                    self.bus,
                    groq_api_key=self.config.providers.groq.api_key,
                )
                logger.info("Telegram channel enabled")
            except ImportError as e:
                logger.warning(f"Telegram channel not available: {e}")
        
        # WhatsApp channel
        if self.config.channels.whatsapp.enabled:
            try:
                from nanobot.channels.whatsapp import WhatsAppChannel
                self.channels["whatsapp"] = WhatsAppChannel(
                    self.config.channels.whatsapp, self.bus,
                    transcriber=self._voice_transcriber,
                )
                logger.info("WhatsApp channel enabled")
            except ImportError as e:
                logger.warning(f"WhatsApp channel not available: {e}")

        # Discord channel
        if self.config.channels.discord.enabled:
            try:
                from nanobot.channels.discord import DiscordChannel
                self.channels["discord"] = DiscordChannel(
                    self.config.channels.discord, self.bus
                )
                logger.info("Discord channel enabled")
            except ImportError as e:
                logger.warning(f"Discord channel not available: {e}")
        
        # Feishu channel
        if self.config.channels.feishu.enabled:
            try:
                from nanobot.channels.feishu import FeishuChannel
                self.channels["feishu"] = FeishuChannel(
                    self.config.channels.feishu, self.bus
                )
                logger.info("Feishu channel enabled")
            except ImportError as e:
                logger.warning(f"Feishu channel not available: {e}")

        # Mochat channel
        if self.config.channels.mochat.enabled:
            try:
                from nanobot.channels.mochat import MochatChannel

                self.channels["mochat"] = MochatChannel(
                    self.config.channels.mochat, self.bus
                )
                logger.info("Mochat channel enabled")
            except ImportError as e:
                logger.warning(f"Mochat channel not available: {e}")

        # DingTalk channel
        if self.config.channels.dingtalk.enabled:
            try:
                from nanobot.channels.dingtalk import DingTalkChannel
                self.channels["dingtalk"] = DingTalkChannel(
                    self.config.channels.dingtalk, self.bus
                )
                logger.info("DingTalk channel enabled")
            except ImportError as e:
                logger.warning(f"DingTalk channel not available: {e}")

        # Email channel
        if self.config.channels.email.enabled:
            try:
                from nanobot.channels.email import EmailChannel
                self.channels["email"] = EmailChannel(
                    self.config.channels.email, self.bus
                )
                logger.info("Email channel enabled")
            except ImportError as e:
                logger.warning(f"Email channel not available: {e}")

        # Slack channel
        if self.config.channels.slack.enabled:
            try:
                from nanobot.channels.slack import SlackChannel
                self.channels["slack"] = SlackChannel(
                    self.config.channels.slack, self.bus
                )
                logger.info("Slack channel enabled")
            except ImportError as e:
                logger.warning(f"Slack channel not available: {e}")

        # QQ channel
        if self.config.channels.qq.enabled:
            try:
                from nanobot.channels.qq import QQChannel
                self.channels["qq"] = QQChannel(
                    self.config.channels.qq,
                    self.bus,
                )
                logger.info("QQ channel enabled")
            except ImportError as e:
                logger.warning(f"QQ channel not available: {e}")
    
    async def _start_channel(self, name: str, channel: BaseChannel) -> None:
        """Start a channel and log any exceptions."""
        try:
            await channel.start()
        except Exception as e:
            logger.error(f"Failed to start channel {name}: {e}")
            from nanobot.copilot.alerting.bus import get_alert_bus
            await get_alert_bus().alert("channel", "high", f"Channel '{name}' failed to start: {e}", "start_failed")

    def _get_bridge_dir(self) -> Path | None:
        """Find the bridge directory, building if needed. Returns None on failure."""
        user_bridge = Path.home() / ".nanobot" / "bridge"

        # Already built?
        if (user_bridge / "dist" / "index.js").exists():
            return user_bridge

        if not shutil.which("npm"):
            logger.error("npm not found — cannot start WhatsApp bridge")
            return None

        # Locate source
        pkg_bridge = Path(__file__).parent.parent / "bridge"
        src_bridge = Path(__file__).parent.parent.parent / "bridge"
        source = None
        if (pkg_bridge / "package.json").exists():
            source = pkg_bridge
        elif (src_bridge / "package.json").exists():
            source = src_bridge

        if not source:
            logger.error("Bridge source not found")
            return None

        logger.info("Setting up WhatsApp bridge...")
        user_bridge.parent.mkdir(parents=True, exist_ok=True)
        if user_bridge.exists():
            shutil.rmtree(user_bridge)
        shutil.copytree(source, user_bridge, ignore=shutil.ignore_patterns("node_modules", "dist"))

        try:
            subprocess.run(["npm", "install"], cwd=user_bridge, check=True, capture_output=True)
            subprocess.run(["npm", "run", "build"], cwd=user_bridge, check=True, capture_output=True)
            logger.info("WhatsApp bridge built successfully")
        except subprocess.CalledProcessError as e:
            logger.error(f"Bridge build failed: {e}")
            return None

        return user_bridge

    @staticmethod
    def _kill_stale_bridge(port: int = 3001) -> None:
        """Kill any process occupying the bridge port (orphan from previous run)."""
        import re, time
        # Use `ss` to find PID listening on the bridge port
        try:
            result = subprocess.run(
                ["ss", "-tlnp", f"sport = :{port}"],
                capture_output=True, text=True, timeout=5,
            )
            # Parse output like: LISTEN 0 511 127.0.0.1:3001 ... users:(("node",pid=12345,fd=18))
            for match in re.finditer(r'pid=(\d+)', result.stdout):
                pid = int(match.group(1))
                logger.warning(f"Killing stale bridge on port {port} (pid {pid})")
                os.kill(pid, signal.SIGTERM)
                time.sleep(1)
                return
        except Exception:
            pass

    def _start_bridge(self) -> None:
        """Start the WhatsApp bridge subprocess."""
        bridge_dir = self._get_bridge_dir()
        if not bridge_dir:
            return

        # Kill any orphaned bridge from a previous crash
        self._kill_stale_bridge()

        env = {**os.environ}
        if self.config.channels.whatsapp.bridge_token:
            env["BRIDGE_TOKEN"] = self.config.channels.whatsapp.bridge_token

        def _child_setup():
            """Set process group and parent-death signal for bridge child."""
            # Put bridge in gateway's process group so _stop_bridge can kill it
            os.setpgid(0, 0)
            # Ask kernel to SIGTERM this child when parent dies
            try:
                PR_SET_PDEATHSIG = 1
                ctypes.CDLL("libc.so.6").prctl(PR_SET_PDEATHSIG, signal.SIGTERM)
            except Exception:
                pass

        logger.info("Starting WhatsApp bridge subprocess...")
        self._bridge_process = subprocess.Popen(
            ["node", "dist/index.js"],
            cwd=bridge_dir,
            env=env,
            preexec_fn=_child_setup,
        )
        logger.info(f"WhatsApp bridge started (pid {self._bridge_process.pid})")

    def _stop_bridge(self) -> None:
        """Stop the WhatsApp bridge subprocess and its entire process group."""
        if self._bridge_process and self._bridge_process.poll() is None:
            logger.info("Stopping WhatsApp bridge...")
            try:
                # Kill entire process group (bridge + any children)
                os.killpg(self._bridge_process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                self._bridge_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(self._bridge_process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            self._bridge_process = None

    async def start_all(self) -> None:
        """Start all channels with supervision."""
        if not self.channels:
            logger.warning("No channels enabled")
            return

        # Auto-start bridge if WhatsApp is enabled
        if "whatsapp" in self.channels and self._bridge_process is None:
            self._start_bridge()
            # Give the bridge a moment to start listening
            await asyncio.sleep(2)

        # Start outbound dispatcher
        self._dispatch_task = asyncio.create_task(self._dispatch_outbound())

        # Start channels as tracked tasks
        for name, channel in self.channels.items():
            logger.info(f"Starting {name} channel...")
            self._channel_tasks[name] = asyncio.create_task(
                self._start_channel(name, channel), name=f"channel:{name}"
            )
            self._restart_counts[name] = 0

        # Start supervisor
        self._supervisor_task = asyncio.create_task(self._supervise_channels())

        # Wait for all channel tasks (they should run forever)
        await asyncio.gather(
            *self._channel_tasks.values(),
            self._supervisor_task,
            return_exceptions=True,
        )
    
    async def _supervise_channels(self) -> None:
        """Monitor channel tasks and restart crashed ones with exponential backoff."""
        while True:
            await asyncio.sleep(15.0)
            for name, task in list(self._channel_tasks.items()):
                if task.done() and not task.cancelled():
                    exc = task.exception()
                    if exc:
                        logger.error(f"Channel '{name}' crashed: {exc}")
                        from nanobot.copilot.alerting.bus import get_alert_bus
                        await get_alert_bus().alert("channel", "high", f"Channel '{name}' crashed: {exc}", f"crash_{name}")

                    count = self._restart_counts.get(name, 0)
                    if count >= self._max_restarts:
                        logger.error(f"Channel '{name}' exceeded max restarts ({self._max_restarts})")
                        from nanobot.copilot.alerting.bus import get_alert_bus
                        await get_alert_bus().alert("channel", "high", f"Channel '{name}' exceeded max restarts ({self._max_restarts})", f"max_restart_{name}")
                        continue

                    self._restart_counts[name] = count + 1
                    backoff = min(2 ** count, 300)
                    logger.warning(
                        f"Channel '{name}' restarting in {backoff}s "
                        f"(attempt {count + 1}/{self._max_restarts})"
                    )
                    await asyncio.sleep(backoff)

                    channel = self.channels.get(name)
                    if channel:
                        self._channel_tasks[name] = asyncio.create_task(
                            self._start_channel(name, channel), name=f"channel:{name}"
                        )

    async def stop_all(self) -> None:
        """Stop all channels and the dispatcher."""
        logger.info("Stopping all channels...")
        
        # Stop dispatcher
        if self._dispatch_task:
            self._dispatch_task.cancel()
            try:
                await self._dispatch_task
            except asyncio.CancelledError:
                pass
        if self._supervisor_task:
            self._supervisor_task.cancel()
            try:
                await self._supervisor_task
            except asyncio.CancelledError:
                pass

        # Stop all channels
        for name, channel in self.channels.items():
            try:
                await channel.stop()
                logger.info(f"Stopped {name} channel")
            except Exception as e:
                logger.error(f"Error stopping {name}: {e}")

        # Stop bridge subprocess
        self._stop_bridge()
    
    async def _dispatch_outbound(self) -> None:
        """Dispatch outbound messages to the appropriate channel."""
        logger.info("Outbound dispatcher started")
        
        while True:
            try:
                msg = await asyncio.wait_for(
                    self.bus.consume_outbound(),
                    timeout=1.0
                )
                
                channel = self.channels.get(msg.channel)
                if channel:
                    try:
                        await channel.send(msg)
                    except Exception as e:
                        logger.error(f"Error sending to {msg.channel}: {e}")
                else:
                    logger.warning(f"Unknown channel: {msg.channel}")
                    
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
    
    def get_channel(self, name: str) -> BaseChannel | None:
        """Get a channel by name."""
        return self.channels.get(name)
    
    def get_status(self) -> dict[str, Any]:
        """Get status of all channels."""
        return {
            name: {
                "enabled": True,
                "running": channel.is_running
            }
            for name, channel in self.channels.items()
        }
    
    @property
    def enabled_channels(self) -> list[str]:
        """Get list of enabled channel names."""
        return list(self.channels.keys())
