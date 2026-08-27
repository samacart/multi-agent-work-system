"""Deterministic rule-based runtime.

This is scaffolding, not reasoning. It composes structurally valid outputs from
the project's real inputs - the goal, and the memories actually retrieved for
it - using fixed templates. That is enough to make the whole pipeline work,
be tested, and be inspected offline, and it is what makes every later phase
provider-agnostic. Swap AGENT_RUNTIME to a model-backed runtime for judgement.

Every output is a pure function of its input, so tests can assert on it.
"""

from __future__ import annotations

from typing import Any

from app.agents.runtime.base import AgentContext, AgentProfileLike, AgentRunResult, AgentRuntime

# Memory types that map onto specific parts of a plan.
_RISKY = {"risk", "gotcha"}
_CONSTRAINING = {"constraint", "decision"}


def _memories(context: AgentContext, *types: str) -> list[dict[str, Any]]:
    wanted = set(types)
    return [m for m in context.memories if not wanted or m.get("type") in wanted]


def _contents(context: AgentContext, *types: str, limit: int = 8) -> list[str]:
    return [str(m.get("content", "")).strip() for m in _memories(context, *types)][:limit]


def _goal(context: AgentContext) -> str:
    return str(context.extra.get("goal") or context.extra.get("project_name") or "the project")


def _project_name(context: AgentContext) -> str:
    return str(context.extra.get("project_name") or "this project")


def _topic_name(context: AgentContext) -> str:
    return str(context.extra.get("topic_name") or "no topic")


def _mentions(context: AgentContext, *words: str) -> bool:
    haystack = " ".join(
        [_goal(context), _project_name(context), *[str(m.get("content", "")) for m in context.memories]]
    ).lower()
    return any(word in haystack for word in words)


def _domain_context(context: AgentContext) -> dict[str, Any]:
    cited = [str(m["id"]) for m in context.memories if m.get("id")]
    return {
        "summary": (
            f"{len(context.memories)} memories from topic '{_topic_name(context)}' are relevant to "
            f"{_project_name(context)}."
        ),
        "key_facts": _contents(context, "fact"),
        "constraints": _contents(context, "constraint"),
        "prior_attempts": _contents(context, "lesson"),
        "gotchas": _contents(context, "gotcha"),
        "terminology": _contents(context, "definition"),
        "open_questions": _contents(context, "open_question"),
        "cited_memory_ids": cited[:50],
    }


def _severity(memory: dict[str, Any]) -> str:
    importance = float(memory.get("importance") or 0.5)
    if importance >= 0.8:
        return "high"
    if importance >= 0.6:
        return "medium"
    return "low"


def _project_brief(context: AgentContext) -> dict[str, Any]:
    goal = _goal(context)
    risks = [
        {"description": m["content"], "severity": _severity(m), "mitigation": None}
        for m in _memories(context, *_RISKY)[:8]
    ]
    return {
        "summary": (
            f"{_project_name(context)}: {goal}. Planned from {len(context.memories)} memories in topic "
            f"'{_topic_name(context)}'."
        ),
        "goals": [goal],
        "non_goals": [
            "Anything not required to satisfy the stated goal",
            "Migrating adjacent systems that are merely nearby",
        ],
        # Decisions and constraints already recorded are treated as given, and
        # listed so a human can contradict them cheaply.
        "assumptions": [f"Still true: {c}" for c in _contents(context, *_CONSTRAINING, limit=6)]
        or ["No recorded decisions or constraints; scope is assumed to be greenfield"],
        "unknowns": _contents(context, "open_question", limit=6) or ["No open questions recorded in topic memory"],
        "risks": risks,
        "success_criteria": [
            f"The stated goal is demonstrably met: {goal}",
            "Every task has acceptance criteria with evidence attached",
            "No unresolved high-severity review or security finding",
        ],
    }


def _architecture_plan(context: AgentContext) -> dict[str, Any]:
    impacted = _contents(context, "architecture", "system", limit=8)
    data_changes: list[str] = []
    if _mentions(context, "schema", "migration", "table", "column", "database"):
        data_changes.append("Schema change implied by topic memory - needs a migration and an approval gate")
    return {
        "approach": (
            f"Follow existing patterns in the systems named by topic memory; keep {_project_name(context)} "
            "scoped to the smallest change that satisfies the goal."
        ),
        "impacted_areas": impacted or ["Unknown - no architecture memories recorded for this topic"],
        "data_changes": data_changes,
        "apis": [c for c in impacted if "api" in c.lower()][:5],
        "rollout_notes": [
            "Ship behind a feature flag where the change is user-visible",
            "Land the migration before the code that depends on it",
        ]
        if data_changes
        else ["No data changes identified; a standard rollout applies"],
        "risks": [
            {"description": m["content"], "severity": _severity(m), "mitigation": None}
            for m in _memories(context, *_RISKY)[:5]
        ],
    }


# The SDLC spine. Every project gets these; risk- and data-specific tasks are
# appended when topic memory justifies them.
_BASE_TASKS = [
    (
        "Confirm scope and open questions",
        "lead_pm",
        "Resolve or explicitly assume every unknown in the brief before implementation starts.",
        ["Every unknown is answered or recorded as a stated assumption", "Scope boundaries are written down"],
        [],
    ),
    (
        "Apply topic memory to the plan",
        "domain_expert",
        "Surface prior attempts, gotchas, and constraints that change how this should be built.",
        ["Relevant prior attempts are cited with memory ids", "Constraints that affect the design are listed"],
        ["Confirm scope and open questions"],
    ),
    (
        "Design the technical approach",
        "architect",
        "Produce an implementation design naming impacted files, data changes, APIs, and rollout steps.",
        ["Impacted areas are named", "Data changes are identified", "Rollout and rollback are described"],
        ["Apply topic memory to the plan"],
    ),
    (
        "Implement the change",
        "developer",
        "Implement the design in a feature branch, following existing repository conventions.",
        ["Change is scoped to the design", "Tests are added or updated where behaviour changed"],
        ["Design the technical approach"],
    ),
    (
        "Verify against acceptance criteria",
        "qa",
        "Verify every acceptance criterion and attach evidence; identify missing coverage.",
        ["Every acceptance criterion has evidence", "Missing coverage is listed"],
        ["Implement the change"],
    ),
    (
        "Review the implementation",
        "code_reviewer",
        "Review for correctness, regressions, maintainability, and missing tests.",
        ["Findings carry severity, evidence, and a suggested fix", "No unresolved high-severity finding"],
        ["Verify against acceptance criteria"],
    ),
    (
        "Security review",
        "security_reviewer",
        "Review authn/authz, data handling, secrets, injection, and irreversible actions.",
        ["Security-sensitive surfaces are enumerated", "No unresolved high-severity finding"],
        ["Implement the change"],
    ),
    (
        "Prepare delivery",
        "release_manager",
        "Produce release notes, rollout checklist, migration notes, and the final summary.",
        ["Release notes exist", "Rollout and rollback steps are written down"],
        ["Review the implementation", "Security review"],
    ),
]


def _task_breakdown(context: AgentContext) -> dict[str, Any]:
    goal = _goal(context)
    tasks = [
        {
            "title": title,
            "description": f"{description} Goal: {goal}",
            "agent_role": role,
            "acceptance_criteria": list(criteria),
            "depends_on": list(depends),
        }
        for title, role, description, criteria, depends in _BASE_TASKS
    ]

    # One explicit mitigation task per high-severity risk in topic memory.
    for memory in _memories(context, *_RISKY):
        if _severity(memory) != "high":
            continue
        tasks.append(
            {
                "title": f"Mitigate risk: {str(memory['content'])[:80]}",
                "description": f"Address the recorded risk: {memory['content']}",
                "agent_role": "developer",
                "acceptance_criteria": [
                    "The risk is either mitigated or explicitly accepted with a rationale",
                    "The decision is recorded",
                ],
                "depends_on": ["Design the technical approach"],
            }
        )

    if _mentions(context, "schema", "migration"):
        tasks.append(
            {
                "title": "Write and review the database migration",
                "description": "Schema changes need a reviewed migration and a rollback path.",
                "agent_role": "architect",
                "acceptance_criteria": ["Migration applies to an empty database", "A rollback path exists"],
                "depends_on": ["Design the technical approach"],
            }
        )

    return {"tasks": tasks}


def _questions(context: AgentContext) -> dict[str, Any]:
    """Only ask about things a stated assumption cannot safely cover."""
    questions = [
        {
            "question": content if content.endswith("?") else f"{content} - what is the answer?",
            "why_it_matters": "Recorded in topic memory as unresolved; it affects scope.",
            "options": [],
            "recommendation": None,
        }
        for content in _contents(context, "open_question", limit=5)
    ]

    for memory in _memories(context, *_RISKY):
        if _severity(memory) == "high":
            questions.append(
                {
                    "question": f"Accept or mitigate this risk: {memory['content']}",
                    "why_it_matters": "High-severity risk from topic memory; mitigation changes scope.",
                    "options": ["Mitigate now", "Accept and document", "Defer to a follow-up"],
                    "recommendation": "Mitigate now",
                }
            )

    if not context.memories:
        questions.append(
            {
                "question": f"No topic memory was retrieved for {_project_name(context)}. Proceed on assumptions?",
                "why_it_matters": "Planning without domain memory raises the chance of repeating a known failure.",
                "options": ["Ingest more sources first", "Proceed on stated assumptions"],
                "recommendation": "Ingest more sources first",
            }
        )
    return {"questions": questions[:8]}


def _approvals(context: AgentContext) -> dict[str, Any]:
    """Pre-register the gated actions this plan implies, so they are visible
    before an agent is blocked by one."""
    approvals: list[dict[str, Any]] = []
    if _mentions(context, "schema", "migration", "table", "column"):
        approvals.append(
            {
                "action_type": "change_database_schema",
                "action_summary": f"{_project_name(context)} implies a schema change",
                "risk_level": "high",
            }
        )
    if _mentions(context, "auth", "permission", "billing", "retention", "password", "token"):
        approvals.append(
            {
                "action_type": "modify_auth_billing_permissions_security_retention",
                "action_summary": f"{_project_name(context)} touches auth, billing, permissions, or retention",
                "risk_level": "high",
            }
        )
    if _mentions(context, "dependency", "library", "package", "sdk"):
        approvals.append(
            {
                "action_type": "add_dependency",
                "action_summary": f"{_project_name(context)} may require a new dependency",
                "risk_level": "medium",
            }
        )
    if _mentions(context, "deploy", "release", "rollout", "production"):
        approvals.append(
            {
                "action_type": "deploy",
                "action_summary": f"{_project_name(context)} reaches production",
                "risk_level": "high",
            }
        )
    return {"approvals": approvals}


def _test_report(context: AgentContext) -> dict[str, Any]:
    criteria = [str(c) for c in context.extra.get("acceptance_criteria", [])]
    return {
        "summary": (
            f"Verification plan for {_project_name(context)} covering {len(criteria)} acceptance criteria."
            if criteria
            else f"No acceptance criteria recorded for {_project_name(context)}; nothing to verify against."
        ),
        "strategy": [
            "Run the existing automated suite",
            "Add cases for behaviour the change introduces",
            "Manually verify anything user-visible",
        ],
        # Honest default: this runtime cannot run tests, so nothing is "met".
        "evidence": [
            {"criterion": c, "verdict": "unverified", "evidence": "No test run recorded by the mock runtime."}
            for c in criteria
        ],
        "missing_coverage": _contents(context, *_RISKY, limit=5),
        "manual_steps": ["Exercise the primary user flow end to end"],
    }


def _review_report(context: AgentContext) -> dict[str, Any]:
    findings = [
        {
            "title": f"Unaddressed risk from topic memory: {str(m['content'])[:70]}",
            "severity": _severity(m),
            "evidence": str(m["content"]),
            "suggested_fix": "Confirm the implementation handles this, or record why it does not apply.",
            "location": None,
        }
        for m in _memories(context, *_RISKY)[:6]
    ]
    return {
        "summary": (
            f"Reviewed {_project_name(context)} against {len(context.memories)} topic memories. "
            "This runtime does not read code; findings are memory-derived only."
        ),
        "findings": findings,
        "blocking": any(f["severity"] == "high" for f in findings),
    }


def _security_report(context: AgentContext) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    checks = [
        (("auth", "login", "session", "token"), "Authentication or session handling is in scope"),
        (("permission", "role", "access"), "Authorization surface is in scope"),
        (("secret", "key", "credential", "password"), "Secret handling is in scope"),
        (("delete", "drop", "purge", "retention"), "Irreversible data operations are in scope"),
        (("sql", "query", "input", "upload"), "Untrusted input reaches a parser or store"),
    ]
    for words, title in checks:
        if _mentions(context, *words):
            findings.append(
                {
                    "title": title,
                    "severity": "medium",
                    "evidence": "Matched against project goal and topic memory.",
                    "suggested_fix": "Confirm the control is present and tested before delivery.",
                    "location": None,
                }
            )
    return {
        "summary": (
            f"Security surfaces implied by {_project_name(context)}. This runtime does not read code; "
            "it flags areas that need a human or model-backed review."
        ),
        "findings": findings,
        "blocking": False,
    }


def _release_summary(context: AgentContext) -> dict[str, Any]:
    done = [str(t) for t in context.extra.get("completed_tasks", [])]
    return {
        "summary": f"{_project_name(context)} delivery summary. {len(done)} tasks completed.",
        "release_notes": [f"Completed: {t}" for t in done] or ["No completed tasks recorded"],
        "rollout_checklist": [
            "Confirm every approval request is resolved",
            "Confirm no unresolved high-severity finding",
            "Land migrations before dependent code",
        ],
        "migration_notes": _contents(context, "architecture", limit=3),
        "operational_risks": _contents(context, *_RISKY, limit=5),
        "monitoring": ["Watch error rates on the touched surfaces for one release cycle"],
        "lessons": _contents(context, "lesson", limit=5),
    }


_GENERATORS = {
    "domain_context": _domain_context,
    "project_brief": _project_brief,
    "architecture_plan": _architecture_plan,
    "task_breakdown": _task_breakdown,
    "questions": _questions,
    "approvals": _approvals,
    "test_report": _test_report,
    "review_report": _review_report,
    "security_report": _security_report,
    "release_summary": _release_summary,
}


class MockAgentRuntime(AgentRuntime):
    name = "mock"

    async def run(
        self,
        agent_profile: AgentProfileLike,
        input: dict[str, Any],
        context: AgentContext | None = None,
    ) -> AgentRunResult:
        context = context or AgentContext()
        task = input.get("task")

        if task is None:
            # No structured task asked for: echo, as in Phase 1.
            return AgentRunResult(
                status="succeeded",
                output={
                    "runtime": self.name,
                    "agent": agent_profile.name,
                    "role": agent_profile.role,
                    "summary": f"[mock] {agent_profile.name} handled: {input.get('instruction', 'no instruction')}",
                    "input_echo": input,
                    "memories_considered": len(context.memories),
                    "next_action": "none (mock runtime)",
                },
            )

        generator = _GENERATORS.get(task)
        if generator is None:
            return AgentRunResult(
                status="failed",
                error=f"Mock runtime has no generator for task {task!r}. Known: {', '.join(sorted(_GENERATORS))}",
            )

        return AgentRunResult(status="succeeded", output=generator(context))
