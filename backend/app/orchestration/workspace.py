"""Reading what the agents actually changed.

Review and verification passes need the diff, not a description of it. Without
this a code review is an opinion about the plan, not about the work - which is
exactly what happened on the first real run: reviewers reported findings derived
from topic memory while nine thousand lines of new code sat unread beside them.

Reads only. Nothing here mutates the workspace, including its index: untracked
files are listed and read directly rather than staged with --intent-to-add,
because a review has no business changing the thing it is reviewing.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

GIT_TIMEOUT_SECONDS = 60


@dataclass
class WorkspaceDiff:
    path: str
    base: str
    available: bool = False
    reason: str | None = None
    stat: str = ""
    changed_files: list[str] = field(default_factory=list)
    new_files: list[str] = field(default_factory=list)
    patch: str = ""
    truncated: bool = False

    @property
    def is_empty(self) -> bool:
        return not self.changed_files and not self.new_files

    def as_context(self) -> dict[str, object]:
        """The shape a runtime sees. Lists render as bullets, strings as facts."""
        if not self.available:
            return {"diff_status": f"No workspace diff available: {self.reason}"}
        if self.is_empty:
            return {"diff_status": f"No changes in {self.path} against {self.base}"}
        return {
            "diff_status": f"{len(self.changed_files)} modified, {len(self.new_files)} new file(s) "
            f"in {self.path} against {self.base}"
            + (" (patch truncated)" if self.truncated else ""),
            "changed_files": self.changed_files,
            "new_files": self.new_files,
            "diff_stat": self.stat,
            "diff": self.patch,
        }


async def _git(path: Path, *args: str) -> tuple[int, str]:
    process = await asyncio.create_subprocess_exec(
        "git",
        "-C",
        str(path),
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, _stderr = await asyncio.wait_for(process.communicate(), timeout=GIT_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        return 1, ""
    return process.returncode or 0, (stdout or b"").decode("utf-8", errors="replace")


async def read_workspace_diff(
    workspace: str | None, base: str = "HEAD", max_chars: int = 60_000
) -> WorkspaceDiff:
    """Everything changed in `workspace` relative to `base`, within a budget."""
    if not workspace:
        return WorkspaceDiff(path="", base=base, reason="no workspace configured (CLAUDE_CODE_CWD)")

    path = Path(workspace).expanduser()
    result = WorkspaceDiff(path=str(path), base=base)

    if not path.is_dir():
        result.reason = f"workspace does not exist: {path}"
        return result

    code, _ = await _git(path, "rev-parse", "--is-inside-work-tree")
    if code != 0:
        result.reason = f"not a git repository: {path}"
        return result

    result.available = True

    _code, stat = await _git(path, "diff", base, "--stat")
    result.stat = stat.strip()

    _code, names = await _git(path, "diff", base, "--name-only")
    result.changed_files = [n for n in names.splitlines() if n.strip()]

    _code, untracked = await _git(path, "ls-files", "--others", "--exclude-standard")
    result.new_files = [n for n in untracked.splitlines() if n.strip()]

    _code, patch = await _git(path, "diff", base)
    budget = max_chars

    if len(patch) > budget:
        patch = patch[:budget]
        result.truncated = True
    budget -= len(patch)
    parts = [patch] if patch else []

    # New files are where most of the new code lives, and `git diff` cannot see
    # them without staging - which would mutate the workspace.
    for name in result.new_files:
        if budget <= 0:
            result.truncated = True
            break
        file_path = path / name
        try:
            if not file_path.is_file() or file_path.stat().st_size > budget:
                result.truncated = True
                continue
            body = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        block = f"\n--- new file: {name} ---\n{body}\n"
        parts.append(block[:budget])
        budget -= len(block)

    result.patch = "".join(parts)
    log.info(
        "workspace diff for %s: %d modified, %d new, %d chars%s",
        path,
        len(result.changed_files),
        len(result.new_files),
        len(result.patch),
        " (truncated)" if result.truncated else "",
    )
    return result
