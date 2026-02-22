"""Test empty content handling in add_assistant_message."""
import tempfile
from pathlib import Path

from nanobot.agent.context import ContextBuilder


def test_add_assistant_message_omits_empty_content():
    """When content is None, the 'content' key should be omitted to prevent API errors."""
    with tempfile.TemporaryDirectory() as td:
        ctx = ContextBuilder(Path(td))
        messages = []
        result = ctx.add_assistant_message(
            messages,
            content=None,
            tool_calls=[{"id": "call_1", "type": "function", "function": {"name": "test", "arguments": "{}"}}],
        )
        msg = result[0]
        assert "content" not in msg
        assert msg["tool_calls"][0]["id"] == "call_1"


def test_add_assistant_message_keeps_nonempty_content():
    """When content has actual text, it should be preserved."""
    with tempfile.TemporaryDirectory() as td:
        ctx = ContextBuilder(Path(td))
        messages = []
        result = ctx.add_assistant_message(messages, content="Hello world")
        msg = result[0]
        assert msg["content"] == "Hello world"


def test_add_assistant_message_omits_empty_string_content():
    """Empty string should also be omitted."""
    with tempfile.TemporaryDirectory() as td:
        ctx = ContextBuilder(Path(td))
        messages = []
        result = ctx.add_assistant_message(messages, content="")
        msg = result[0]
        assert "content" not in msg
