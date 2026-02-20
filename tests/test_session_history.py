"""Test get_history() preserves tool metadata for multi-turn tool conversations."""
from nanobot.session.manager import Session


def test_get_history_preserves_tool_metadata():
    """get_history() must preserve tool_calls, tool_call_id, name."""
    session = Session(key="test:tools")
    session.messages = [
        {"role": "user", "content": "search for X", "timestamp": "2026-01-01T00:00:00"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "web_search", "arguments": '{"q":"X"}'}}],
            "timestamp": "2026-01-01T00:00:01",
        },
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "name": "web_search",
            "content": "Results for X",
            "timestamp": "2026-01-01T00:00:02",
        },
        {"role": "assistant", "content": "Here are the results.", "timestamp": "2026-01-01T00:00:03"},
    ]
    history = session.get_history()
    # Assistant message with tool_calls
    assert "tool_calls" in history[1]
    assert history[1]["tool_calls"][0]["id"] == "call_1"
    # Tool result with tool_call_id and name
    assert history[2]["tool_call_id"] == "call_1"
    assert history[2]["name"] == "web_search"
    # Regular messages still work
    assert history[0] == {"role": "user", "content": "search for X"}
    assert history[3] == {"role": "assistant", "content": "Here are the results."}


def test_get_history_omits_absent_tool_fields():
    """Regular messages should NOT get empty tool_calls/tool_call_id/name fields."""
    session = Session(key="test:no_tools")
    session.messages = [
        {"role": "user", "content": "hello", "timestamp": "2026-01-01T00:00:00"},
        {"role": "assistant", "content": "hi", "timestamp": "2026-01-01T00:00:01"},
    ]
    history = session.get_history()
    assert history[0] == {"role": "user", "content": "hello"}
    assert history[1] == {"role": "assistant", "content": "hi"}
    assert "tool_calls" not in history[0]
    assert "tool_call_id" not in history[1]
