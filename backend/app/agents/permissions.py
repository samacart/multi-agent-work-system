"""Turning a profile's stated capabilities into real ones.

Every agent profile carries `allowed_tools_json` describing what that role may
do. Until this module existed nothing read it: the runtime applied one global
tool policy to every role, so a Security Reviewer could edit the repository
exactly as freely as a Developer. Recorded permissions that nothing enforces are
worse than none, because they read as a guarantee.

The profiles speak an abstract vocabulary; Claude Code speaks tool names. This
is the one place that translates between them.

Enforcement is by DENY, not by allow. `--allowedTools` means "pre-approved
without prompting", not "only these": a session given an allow list can still
reach for anything absent from it, which was verified against the real CLI by
handing a read-only profile an allow list and watching it edit a file anyway.
Only `--disallowedTools` refuses. So a role's permissions are expressed as the
complement of what it was granted.
"""

from __future__ import annotations

from app.config import get_settings

# Capabilities an agent exercises through its own tools.
CAPABILITY_TOOLS: dict[str, tuple[str, ...]] = {
    "source.read": ("Read", "Glob", "Grep"),
    "repo.edit": ("Edit", "Write", "MultiEdit", "NotebookEdit"),
    "tests.run": (
        "Bash(pytest:*)",
        "Bash(npm:*)",
        "Bash(npx:*)",
        "Bash(make:*)",
        "Bash(uv:*)",
        "Bash(vitest:*)",
    ),
    "vcs.commit": (
        "Bash(git add:*)",
        "Bash(git commit:*)",
        "Bash(git status:*)",
        "Bash(git diff:*)",
        "Bash(git log:*)",
    ),
}

# Capabilities the orchestrator performs on the agent's behalf. An agent never
# calls these itself, so they map to no tool - listed explicitly so the absence
# reads as deliberate rather than as a gap in the mapping.
ORCHESTRATOR_CAPABILITIES: frozenset[str] = frozenset(
    {
        "memory.search",
        "artifact.write",
        "approval.request",
        "task.write",
        "decision.write",
    }
)

# An agent that cannot read cannot do anything. Read-only is the floor, not a
# privilege to be granted.
ALWAYS_ALLOWED: tuple[str, ...] = ("Read", "Glob", "Grep")

# Tools that must be denied when the capability behind them was not granted.
# Anything not listed here cannot be withheld, so a capability guarding nothing
# is a capability that does not actually constrain.
WITHHELD_WITHOUT: dict[str, tuple[str, ...]] = {
    "repo.edit": ("Edit", "Write", "MultiEdit", "NotebookEdit"),
    # Bash is all-or-nothing: withheld entirely from a role granted neither
    # tests.run nor vcs.commit.
    "shell": ("Bash",),
    # A role that may run tests but not commit still must not reach git.
    "vcs.commit": ("Bash(git add:*)", "Bash(git commit:*)"),
}


def tools_for(allowed_capabilities: list[str] | None) -> list[str]:
    """The concrete tool names a role may use, in a stable order."""
    tools: list[str] = list(ALWAYS_ALLOWED)
    for capability in allowed_capabilities or []:
        # Unknown capabilities are ignored rather than fatal: a typo in a
        # profile should narrow what an agent can do, never crash its run.
        for tool in CAPABILITY_TOOLS.get(str(capability), ()):
            if tool not in tools:
                tools.append(tool)
    return tools


def denied_for(allowed_capabilities: list[str] | None) -> list[str]:
    """Tools withheld from a role: everything it was not granted.

    The global deny list is folded in last, so `rm`, `sudo`, `curl`, `wget`,
    `ssh` and `git push` stay blocked for every role no matter what its profile
    claims. A profile grants; it never overrides.
    """
    granted = {str(c) for c in (allowed_capabilities or [])}
    denied: list[str] = []

    if "repo.edit" not in granted:
        denied.extend(WITHHELD_WITHOUT["repo.edit"])

    if not granted & {"tests.run", "vcs.commit"}:
        denied.extend(WITHHELD_WITHOUT["shell"])
    elif "vcs.commit" not in granted:
        denied.extend(WITHHELD_WITHOUT["vcs.commit"])

    for tool in get_settings().claude_code_disallowed_tools.split(","):
        tool = tool.strip()
        if tool and tool not in denied:
            denied.append(tool)
    return denied


def tool_flags_for(allowed_capabilities: list[str] | None) -> list[str]:
    """Claude Code flags for a role.

    The allow list documents intent and pre-approves; the deny list is what
    actually constrains.
    """
    flags = ["--allowedTools", ",".join(tools_for(allowed_capabilities))]
    denied = denied_for(allowed_capabilities)
    if denied:
        flags += ["--disallowedTools", ",".join(denied)]
    return flags


def can_write(allowed_capabilities: list[str] | None) -> bool:
    """Whether a role may change the workspace. Used for reporting, not gating."""
    return "repo.edit" in set(allowed_capabilities or [])


def unmapped_capabilities(allowed_capabilities: list[str] | None) -> set[str]:
    """Capabilities that are neither tool-backed nor orchestrator-side.

    A profile naming something this returns is a typo or an unimplemented
    capability; either way it grants nothing and should be caught by a test
    rather than discovered by an agent that cannot do its job.
    """
    named = {str(c) for c in (allowed_capabilities or [])}
    return named - set(CAPABILITY_TOOLS) - ORCHESTRATOR_CAPABILITIES
