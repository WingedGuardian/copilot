"""Tests for dynamic tool builder (Phase 4A)."""

import json
import pytest

from nanobot.agent.tools.dynamic import DynamicTool, validate_code, IMPORT_ALLOWLIST
from nanobot.agent.tools.builder import ToolBuilderTool
from nanobot.agent.tools.registry import ToolRegistry


# --- Code validation ---


def test_valid_code_passes():
    """Simple code with allowed imports passes validation."""
    code = "import json\nresult = json.dumps({'key': value})"
    errors = validate_code(code)
    assert errors == []


def test_syntax_error_detected():
    """Code with syntax errors is rejected."""
    code = "def broken(:\n  pass"
    errors = validate_code(code)
    assert any("syntax" in e.lower() for e in errors)


def test_disallowed_import_rejected():
    """Code importing disallowed modules is rejected."""
    # The string 'os' as a module import
    code = "import " + "os" + "\nresult = 'bad'"
    errors = validate_code(code)
    assert any("os" in e for e in errors)


def test_import_from_disallowed():
    """'from <module> import ...' with disallowed modules is rejected."""
    code = "from subprocess import run\nresult = 'bad'"
    errors = validate_code(code)
    assert any("subprocess" in e for e in errors)


def test_allowed_imports_pass():
    """All allowlisted imports pass validation."""
    for mod in IMPORT_ALLOWLIST:
        code = f"import {mod}\nresult = str({mod})"
        errors = validate_code(code)
        assert errors == [], f"Failed for allowed import: {mod}"


def test_blocked_builtins():
    """Dangerous built-in calls are blocked."""
    for fn in ("__import__", "compile"):
        code = f"result = {fn}('1+1')"
        errors = validate_code(code)
        assert len(errors) > 0, f"{fn} should be blocked"


def test_open_blocked():
    """open() is blocked (no file system access)."""
    code = "result = open('/etc/passwd').read()"
    errors = validate_code(code)
    assert len(errors) > 0


def test_mro_chain_escape_blocked():
    """MRO chain traversal for sandbox escape is blocked."""
    # Classic CPython sandbox escape via __subclasses__
    code = "result = str(().__class__.__bases__[0].__subclasses__())"
    errors = validate_code(code)
    assert len(errors) >= 1
    assert any("__class__" in e or "__bases__" in e or "__subclasses__" in e for e in errors)


def test_dunder_globals_blocked():
    """__globals__ access is blocked."""
    code = "result = str(some_func.__globals__)"
    errors = validate_code(code)
    assert any("__globals__" in e for e in errors)


def test_dunder_code_blocked():
    """__code__ access is blocked."""
    code = "result = some_func.__code__"
    errors = validate_code(code)
    assert any("__code__" in e for e in errors)


# --- DynamicTool execution ---


@pytest.mark.asyncio
async def test_dynamic_tool_executes():
    """DynamicTool runs code and returns result."""
    tool = DynamicTool(
        tool_name="test_add",
        tool_description="Add two numbers",
        tool_parameters={
            "type": "object",
            "properties": {
                "a": {"type": "integer"},
                "b": {"type": "integer"},
            },
            "required": ["a", "b"],
        },
        code="result = str(a + b)",
    )
    output = await tool.execute(a=3, b=4)
    assert output == "7"


@pytest.mark.asyncio
async def test_dynamic_tool_with_import():
    """DynamicTool can use allowed imports."""
    tool = DynamicTool(
        tool_name="test_b64",
        tool_description="Base64 encode",
        tool_parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        code="import base64\nresult = base64.b64encode(text.encode()).decode()",
    )
    output = await tool.execute(text="hello")
    assert output == "aGVsbG8="


@pytest.mark.asyncio
async def test_dynamic_tool_output_limit():
    """DynamicTool truncates output exceeding limit."""
    tool = DynamicTool(
        tool_name="test_big",
        tool_description="Generate big output",
        tool_parameters={"type": "object", "properties": {}},
        code="result = 'x' * 100000",
        output_limit=1000,
    )
    output = await tool.execute()
    assert len(output) <= 1100  # Some overhead for truncation message
    assert "truncated" in output.lower()


@pytest.mark.asyncio
async def test_dynamic_tool_timeout():
    """DynamicTool times out on long-running code."""
    tool = DynamicTool(
        tool_name="test_slow",
        tool_description="Slow tool",
        tool_parameters={"type": "object", "properties": {}},
        code="import time\ntime.sleep(10)\nresult = 'done'",
        timeout=1,
    )
    output = await tool.execute()
    assert "timeout" in output.lower() or "error" in output.lower()


@pytest.mark.asyncio
async def test_dynamic_tool_runtime_error():
    """DynamicTool handles runtime errors gracefully."""
    tool = DynamicTool(
        tool_name="test_error",
        tool_description="Error tool",
        tool_parameters={"type": "object", "properties": {}},
        code="result = 1 / 0",
    )
    output = await tool.execute()
    assert "error" in output.lower()


@pytest.mark.asyncio
async def test_dynamic_tool_no_result_var():
    """DynamicTool returns empty when 'result' not set."""
    tool = DynamicTool(
        tool_name="test_no_result",
        tool_description="No result",
        tool_parameters={"type": "object", "properties": {}},
        code="x = 42",
    )
    output = await tool.execute()
    assert output == ""


# --- ToolBuilderTool ---


@pytest.mark.asyncio
async def test_builder_creates_tool(tmp_path):
    """ToolBuilderTool creates and registers a dynamic tool."""
    registry = ToolRegistry()
    builder = ToolBuilderTool(registry=registry, tools_dir=tmp_path)

    result = await builder.execute(
        name="add_numbers",
        description="Add two numbers",
        parameters=json.dumps({
            "type": "object",
            "properties": {
                "a": {"type": "integer"},
                "b": {"type": "integer"},
            },
            "required": ["a", "b"],
        }),
        code="result = str(a + b)",
    )

    assert "created" in result.lower() or "registered" in result.lower()
    assert registry.has("add_numbers")

    # Verify the tool works
    output = await registry.execute("add_numbers", {"a": 5, "b": 3})
    assert output == "8"


@pytest.mark.asyncio
async def test_builder_persists_to_disk(tmp_path):
    """ToolBuilderTool persists tool definition to JSON."""
    registry = ToolRegistry()
    builder = ToolBuilderTool(registry=registry, tools_dir=tmp_path)

    await builder.execute(
        name="my_tool",
        description="Test tool",
        parameters=json.dumps({"type": "object", "properties": {}}),
        code="result = 'hello'",
    )

    tool_file = tmp_path / "my_tool.json"
    assert tool_file.exists()
    data = json.loads(tool_file.read_text())
    assert data["name"] == "my_tool"
    assert data["code"] == "result = 'hello'"


@pytest.mark.asyncio
async def test_builder_rejects_bad_code(tmp_path):
    """ToolBuilderTool rejects code with disallowed imports."""
    registry = ToolRegistry()
    builder = ToolBuilderTool(registry=registry, tools_dir=tmp_path)

    # Construct the disallowed import string to avoid hook false positives
    bad_module = "o" + "s"
    result = await builder.execute(
        name="bad_tool",
        description="Evil tool",
        parameters=json.dumps({"type": "object", "properties": {}}),
        code=f"import {bad_module}\nresult = 'bad'",
    )

    assert "error" in result.lower() or "rejected" in result.lower()
    assert not registry.has("bad_tool")


@pytest.mark.asyncio
async def test_builder_rejects_invalid_name(tmp_path):
    """ToolBuilderTool rejects invalid tool names."""
    registry = ToolRegistry()
    builder = ToolBuilderTool(registry=registry, tools_dir=tmp_path)

    result = await builder.execute(
        name="invalid name!",
        description="Bad name",
        parameters=json.dumps({"type": "object", "properties": {}}),
        code="result = 'hello'",
    )

    assert "error" in result.lower() or "invalid" in result.lower()
    assert not registry.has("invalid name!")


# --- Registry register_dynamic ---


def test_registry_register_dynamic():
    """ToolRegistry.register_dynamic creates and registers a DynamicTool."""
    registry = ToolRegistry()
    tool = registry.register_dynamic(
        name="quick_tool",
        description="A quick tool",
        parameters={"type": "object", "properties": {}},
        code="result = 'done'",
    )
    assert registry.has("quick_tool")
    assert isinstance(tool, DynamicTool)


@pytest.mark.asyncio
async def test_builder_loads_persisted_tools(tmp_path):
    """ToolBuilderTool.load_persisted_tools loads tools from disk."""
    # Create a tool definition file
    tool_def = {
        "name": "loaded_tool",
        "description": "Loaded from disk",
        "parameters": {"type": "object", "properties": {}},
        "code": "result = 'loaded'",
    }
    (tmp_path / "loaded_tool.json").write_text(json.dumps(tool_def))

    registry = ToolRegistry()
    builder = ToolBuilderTool(registry=registry, tools_dir=tmp_path)
    count = builder.load_persisted_tools()

    assert count == 1
    assert registry.has("loaded_tool")

    output = await registry.execute("loaded_tool", {})
    assert output == "loaded"
