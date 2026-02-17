"""Tests for /help command response builder."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock


class TestBuildHelpResponse:
    """Test _build_help_response helper."""

    def test_no_topic_returns_commands(self):
        """Default /help shows commands list."""
        from nanobot.agent.loop import _build_help_response
        result = _build_help_response(topic=None, copilot_config=None, session_meta={}, help_md_dir=None)
        assert "/new" in result
        assert "/status" in result
        assert "/tasks" in result
        assert "/help" in result

    def test_no_topic_shows_available_topics(self):
        """Default /help lists available drill-down topics."""
        from nanobot.agent.loop import _build_help_response
        result = _build_help_response(topic=None, copilot_config=None, session_meta={}, help_md_dir=None)
        assert "routing" in result.lower()
        assert "policy" in result.lower()

    def test_known_topic_returns_section(self, tmp_path):
        """Known topic returns matching section from help.md."""
        help_md = tmp_path / "help.md"
        help_md.write_text("# Help\n\n## routing\n\nRouting details here.\n\n## policy\n\nPolicy details here.\n")

        from nanobot.agent.loop import _build_help_response
        result = _build_help_response(topic="routing", copilot_config=None, session_meta={}, help_md_dir=str(tmp_path))
        assert "Routing details here" in result
        assert "Policy details" not in result

    def test_unknown_topic_lists_available(self, tmp_path):
        """Unknown topic shows error with available topics."""
        help_md = tmp_path / "help.md"
        help_md.write_text("# Help\n\n## routing\n\nDetails.\n\n## policy\n\nDetails.\n")

        from nanobot.agent.loop import _build_help_response
        result = _build_help_response(topic="banana", copilot_config=None, session_meta={}, help_md_dir=str(tmp_path))
        assert "not found" in result.lower()
        assert "routing" in result
        assert "policy" in result

    def test_missing_help_md_fallback(self):
        """Missing help.md falls back gracefully."""
        from nanobot.agent.loop import _build_help_response
        result = _build_help_response(topic="routing", copilot_config=None, session_meta={}, help_md_dir="/nonexistent")
        assert "not found" in result.lower()

    def test_dynamic_tips_with_copilot(self):
        """When copilot config present, tips are generated."""
        from nanobot.agent.loop import _build_help_response
        config = MagicMock()
        config.dream_cron_expr = "0 7 * * *"
        config.heartbeat_interval = 7200
        config.copilot_docs_dir = "/nonexistent"

        result = _build_help_response(topic=None, copilot_config=config, session_meta={}, help_md_dir=None)
        assert "/status" in result
        assert "7 * * *" in result

    def test_active_override_shows_warning(self):
        """Active /use override shows in tips."""
        from nanobot.agent.loop import _build_help_response
        config = MagicMock()
        config.copilot_docs_dir = "/nonexistent"
        config.dream_cron_expr = "0 7 * * *"
        config.heartbeat_interval = 7200

        meta = {"force_provider": "venice", "force_tier": "big"}
        result = _build_help_response(topic=None, copilot_config=config, session_meta=meta, help_md_dir=None)
        assert "venice" in result.lower()


class TestLoadHelpSection:
    """Test _load_help_section helper."""

    def test_extracts_section(self, tmp_path):
        """Extracts a specific section by topic name."""
        help_md = tmp_path / "help.md"
        help_md.write_text("# Help\n\n## alpha\n\nAlpha content.\n\n## beta\n\nBeta content.\n")

        from nanobot.agent.loop import _load_help_section
        result = _load_help_section("alpha", str(tmp_path))
        assert result == "Alpha content."

    def test_returns_none_for_missing_topic(self, tmp_path):
        """Returns None when topic doesn't exist."""
        help_md = tmp_path / "help.md"
        help_md.write_text("# Help\n\n## alpha\n\nContent.\n")

        from nanobot.agent.loop import _load_help_section
        result = _load_help_section("missing", str(tmp_path))
        assert result is None

    def test_returns_none_for_missing_file(self):
        """Returns None when help.md doesn't exist."""
        from nanobot.agent.loop import _load_help_section
        result = _load_help_section("alpha", "/nonexistent")
        assert result is None

    def test_returns_none_for_no_dir(self):
        """Returns None when docs_dir is None."""
        from nanobot.agent.loop import _load_help_section
        result = _load_help_section("alpha", None)
        assert result is None


class TestListHelpTopics:
    """Test _list_help_topics helper."""

    def test_lists_topics(self, tmp_path):
        """Lists all ## headers from help.md."""
        help_md = tmp_path / "help.md"
        help_md.write_text("# Help\n\n## routing\n\nContent.\n\n## policy\n\nContent.\n\n## memory\n\nContent.\n")

        from nanobot.agent.loop import _list_help_topics
        result = _list_help_topics(str(tmp_path))
        assert result == ["routing", "policy", "memory"]

    def test_empty_for_missing_file(self):
        """Returns empty list when file is missing."""
        from nanobot.agent.loop import _list_help_topics
        result = _list_help_topics("/nonexistent")
        assert result == []
