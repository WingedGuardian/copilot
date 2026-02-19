"""Phase 4 tests: Message UX (ack, coalescing, queue notification)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# 4A. Processing Acknowledgment
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ack_delay_attribute():
    """AgentLoop should have ack delay config."""
    from nanobot.agent.loop import AgentLoop
    from nanobot.bus.queue import MessageBus

    bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "m"
    loop = AgentLoop(bus=bus, provider=provider, workspace=Path("/tmp"))
    assert hasattr(loop, '_ack_delay')


# ---------------------------------------------------------------------------
# 4B. Message Coalescing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_message_coalescing_attributes():
    """AgentLoop should have coalescing config."""
    from nanobot.agent.loop import AgentLoop
    from nanobot.bus.queue import MessageBus

    bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "m"
    loop = AgentLoop(bus=bus, provider=provider, workspace=Path("/tmp"))
    assert hasattr(loop, '_coalesce_window')
    assert loop._coalesce_window == 0.5


# ---------------------------------------------------------------------------
# 4C. Queue Notification
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_queue_notification_attributes():
    """AgentLoop should track processing sessions for notification."""
    from nanobot.agent.loop import AgentLoop
    from nanobot.bus.queue import MessageBus

    bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "m"
    loop = AgentLoop(bus=bus, provider=provider, workspace=Path("/tmp"))
    assert hasattr(loop, '_processing_sessions')
    assert hasattr(loop, '_notified_sessions')
    assert isinstance(loop._processing_sessions, dict)
    assert isinstance(loop._notified_sessions, set)
