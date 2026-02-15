"""Test that POLICY.md is loaded into the system prompt."""

from nanobot.copilot.context.extended import ExtendedContextBuilder
from nanobot.agent.context import ContextBuilder


def test_policy_md_loaded_into_identity_docs(tmp_path):
    """POLICY.md should be loaded alongside soul.md, user.md, agents.md."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "soul.md").write_text("I am a helpful bot.")
    (docs_dir / "policy.md").write_text("# Action Policy\n\n## Always Ask First\n- Do X")

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    base = ContextBuilder(workspace)
    ext = ExtendedContextBuilder(base)
    ext._docs_dir = docs_dir
    ext._identity_cache = ""

    result = ext._load_identity_docs()
    assert "Action Policy" in result
    assert "Always Ask First" in result


def test_policy_md_absent_no_error(tmp_path):
    """Missing POLICY.md should not cause errors."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "soul.md").write_text("I am a helpful bot.")

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    base = ContextBuilder(workspace)
    ext = ExtendedContextBuilder(base)
    ext._docs_dir = docs_dir
    ext._identity_cache = ""

    result = ext._load_identity_docs()
    assert "Action Policy" not in result
    assert "helpful bot" in result
