"""Git operations tool via gitpython."""

from __future__ import annotations

import asyncio
import functools
from typing import Any

from loguru import logger

from nanobot.agent.tools.base import Tool


class GitTool(Tool):
    """Tool for Git repository operations."""

    def __init__(
        self,
        default_repo: str | None = None,
        allow_clone: bool = False,
        max_clone_size_mb: int = 50,
        clone_timeout: int = 120,
    ):
        self._default_repo = default_repo
        self._allow_clone = allow_clone
        self._max_clone_size_mb = max_clone_size_mb
        self._clone_timeout = clone_timeout

    @property
    def name(self) -> str:
        return "git"

    @property
    def description(self) -> str:
        return (
            "Perform Git operations on a repository. "
            "Actions: status, log, diff, add, commit, push, pull, branch, checkout, stash, clone."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "status", "log", "diff", "add", "commit",
                        "push", "pull", "branch", "checkout", "stash", "clone",
                    ],
                    "description": "Git action to perform",
                },
                "args": {
                    "type": "string",
                    "description": "Additional arguments (e.g. file paths, branch name, commit message)",
                },
                "repo_path": {
                    "type": "string",
                    "description": "Repository path (optional, defaults to workspace)",
                },
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "status")
        args = kwargs.get("args", "")
        repo_path = kwargs.get("repo_path", self._default_repo or ".")

        try:
            import git
            repo = git.Repo(repo_path)
        except Exception as e:
            return f"Error opening repository at {repo_path}: {e}"

        try:
            if action == "status":
                return self._status(repo)
            elif action == "log":
                return self._log(repo, args)
            elif action == "diff":
                return self._diff(repo, args)
            elif action == "add":
                return self._add(repo, args)
            elif action == "commit":
                return self._commit(repo, args)
            elif action == "push":
                return self._push(repo, args)
            elif action == "pull":
                return self._pull(repo, args)
            elif action == "branch":
                return self._branch(repo, args)
            elif action == "checkout":
                return self._checkout(repo, args)
            elif action == "stash":
                return self._stash(repo, args)
            elif action == "clone":
                return await self._clone_safe(args, repo_path)
            else:
                return f"Unknown git action: {action}"
        except Exception as e:
            return f"Git error: {e}"

    @staticmethod
    def _status(repo) -> str:
        lines = []
        lines.append(f"Branch: {repo.active_branch.name}")
        if repo.is_dirty():
            lines.append("Working tree: dirty")
        else:
            lines.append("Working tree: clean")

        # Changed files
        changed = [item.a_path for item in repo.index.diff(None)]
        if changed:
            lines.append(f"Modified: {', '.join(changed[:20])}")

        # Staged files
        staged = [item.a_path for item in repo.index.diff("HEAD")]
        if staged:
            lines.append(f"Staged: {', '.join(staged[:20])}")

        # Untracked
        untracked = repo.untracked_files
        if untracked:
            lines.append(f"Untracked: {', '.join(untracked[:20])}")

        return "\n".join(lines)

    @staticmethod
    def _log(repo, args: str) -> str:
        count = 10
        if args and args.strip().isdigit():
            count = int(args.strip())
        commits = list(repo.iter_commits(max_count=count))
        lines = []
        for c in commits:
            date = c.committed_datetime.strftime("%Y-%m-%d %H:%M")
            lines.append(f"{c.hexsha[:7]} {date} {c.summary}")
        return "\n".join(lines) if lines else "No commits found."

    @staticmethod
    def _diff(repo, args: str) -> str:
        if args.strip():
            diff = repo.git.diff(args.strip())
        else:
            diff = repo.git.diff()
        if not diff:
            diff = repo.git.diff("--cached")
        if len(diff) > 5000:
            diff = diff[:5000] + "\n... (truncated)"
        return diff or "No changes."

    @staticmethod
    def _add(repo, args: str) -> str:
        files = args.strip().split() if args.strip() else ["."]
        repo.index.add(files)
        return f"Added: {', '.join(files)}"

    @staticmethod
    def _commit(repo, args: str) -> str:
        message = args.strip() or "Auto-commit by copilot"
        commit = repo.index.commit(message)
        return f"Committed: {commit.hexsha[:7]} {message}"

    @staticmethod
    def _push(repo, args: str) -> str:
        remote_name = args.strip() or "origin"
        remote = repo.remote(remote_name)
        info = remote.push()
        results = [str(i.summary) for i in info]
        return f"Pushed to {remote_name}: {'; '.join(results)}"

    @staticmethod
    def _pull(repo, args: str) -> str:
        remote_name = args.strip() or "origin"
        remote = repo.remote(remote_name)
        info = remote.pull()
        results = [str(i.note) for i in info]
        return f"Pulled from {remote_name}: {'; '.join(results)}"

    @staticmethod
    def _branch(repo, args: str) -> str:
        if args.strip():
            # Create new branch
            new_branch = repo.create_head(args.strip())
            return f"Created branch: {new_branch.name}"
        else:
            branches = [b.name for b in repo.branches]
            active = repo.active_branch.name
            lines = [f"{'* ' if b == active else '  '}{b}" for b in branches]
            return "\n".join(lines)

    @staticmethod
    def _checkout(repo, args: str) -> str:
        branch_name = args.strip()
        if not branch_name:
            return "Error: branch name required"
        repo.git.checkout(branch_name)
        return f"Checked out: {branch_name}"

    @staticmethod
    def _stash(repo, args: str) -> str:
        subcmd = args.strip() or "push"
        if subcmd == "push" or subcmd == "save":
            repo.git.stash("push")
            return "Stashed changes."
        elif subcmd == "pop":
            repo.git.stash("pop")
            return "Popped stash."
        elif subcmd == "list":
            return repo.git.stash("list") or "No stashes."
        else:
            return f"Unknown stash command: {subcmd}"

    async def _clone_safe(self, url: str, dest: str) -> str:
        """Clone with size pre-check, async execution, timeout, and shallow default."""
        url = url.strip()
        if not url:
            return "Error: URL required for clone"

        if not self._allow_clone:
            return "Error: git clone is disabled. Enable allow_clone in config."

        # Size pre-check for GitHub repos
        size_error = await self._check_repo_size(url)
        if size_error:
            return size_error

        # Run blocking clone in executor with timeout
        import git

        loop = asyncio.get_event_loop()
        clone_fn = functools.partial(
            git.Repo.clone_from, url, dest, depth=1,  # shallow clone by default
        )
        try:
            await asyncio.wait_for(
                loop.run_in_executor(None, clone_fn),
                timeout=self._clone_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(f"git clone timed out after {self._clone_timeout}s: {url}")
            return f"Error: git clone timed out after {self._clone_timeout}s"

        return f"Cloned {url} to {dest} (shallow, depth=1)"

    async def _check_repo_size(self, url: str) -> str | None:
        """Check GitHub repo size before cloning. Returns error string or None."""
        import re

        m = re.match(r"https?://github\.com/([^/]+)/([^/.]+)", url)
        if not m:
            return None  # Non-GitHub — can't pre-check, allow with timeout protection

        owner, repo = m.group(1), m.group(2)
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(f"https://api.github.com/repos/{owner}/{repo}")
                if r.status_code == 200:
                    size_kb = r.json().get("size", 0)
                    size_mb = size_kb / 1024
                    if size_mb > self._max_clone_size_mb:
                        return (
                            f"Error: Repository is {size_mb:.0f}MB, "
                            f"exceeds {self._max_clone_size_mb}MB limit"
                        )
        except Exception as e:
            logger.debug(f"GitHub size check failed (allowing clone): {e}")

        return None
