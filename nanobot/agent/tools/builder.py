"""ToolBuilderTool — lets the agent create new tools at runtime."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, TYPE_CHECKING

from loguru import logger

from nanobot.agent.tools.base import Tool
from nanobot.agent.tools.dynamic import DynamicTool, validate_code

if TYPE_CHECKING:
    from nanobot.agent.tools.registry import ToolRegistry

# Tool names must be lowercase alphanumeric + underscores, 3-40 chars.
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,39}$")


class ToolBuilderTool(Tool):
    """Agent-callable tool that creates new dynamic tools at runtime.

    The agent provides: name, description, JSON schema for parameters,
    and Python code.  The code is validated (syntax + import allowlist)
    before being registered and persisted.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        tools_dir: Path | str | None = None,
    ):
        self._registry = registry
        self._tools_dir = Path(tools_dir) if tools_dir else None
        if self._tools_dir:
            self._tools_dir.mkdir(parents=True, exist_ok=True)

    @property
    def name(self) -> str:
        return "tool_builder"

    @property
    def description(self) -> str:
        return (
            "Create a new tool at runtime. Provide a name, description, "
            "JSON schema for parameters, and Python code. The code should "
            "set a variable named 'result' with the output string. "
            "Only allowlisted imports are permitted (json, re, math, datetime, "
            "urllib, hashlib, base64, collections, itertools, functools, "
            "string, textwrap). Parameters are available as local variables."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Tool name (lowercase, 3-40 chars, letters/digits/underscores).",
                },
                "description": {
                    "type": "string",
                    "description": "What the tool does.",
                },
                "parameters": {
                    "type": "string",
                    "description": "JSON string of the tool's parameter schema.",
                },
                "code": {
                    "type": "string",
                    "description": "Python code. Set 'result' variable for output.",
                },
            },
            "required": ["name", "description", "parameters", "code"],
        }

    async def execute(self, **kwargs: Any) -> str:
        tool_name = kwargs.get("name", "")
        tool_desc = kwargs.get("description", "")
        params_json = kwargs.get("parameters", "{}")
        code = kwargs.get("code", "")

        # Validate name
        if not _NAME_RE.match(tool_name):
            return (
                f"Error: Invalid tool name '{tool_name}'. "
                "Must be 3-40 lowercase chars (letters, digits, underscores), "
                "starting with a letter."
            )

        # Parse parameters JSON
        try:
            tool_params = json.loads(params_json)
        except json.JSONDecodeError as e:
            return f"Error: Invalid parameters JSON: {e}"

        # Validate code
        errors = validate_code(code)
        if errors:
            return "Error: Code validation failed:\n" + "\n".join(f"  - {e}" for e in errors)

        # Create and register
        dynamic_tool = DynamicTool(
            tool_name=tool_name,
            tool_description=tool_desc,
            tool_parameters=tool_params,
            code=code,
        )
        self._registry.register(dynamic_tool)

        # Persist to disk
        if self._tools_dir:
            self._persist(dynamic_tool)

        logger.info(f"Dynamic tool created: {tool_name}")
        return f"Tool '{tool_name}' created and registered successfully."

    def _persist(self, tool: DynamicTool) -> None:
        """Save tool definition to disk as JSON."""
        path = self._tools_dir / f"{tool.name}.json"
        path.write_text(json.dumps(tool.to_dict(), indent=2))

    def load_persisted_tools(self) -> int:
        """Load all persisted tool definitions from disk.

        Returns the number of tools loaded.
        """
        if not self._tools_dir or not self._tools_dir.exists():
            return 0

        count = 0
        for path in self._tools_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text())
                errors = validate_code(data.get("code", ""))
                if errors:
                    logger.warning(f"Skipping invalid tool {path.name}: {errors}")
                    continue

                tool = DynamicTool(
                    tool_name=data["name"],
                    tool_description=data.get("description", ""),
                    tool_parameters=data.get("parameters", {}),
                    code=data["code"],
                )
                self._registry.register(tool)
                count += 1
                logger.info(f"Loaded persisted tool: {data['name']}")
            except Exception as e:
                logger.warning(f"Failed to load tool from {path.name}: {e}")

        return count
