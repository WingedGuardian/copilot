import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from nanobot.cli.commands import app

runner = CliRunner()


@pytest.fixture
def mock_paths():
    """Mock config/workspace paths for test isolation."""
    with patch("nanobot.config.loader.get_config_path") as mock_cp, \
         patch("nanobot.config.loader.save_config") as mock_sc, \
         patch("nanobot.config.loader.load_config"), \
         patch("nanobot.utils.helpers.get_workspace_path") as mock_ws:

        base_dir = Path("./test_onboard_data")
        if base_dir.exists():
            shutil.rmtree(base_dir)
        base_dir.mkdir()

        config_file = base_dir / "config.json"
        workspace_dir = base_dir / "workspace"

        mock_cp.return_value = config_file

        def _mock_get_workspace(**kwargs):
            workspace_dir.mkdir(parents=True, exist_ok=True)
            return workspace_dir

        mock_ws.side_effect = _mock_get_workspace
        mock_sc.side_effect = lambda config: config_file.write_text("{}")

        yield config_file, workspace_dir

        if base_dir.exists():
            shutil.rmtree(base_dir)


def test_onboard_fresh_install(mock_paths):
    """No existing config — should create from scratch."""
    config_file, workspace_dir = mock_paths

    result = runner.invoke(app, ["onboard"])

    assert result.exit_code == 0
    assert "Created config" in result.stdout
    assert "nanobot is ready" in result.stdout
    assert config_file.exists()
    assert (workspace_dir / "AGENTS.md").exists()
    assert (workspace_dir / "memory" / "MEMORY.md").exists()


def test_onboard_existing_config_refresh(mock_paths):
    """Config exists — should refresh by loading and re-saving (Pydantic fills defaults)."""
    config_file, workspace_dir = mock_paths
    config_file.write_text('{"existing": true}')

    result = runner.invoke(app, ["onboard"])

    assert result.exit_code == 0
    assert "Config refreshed" in result.stdout
    assert "existing values preserved" in result.stdout
    assert workspace_dir.exists()
    assert (workspace_dir / "AGENTS.md").exists()


def test_onboard_creates_workspace_templates(mock_paths):
    """Onboard should create AGENTS.md, SOUL.md, USER.md, and memory/MEMORY.md."""
    config_file, workspace_dir = mock_paths

    result = runner.invoke(app, ["onboard"])

    assert result.exit_code == 0
    assert (workspace_dir / "AGENTS.md").exists()
    assert (workspace_dir / "SOUL.md").exists()
    assert (workspace_dir / "USER.md").exists()
    assert (workspace_dir / "memory" / "MEMORY.md").exists()


def test_onboard_does_not_overwrite_existing_templates(mock_paths):
    """If a template file already exists, onboard should not overwrite it."""
    config_file, workspace_dir = mock_paths
    workspace_dir.mkdir(parents=True, exist_ok=True)
    custom_content = "# My Custom Agents"
    (workspace_dir / "AGENTS.md").write_text(custom_content)

    result = runner.invoke(app, ["onboard"])

    assert result.exit_code == 0
    assert (workspace_dir / "AGENTS.md").read_text() == custom_content
    assert "Created AGENTS.md" not in result.stdout
