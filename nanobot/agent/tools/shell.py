"""Shell execution tool."""

import asyncio
import os
import re
import shlex
import signal
from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool

# Default commands allowed in allowlist mode
DEFAULT_ALLOWED_COMMANDS = [
    "ls", "cat", "grep", "find", "wc", "head", "tail",
    "python", "python3", "pip", "pip3",
    "gh", "sqlite3", "curl", "wget", "git",
    "diff", "patch", "sort", "uniq", "awk", "sed",
    "date", "echo", "printf", "test", "stat", "file",
    "jq", "bc", "tr", "cut", "tee", "mkdir", "cp", "mv", "touch",
    "chmod", "basename", "dirname", "realpath", "xargs",
    "tar", "gzip", "gunzip", "zip", "unzip",
]


class ExecTool(Tool):
    """Tool to execute shell commands."""

    def __init__(
        self,
        timeout: int = 60,
        working_dir: str | None = None,
        deny_patterns: list[str] | None = None,
        allow_patterns: list[str] | None = None,
        restrict_to_workspace: bool = False,
        mode: str = "allowlist",
        allowed_commands: list[str] | None = None,
        output_limit_bytes: int = 524_288,  # 512KB
    ):
        self.timeout = timeout
        self.working_dir = working_dir
        self.deny_patterns = deny_patterns or [
            r"\brm\s+-[rf]{1,2}\b",          # rm -r, rm -rf, rm -fr
            r"\bdel\s+/[fq]\b",              # del /f, del /q
            r"\brmdir\s+/s\b",               # rmdir /s
            r"\b(format|mkfs|diskpart)\b",   # disk operations
            r"\bdd\s+if=",                   # dd
            r">\s*/dev/sd",                  # write to disk
            r"\b(shutdown|reboot|poweroff)\b",  # system power
            r":\(\)\s*\{.*\};\s*:",          # fork bomb
        ]
        self.allow_patterns = allow_patterns or []
        self.restrict_to_workspace = restrict_to_workspace
        self.mode = mode
        self.allowed_commands = set(allowed_commands or DEFAULT_ALLOWED_COMMANDS)
        self.output_limit_bytes = output_limit_bytes

    @property
    def name(self) -> str:
        return "exec"

    @property
    def description(self) -> str:
        return "Execute a shell command and return its output. Use with caution."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute"
                },
                "working_dir": {
                    "type": "string",
                    "description": "Optional working directory for the command"
                }
            },
            "required": ["command"]
        }

    async def execute(self, command: str, working_dir: str | None = None, **kwargs: Any) -> str:
        cwd = working_dir or self.working_dir or os.getcwd()
        guard_error = self._guard_command(command, cwd)
        if guard_error:
            from nanobot.agent.tools.limiter import log_guardrail_block
            await log_guardrail_block("exec", "command_blocked", command[:80], guard_error[:80])
            return guard_error

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                start_new_session=True,  # Creates new process group
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    self._read_bounded(process),
                    timeout=self.timeout,
                )
            except asyncio.TimeoutError:
                self._kill_process_group(process)
                return f"Error: Command timed out after {self.timeout} seconds"

            output_parts = []

            if stdout_bytes:
                output_parts.append(stdout_bytes.decode("utf-8", errors="replace"))

            if stderr_bytes:
                stderr_text = stderr_bytes.decode("utf-8", errors="replace")
                if stderr_text.strip():
                    output_parts.append(f"STDERR:\n{stderr_text}")

            if process.returncode != 0:
                output_parts.append(f"\nExit code: {process.returncode}")

            result = "\n".join(output_parts) if output_parts else "(no output)"

            # Truncate very long output (char-level, after decode)
            max_len = 10000
            if len(result) > max_len:
                result = result[:max_len] + f"\n... (truncated, {len(result) - max_len} more chars)"

            return result

        except Exception as e:
            return f"Error executing command: {str(e)}"

    async def _read_bounded(self, process: asyncio.subprocess.Process) -> tuple[bytes, bytes]:
        """Read stdout/stderr with a hard byte cap. Keeps draining to avoid blocking the child."""
        limit = self.output_limit_bytes
        chunk_size = 8192
        stdout_buf = bytearray()
        stderr_buf = bytearray()

        async def _drain(stream: asyncio.StreamReader | None, buf: bytearray) -> None:
            if not stream:
                return
            while True:
                chunk = await stream.read(chunk_size)
                if not chunk:
                    break
                if len(buf) < limit:
                    buf.extend(chunk[: limit - len(buf)])
                # else: keep draining to prevent child blocking, but discard

        await asyncio.gather(
            _drain(process.stdout, stdout_buf),
            _drain(process.stderr, stderr_buf),
        )
        await process.wait()
        return bytes(stdout_buf), bytes(stderr_buf)

    @staticmethod
    def _kill_process_group(process: asyncio.subprocess.Process) -> None:
        """Kill the entire process group (shell + all children)."""
        try:
            pgid = os.getpgid(process.pid)
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            # Process already dead or no permission
            try:
                process.kill()
            except ProcessLookupError:
                pass

    # Patterns that reference sensitive files/dirs — block from shell
    _SECRETS_PATTERNS = [
        re.compile(r"secrets\.json", re.I),
        re.compile(r"whatsapp-auth", re.I),
        re.compile(r"\.ssh/", re.I),
        re.compile(r"\.gnupg/", re.I),
        re.compile(r"credentials\.json", re.I),
        re.compile(r"\.env\b", re.I),
        re.compile(r"\.pem\b", re.I),
        re.compile(r"\.key\b", re.I),
    ]

    def _guard_command(self, command: str, cwd: str) -> str | None:
        """Safety guard: allowlist mode checks executables, denylist mode checks patterns."""
        cmd = command.strip()
        lower = cmd.lower()

        # Block access to sensitive files (always active)
        for pattern in self._SECRETS_PATTERNS:
            if pattern.search(cmd):
                return "Error: Command blocked by safety guard (references protected file)"

        # Allowlist mode: extract base executables and check each
        if self.mode == "allowlist":
            error = self._check_allowlist(cmd)
            if error:
                return error
        else:
            # Legacy denylist mode
            for pattern in self.deny_patterns:
                if re.search(pattern, lower):
                    return "Error: Command blocked by safety guard (dangerous pattern detected)"

            if self.allow_patterns:
                if not any(re.search(p, lower) for p in self.allow_patterns):
                    return "Error: Command blocked by safety guard (not in allowlist)"

        if self.restrict_to_workspace:
            if "..\\" in cmd or "../" in cmd:
                return "Error: Command blocked by safety guard (path traversal detected)"

            cwd_path = Path(cwd).resolve()
            win_paths = re.findall(r"[A-Za-z]:\\[^\\\"']+", cmd)
            posix_paths = re.findall(r"(?:^|[\s|>])(/[^\s\"'>]+)", cmd)

            for raw in win_paths + posix_paths:
                try:
                    p = Path(raw.strip()).resolve()
                except Exception:
                    continue
                if p.is_absolute() and cwd_path not in p.parents and p != cwd_path:
                    return "Error: Command blocked by safety guard (path outside working dir)"

        return None

    def _check_allowlist(self, command: str) -> str | None:
        """Extract executables from a shell command and check against allowlist."""
        # Split on pipes and shell operators to get individual commands
        # Handle: cmd1 | cmd2, cmd1 && cmd2, cmd1 ; cmd2, cmd1 || cmd2
        segments = re.split(r"\s*(?:\|\||&&|[|;])\s*", command)

        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue

            # Strip leading env vars (FOO=bar cmd), redirections, subshell parens
            segment = re.sub(r"^\s*(?:\w+=\S+\s+)*", "", segment)
            segment = segment.lstrip("(").strip()
            if not segment:
                continue

            try:
                tokens = shlex.split(segment)
            except ValueError:
                # Malformed shell — fail closed
                return f"Error: Command blocked — could not parse: {segment[:60]}"

            if not tokens:
                continue

            executable = Path(tokens[0]).name  # handles /usr/bin/python -> python
            if executable not in self.allowed_commands:
                return f"Error: Command blocked — '{executable}' not in allowed commands"

        return None
