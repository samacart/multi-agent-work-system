"""Per-role tool permissions.

These were stored and never enforced: every role ran under one global tool
policy, so the profiles described a separation of powers that did not exist.
"""

from __future__ import annotations

import pytest

from app.agents.permissions import (
    ALWAYS_ALLOWED,
    CAPABILITY_TOOLS,
    ORCHESTRATOR_CAPABILITIES,
    can_write,
    denied_for,
    tool_flags_for,
    tools_for,
    unmapped_capabilities,
)
from app.agents.profiles import DEFAULT_AGENT_PROFILES


def _allowed(capabilities: list[str]) -> str:
    flags = tool_flags_for(capabilities)
    return flags[flags.index("--allowedTools") + 1]


def _denied(capabilities: list[str]) -> list[str]:
    return denied_for(capabilities)


def test_every_capability_a_default_profile_names_is_accounted_for():
    """A typo in a profile silently grants nothing, which an agent discovers by
    being unable to do its job. Catch it here instead."""
    for profile in DEFAULT_AGENT_PROFILES:
        unmapped = unmapped_capabilities(profile.allowed_tools)
        assert unmapped == set(), f"{profile.role} names unmapped capabilities: {unmapped}"


def test_reading_is_the_floor_not_a_privilege():
    """An agent that cannot read cannot do anything."""
    for tool in ALWAYS_ALLOWED:
        assert tool in tools_for([])
        assert tool in tools_for(["memory.search"])


def test_enforcement_is_by_denial_not_by_omission():
    """--allowedTools means "pre-approved", not "only these". A session handed
    an allow list still reached for Write and edited a file - verified against
    the real CLI. Only --disallowedTools refuses, so a role's permissions are
    expressed as the complement of what it was granted."""
    flags = tool_flags_for(["memory.search", "source.read", "artifact.write"])
    assert "--disallowedTools" in flags, "an allow list alone constrains nothing"


def test_a_read_only_role_is_denied_editing_and_the_shell():
    denied = _denied(["memory.search", "source.read", "artifact.write"])
    for forbidden in ("Edit", "Write", "MultiEdit", "NotebookEdit", "Bash"):
        assert forbidden in denied
    assert "Read" in _allowed(["source.read"])


def test_the_developer_is_denied_none_of_its_granted_capabilities():
    denied = _denied(["source.read", "repo.edit", "tests.run", "vcs.commit"])
    for granted in ("Edit", "Write", "Bash", "Bash(git commit:*)"):
        assert granted not in denied


def test_qa_can_write_and_run_but_not_commit():
    """A verifier that can only read cannot close a coverage gap it finds - but
    it has no business committing the work it is verifying."""
    qa = next(p for p in DEFAULT_AGENT_PROFILES if p.role == "qa")
    assert can_write(qa.allowed_tools)
    denied = _denied(qa.allowed_tools)
    assert "Edit" not in denied and "Bash" not in denied
    assert "Bash(git commit:*)" in denied


def test_a_role_granted_neither_tests_nor_commit_loses_the_shell_entirely():
    assert "Bash" in _denied(["source.read"])
    assert "Bash" not in _denied(["source.read", "tests.run"])


def test_only_the_roles_that_should_write_can():
    writers = {p.role for p in DEFAULT_AGENT_PROFILES if can_write(p.allowed_tools)}
    assert writers == {"developer", "qa"}


def test_only_the_roles_that_should_commit_can():
    committers = {p.role for p in DEFAULT_AGENT_PROFILES if "vcs.commit" in p.allowed_tools}
    assert committers == {"developer", "release_manager"}


def test_reviewers_cannot_change_what_they_review():
    for role in ("code_reviewer", "security_reviewer", "architect", "domain_expert", "lead_pm"):
        profile = next(p for p in DEFAULT_AGENT_PROFILES if p.role == role)
        assert not can_write(profile.allowed_tools), f"{role} can edit the repository"


def test_the_global_deny_list_applies_on_top_of_any_profile():
    """A profile grants; it never overrides. rm, sudo, curl, ssh and git push
    stay blocked for every role no matter what it claims."""
    for capabilities in ([], ["source.read", "repo.edit", "tests.run", "vcs.commit"]):
        denied = ",".join(_denied(capabilities))
        for blocked in ("rm", "sudo", "ssh", "git push"):
            assert blocked in denied


def test_the_global_deny_list_must_not_withhold_what_profiles_grant():
    """Naming Edit, Write or bare Bash globally would silently override every
    grant and leave the developer unable to work."""
    from app.config import get_settings

    globally_denied = {t.strip() for t in get_settings().claude_code_disallowed_tools.split(",")}
    assert not globally_denied & {"Edit", "Write", "MultiEdit", "NotebookEdit", "Bash"}


def test_an_unknown_capability_narrows_rather_than_crashes():
    """A typo should reduce what an agent can do, never fail its run."""
    tools = tools_for(["source.read", "definitely.not.a.capability"])
    assert "Read" in tools
    assert unmapped_capabilities(["definitely.not.a.capability"]) == {"definitely.not.a.capability"}


def test_orchestrator_capabilities_map_to_no_tool():
    """The orchestrator performs these; the agent never calls them."""
    for capability in ORCHESTRATOR_CAPABILITIES:
        assert capability not in CAPABILITY_TOOLS
        assert tools_for([capability]) == list(ALWAYS_ALLOWED)


@pytest.mark.parametrize("profile", DEFAULT_AGENT_PROFILES, ids=lambda p: p.role)
def test_every_profile_produces_usable_flags(profile):
    flags = tool_flags_for(profile.allowed_tools)
    assert flags[0] == "--allowedTools"
    assert flags[1], f"{profile.role} would be invoked with an empty allow list"
    assert "--disallowedTools" in flags, f"{profile.role} is constrained by nothing"
