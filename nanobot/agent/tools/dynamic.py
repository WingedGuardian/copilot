"""DynamicTool — sandboxed execution wrapper for runtime-created tools."""

from __future__ import annotations

import ast
import asyncio
import concurrent.futures
from typing import Any

from loguru import logger

from nanobot.agent.tools.base import Tool

# Modules that dynamic tool code is allowed to import.
IMPORT_ALLOWLIST = frozenset({
    "json", "re", "math", "datetime", "urllib",
    "hashlib", "base64", "collections", "itertools",
    "functools", "string", "textwrap",
})

# Built-in names that are blocked in dynamic code.
_BLOCKED_BUILTINS = frozenset({
    "__import__", "compile", "open", "breakpoint",
    "globals", "locals", "vars", "dir", "getattr", "setattr", "delattr",
    "input", "print",  # print is useless in tool context; input blocks
})

# Dunder attributes that enable sandbox escape via MRO chain traversal.
# e.g. ().__class__.__bases__[0].__subclasses__() can reach os._wrap_close
_BLOCKED_DUNDER_ATTRS = frozenset({
    "__class__", "__bases__", "__subclasses__", "__mro__",
    "__globals__", "__code__", "__builtins__", "__import__",
    "__loader__", "__spec__", "__qualname__", "__func__",
    "__self__", "__wrapped__", "__closure__",
})

# Default execution timeout (seconds) and output limit (bytes).
_DEFAULT_TIMEOUT = 30
_DEFAULT_OUTPUT_LIMIT = 50_000  # 50 KB


def validate_code(code: str) -> list[str]:
    """Validate dynamic tool code for safety.

    Checks:
    - Syntax correctness
    - Only allowlisted imports
    - No blocked built-in calls

    Returns list of error strings (empty if valid).
    """
    errors: list[str] = []

    # 1. Syntax check
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"Syntax error at line {e.lineno}: {e.msg}"]

    # 2. Walk AST to check imports and dangerous calls
    for node in ast.walk(tree):
        # Check import statements
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name.split(".")[0]
                if module not in IMPORT_ALLOWLIST:
                    errors.append(f"Import not allowed: {module}")

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                module = node.module.split(".")[0]
                if module not in IMPORT_ALLOWLIST:
                    errors.append(f"Import not allowed: {module}")

        # Check for blocked built-in calls
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in _BLOCKED_BUILTINS:
                errors.append(f"Blocked built-in: {func.id}()")
            elif isinstance(func, ast.Attribute) and func.attr in _BLOCKED_BUILTINS:
                errors.append(f"Blocked call: .{func.attr}()")

        # Check for dunder attribute access (MRO chain sandbox escape)
        elif isinstance(node, ast.Attribute):
            if node.attr in _BLOCKED_DUNDER_ATTRS:
                errors.append(f"Blocked attribute: .{node.attr}")

    return errors


def _build_safe_globals() -> dict[str, Any]:
    """Build a restricted globals dict for code execution."""
    safe: dict[str, Any] = {"__builtins__": {}}

    # Allow safe builtins
    import builtins
    allowed = {
        "True", "False", "None",
        "abs", "all", "any", "bin", "bool", "bytes", "chr",
        "dict", "divmod", "enumerate", "filter", "float",
        "format", "frozenset", "hex", "int", "isinstance",
        "issubclass", "iter", "len", "list", "map", "max",
        "min", "next", "oct", "ord", "pow", "range", "repr",
        "reversed", "round", "set", "slice", "sorted", "str",
        "sum", "tuple", "zip",
    }
    for name in allowed:
        if hasattr(builtins, name):
            safe["__builtins__"][name] = getattr(builtins, name)

    # Allow __import__ only for allowlisted modules
    real_import = builtins.__import__

    def _safe_import(name: str, *args: Any, **kwargs: Any) -> Any:
        module_root = name.split(".")[0]
        if module_root not in IMPORT_ALLOWLIST:
            raise ImportError(f"Import not allowed: {name}")
        return real_import(name, *args, **kwargs)

    safe["__builtins__"]["__import__"] = _safe_import

    return safe


def _run_in_sandbox(code: str, params: dict[str, Any], timeout: int) -> str:
    """Run code in a sandboxed environment (called from a thread).

    The code should set a variable named ``result`` to produce output.
    Uses restricted globals and a safe import function.
    """
    safe_globals = _build_safe_globals()
    local_ns: dict[str, Any] = dict(params)

    try:
        compiled = compile(code, "<dynamic_tool>", "exec")  # noqa: S102
        # Intentional sandboxed execution with restricted builtins
        _sandbox_exec(compiled, safe_globals, local_ns)
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"

    return str(local_ns.get("result", ""))


def _sandbox_exec(
    compiled: Any, safe_globals: dict[str, Any], local_ns: dict[str, Any]
) -> None:
    """Execute compiled code in the sandbox. Separated for clarity."""
    # This uses Python's exec() intentionally — code is validated via
    # validate_code() before reaching here, and globals are restricted
    # to a safe subset with allowlisted imports only.
    exec(compiled, safe_globals, local_ns)  # noqa: S102


class DynamicTool(Tool):
    """A tool created at runtime with user-provided code.

    Code runs in a restricted sandbox:
    - Only allowlisted imports
    - No file system access
    - No shell access
    - Timeout enforcement
    - Output size limit
    """

    def __init__(
        self,
        tool_name: str,
        tool_description: str,
        tool_parameters: dict[str, Any],
        code: str,
        *,
        timeout: int = _DEFAULT_TIMEOUT,
        output_limit: int = _DEFAULT_OUTPUT_LIMIT,
    ):
        self._name = tool_name
        self._description = tool_description
        self._parameters = tool_parameters
        self._code = code
        self._timeout = timeout
        self._output_limit = output_limit

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._parameters

    @property
    def code(self) -> str:
        return self._code

    async def execute(self, **kwargs: Any) -> str:
        """Execute the dynamic tool code with the given parameters."""
        loop = asyncio.get_event_loop()
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    executor, _run_in_sandbox, self._code, kwargs, self._timeout
                ),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(f"Dynamic tool '{self._name}' timed out after {self._timeout}s")
            return f"Error: Tool execution timed out after {self._timeout} seconds"
        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"
        finally:
            executor.shutdown(wait=False)

        # Enforce output limit
        if len(result) > self._output_limit:
            truncated = result[: self._output_limit]
            result = truncated + f"\n\n[Output truncated at {self._output_limit} bytes]"

        return result

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict for persistence."""
        return {
            "name": self._name,
            "description": self._description,
            "parameters": self._parameters,
            "code": self._code,
        }
