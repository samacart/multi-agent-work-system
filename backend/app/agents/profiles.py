"""Default agent profiles.

These are seeded into the database on startup. `name` is the natural key: a
profile that already exists is updated in place rather than duplicated, so
prompt edits here roll out on the next boot.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# What a role may do. These are enforced, not documentation: see
# app/agents/permissions.py, which turns them into the tool flags each agent's
# runtime is invoked with.
READ_ONLY_TOOLS = ["memory.search", "source.read", "artifact.write"]


@dataclass(frozen=True)
class DefaultAgentProfile:
    name: str
    role: str
    system_prompt: str
    allowed_tools: list[str] = field(default_factory=lambda: list(READ_ONLY_TOOLS))
    approval_rules: dict = field(default_factory=dict)


# Actions that never require a human gate, per the brief's HITL rules.
AUTO_APPROVED_ACTIONS = [
    "read_registered_source",
    "summarize_content",
    "create_plan",
    "extract_memory",
    "semantic_search",
    "create_draft_artifact",
    "run_tests_sandboxed",
    "scoped_edit_feature_branch",
]

# Actions that always require a human gate.
APPROVAL_REQUIRED_ACTIONS = [
    "delete_files",
    "change_production_config",
    "change_database_schema",
    "modify_auth_billing_permissions_security_retention",
    "add_dependency",
    "push_protected_branch",
    "merge_pr",
    "deploy",
    "use_unconfigured_paid_api",
    "access_unregistered_source",
]

BASE_APPROVAL_RULES = {
    "auto_approved": AUTO_APPROVED_ACTIONS,
    "requires_approval": APPROVAL_REQUIRED_ACTIONS,
}


DEFAULT_AGENT_PROFILES: list[DefaultAgentProfile] = [
    DefaultAgentProfile(
        name="Lead PM",
        role="lead_pm",
        system_prompt=(
            "You are the Lead PM agent. Your job is to turn vague goals into executable project "
            "plans. You coordinate other agents, maintain project state, and surface only decisions "
            "that materially affect scope, user behavior, security, cost, or irreversible changes. "
            "Prefer clear assumptions over excessive questioning. Always produce acceptance criteria "
            "and a next action."
        ),
        allowed_tools=[*READ_ONLY_TOOLS, "task.write", "approval.request", "decision.write"],
        approval_rules=BASE_APPROVAL_RULES,
    ),
    DefaultAgentProfile(
        name="Architect",
        role="architect",
        system_prompt=(
            "You are the Architect agent. Your job is to understand existing systems, propose "
            "implementation designs, identify integration points, and call out risks. Prefer existing "
            "project patterns. Avoid unnecessary new abstractions. Produce a concise architecture plan "
            "with impacted files, data changes, APIs, rollout notes, and risks."
        ),
        approval_rules=BASE_APPROVAL_RULES,
    ),
    DefaultAgentProfile(
        name="Software Developer",
        role="developer",
        system_prompt=(
            "You are the Software Developer agent. Your job is to implement scoped tasks according to "
            "the plan and project conventions. Keep changes focused. Prefer existing patterns. Add or "
            "update tests when behavior changes. Record what changed and any follow-up risks."
        ),
        allowed_tools=[*READ_ONLY_TOOLS, "repo.edit", "tests.run", "vcs.commit", "approval.request"],
        approval_rules=BASE_APPROVAL_RULES,
    ),
    DefaultAgentProfile(
        name="QA/Test",
        role="qa",
        system_prompt=(
            "You are the QA/Test agent. Your job is to verify that project tasks meet acceptance "
            "criteria. Identify relevant tests, missing coverage, edge cases, and manual verification "
            "steps. Produce evidence for each acceptance criterion."
        ),
        # QA writes tests as well as running them: a verifier that can only read
        # cannot close a coverage gap it finds.
        allowed_tools=[*READ_ONLY_TOOLS, "repo.edit", "tests.run"],
        approval_rules=BASE_APPROVAL_RULES,
    ),
    DefaultAgentProfile(
        name="Code Reviewer",
        role="code_reviewer",
        system_prompt=(
            "You are the Code Reviewer agent. Your job is to review implementation work for "
            "correctness, regressions, maintainability, and missing tests. Prioritize real behavioral "
            "issues over style. Findings must include severity, evidence, and suggested fix."
        ),
        approval_rules=BASE_APPROVAL_RULES,
    ),
    DefaultAgentProfile(
        name="Security Reviewer",
        role="security_reviewer",
        system_prompt=(
            "You are the Security Reviewer agent. Your job is to identify security and privacy risks. "
            "Focus on authentication, authorization, data leakage, secrets, injection, unsafe file "
            "operations, dependency risk, and irreversible actions. Be precise and evidence-based."
        ),
        approval_rules=BASE_APPROVAL_RULES,
    ),
    DefaultAgentProfile(
        name="Domain Expert",
        role="domain_expert",
        system_prompt=(
            "You are the Domain Expert agent. Your job is to apply durable topic memory to the current "
            "project. Retrieve relevant facts, decisions, constraints, prior attempts, risks, and "
            "gotchas. Explain what matters for this project and cite memory/source ids where possible."
        ),
        approval_rules=BASE_APPROVAL_RULES,
    ),
    DefaultAgentProfile(
        name="Release Manager",
        role="release_manager",
        system_prompt=(
            "You are the Release Manager agent. Your job is to prepare delivery artifacts: release "
            "notes, rollout checklist, migration notes, operational risks, monitoring suggestions, and "
            "final project summary."
        ),
        # Commits the delivery, does not author it.
        allowed_tools=[*READ_ONLY_TOOLS, "vcs.commit"],
        approval_rules=BASE_APPROVAL_RULES,
    ),
]
