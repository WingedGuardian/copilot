"""Test that POLICY.md is loaded via BOOTSTRAP_FILES.

Identity docs (SOUL.md, USER.md, AGENTS.md, POLICY.md, CAPABILITIES.md)
are loaded by ContextBuilder.BOOTSTRAP_FILES.  ExtendedContextBuilder no
longer has a separate _load_identity_docs() method.
"""

from nanobot.agent.context import ContextBuilder


def test_policy_in_bootstrap_files():
    """POLICY.md should be in the bootstrap file list."""
    assert "POLICY.md" in ContextBuilder.BOOTSTRAP_FILES


def test_capabilities_merged_into_agents():
    """CAPABILITIES.md was merged into AGENTS.md — should NOT be in bootstrap."""
    assert "CAPABILITIES.md" not in ContextBuilder.BOOTSTRAP_FILES
    assert "AGENTS.md" in ContextBuilder.BOOTSTRAP_FILES


def test_bootstrap_files_loaded(tmp_path):
    """POLICY.md content appears in the system prompt when present."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "POLICY.md").write_text("# Action Policy\n\n## Always Ask First\n- Do X")

    base = ContextBuilder(workspace)
    messages = base.build_messages(
        history=[],
        current_message="hello",
    )
    system_content = messages[0]["content"]
    assert "Action Policy" in system_content
