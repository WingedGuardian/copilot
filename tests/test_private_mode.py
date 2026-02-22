"""Tests for private mode (session-level local-only routing)."""


from nanobot.session.manager import Session, SessionManager


def test_detect_private_mode_on():
    """Detect 'private mode' activation phrases."""
    cases = [
        "private mode",
        "keep this local",
        "go private",
        "local only please",
    ]
    for text in cases:
        result = SessionManager.detect_private_mode_command(text)
        assert result == "on", f"Failed for: {text}"


def test_detect_private_mode_off():
    """Detect 'end private mode' deactivation phrases."""
    cases = [
        "end private mode",
        "back to normal",
        "normal mode",
        "stop private mode",
    ]
    for text in cases:
        result = SessionManager.detect_private_mode_command(text)
        assert result == "off", f"Failed for: {text}"


def test_detect_private_mode_extend():
    """Detect 'stay private' extension phrases."""
    result = SessionManager.detect_private_mode_command("stay private")
    assert result == "extend"


def test_detect_no_command():
    """Normal messages don't trigger private mode."""
    result = SessionManager.detect_private_mode_command("how's the weather?")
    assert result is None


def test_session_activate_private():
    """Session activates private mode correctly."""
    session = Session(key="test")
    assert session.private_mode is False

    session.activate_private_mode()
    assert session.private_mode is True
    assert session.private_mode_since > 0


def test_session_deactivate_private():
    """Session deactivates private mode correctly."""
    session = Session(key="test")
    session.activate_private_mode()
    assert session.private_mode is True

    session.deactivate_private_mode()
    assert session.private_mode is False


def test_private_mode_never_persists_across_sessions():
    """New sessions start in normal mode (private mode is session-level only)."""
    session = Session(key="test")
    # Even if metadata somehow had private_mode from a prior session,
    # new Session() starts with empty metadata
    assert session.private_mode is False


def test_session_touch_activity():
    """touch_activity updates the last message timestamp."""
    session = Session(key="test")
    session.touch_activity()
    assert session.last_user_message_at > 0


def test_off_takes_priority_over_on():
    """'end private mode' overrides 'private mode' if both match."""
    # "end private mode" contains both "private mode" and "end private mode"
    # Off patterns should be checked first
    result = SessionManager.detect_private_mode_command("end private mode")
    assert result == "off"
