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

from app.config import get_settings
from app.paths import PathNotAllowed, resolve_within

log = logging.getLogger(__name__)

GIT_TIMEOUT_SECONDS = 60

# A branch an agent is expected to work on. Anything else is a working tree
# someone may be using, which is worth warning about rather than refusing.
AGENT_BRANCH_PREFIX = "agents/"


@dataclass
class WorkspaceValidation:
    """Whether a workspace may be used, and what state it is in."""

    path: str
    valid: bool = False
    reason: str | None = None
    resolved_path: str | None = None
    branch: str | None = None
    dirty_files: int = 0
    is_agent_branch: bool = False
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "valid": self.valid,
            "reason": self.reason,
            "resolved_path": self.resolved_path,
            "branch": self.branch,
            "dirty_files": self.dirty_files,
            "is_agent_branch": self.is_agent_branch,
            "warnings": self.warnings,
        }


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
    omitted_files: list[str] = field(default_factory=list)

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
            **({"files_not_shown": self.omitted_files} if self.omitted_files else {}),
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


def workspace_for(project) -> str | None:  # noqa: ANN001 - Project, avoiding a circular import
    """The repository this project's agents work in.

    A project's own workspace wins; the global CLAUDE_CODE_CWD is a fallback for
    projects that have not set one, not an override. Two projects targeting two
    repositories is the point.
    """
    return getattr(project, "workspace_path", None) or (get_settings().claude_code_cwd or None)


async def validate_workspace(
    raw_path: str | None, enforce_roots: bool = True
) -> WorkspaceValidation:
    """Whether agents may run in `raw_path`, and what state it is in.

    A workspace becomes an agent's working directory with shell access, so a
    path supplied through the API is constrained to ALLOWED_WORKSPACE_ROOTS
    rather than trusted. Resolution is on the fully resolved path, so `..` and a
    symlink escaping the root are both refused.

    `enforce_roots=False` is for the global CLAUDE_CODE_CWD fallback only. That
    value is set by whoever runs the server, in the same file as the database
    credentials - it is already a deliberate act by someone who could edit the
    roots anyway, and holding it to a list it predates would break every
    existing deployment. It still has to exist and be a git repository.
    """
    result = WorkspaceValidation(path=raw_path or "")

    if enforce_roots:
        try:
            path = resolve_within(raw_path or "", get_settings().allowed_workspace_root_list, what="workspace")
        except PathNotAllowed as exc:
            result.reason = str(exc)
            return result
    else:
        path = Path(raw_path or "").expanduser().resolve(strict=False)
        if not raw_path or not path.exists():
            result.reason = f"Path does not exist: {raw_path}"
            return result

    if not path.is_dir():
        result.reason = f"Not a directory: {path}"
        return result

    result.resolved_path = str(path)

    code, _ = await _git(path, "rev-parse", "--is-inside-work-tree")
    if code != 0:
        result.reason = f"Not a git repository: {path}"
        return result

    _code, branch = await _git(path, "rev-parse", "--abbrev-ref", "HEAD")
    result.branch = branch.strip() or None
    result.is_agent_branch = bool(result.branch and result.branch.startswith(AGENT_BRANCH_PREFIX))

    _code, status = await _git(path, "status", "--porcelain")
    result.dirty_files = len([line for line in status.splitlines() if line.strip()])

    # Valid but worth saying out loud: agents write here.
    if not result.is_agent_branch:
        result.warnings.append(
            f"Branch {result.branch!r} is not an {AGENT_BRANCH_PREFIX} branch - agent changes "
            "would land on a tree you may be using"
        )
    if result.dirty_files:
        result.warnings.append(
            f"{result.dirty_files} uncommitted change(s) already present; agent work will mix with them"
        )

    result.valid = True
    return result


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
    for index, name in enumerate(result.new_files):
        if budget <= 0:
            result.truncated = True
            # Name what the reviewer did not see, not merely that something was cut.
            result.omitted_files.extend(result.new_files[index:])
            break
        file_path = path / name
        try:
            if not file_path.is_file() or file_path.stat().st_size > budget:
                result.truncated = True
                result.omitted_files.append(name)
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
