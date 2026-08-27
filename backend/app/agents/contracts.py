"""Structured outputs exchanged with agent runtimes.

Every planning and review step asks a runtime for one named output and
validates the reply against the matching model. That is what keeps
orchestration provider-agnostic: a runtime may be a rule-based mock, a
LangGraph graph, or a model with tool-calling, and the code above it only ever
sees a validated object or a failed run.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.db.models import AGENT_ROLES, RISK_LEVELS


class DomainContext(BaseModel):
    """Domain Expert: what the topic's memory says that matters here."""

    summary: str
    key_facts: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    prior_attempts: list[str] = Field(default_factory=list)
    gotchas: list[str] = Field(default_factory=list)
    terminology: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    cited_memory_ids: list[str] = Field(default_factory=list)


class RiskItem(BaseModel):
    description: str
    severity: str = Field(default="medium", description=f"One of: {', '.join(RISK_LEVELS)}")
    mitigation: str | None = None


class ProjectBrief(BaseModel):
    """Lead PM: the scoped plan a human can argue with."""

    summary: str
    goals: list[str] = Field(default_factory=list)
    non_goals: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    risks: list[RiskItem] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)


class ArchitecturePlan(BaseModel):
    """Architect: how it gets built and what it touches."""

    approach: str
    impacted_areas: list[str] = Field(default_factory=list)
    data_changes: list[str] = Field(default_factory=list)
    apis: list[str] = Field(default_factory=list)
    rollout_notes: list[str] = Field(default_factory=list)
    risks: list[RiskItem] = Field(default_factory=list)


class TaskSpec(BaseModel):
    title: str
    description: str = ""
    agent_role: str = Field(default="developer", description=f"One of: {', '.join(AGENT_ROLES)}")
    acceptance_criteria: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list, description="Titles of tasks that must finish first")


class TaskBreakdown(BaseModel):
    tasks: list[TaskSpec] = Field(default_factory=list)


class QuestionSpec(BaseModel):
    question: str
    why_it_matters: str = ""
    options: list[str] = Field(default_factory=list)
    recommendation: str | None = None


class QuestionSet(BaseModel):
    """Only questions that materially affect scope, behaviour, security, cost,
    or irreversibility. Everything else should be a stated assumption."""

    questions: list[QuestionSpec] = Field(default_factory=list)


class ApprovalSpec(BaseModel):
    action_type: str
    action_summary: str
    risk_level: str = Field(default="medium", description=f"One of: {', '.join(RISK_LEVELS)}")


class ApprovalSet(BaseModel):
    approvals: list[ApprovalSpec] = Field(default_factory=list)


class TaskOutcome(BaseModel):
    """What a role reports after working a single task.

    Used by roles without a dedicated report - PM, Domain Expert, Architect,
    Developer - so every task pass leaves the same shape of trail.
    """

    summary: str
    work_done: list[str] = Field(default_factory=list)
    follow_ups: list[str] = Field(default_factory=list)
    blocked_by: list[str] = Field(default_factory=list)


class TestEvidence(BaseModel):
    criterion: str
    verdict: str = Field(default="unverified", description="met | not_met | unverified")
    evidence: str = ""


class TestReport(BaseModel):
    """QA: verification strategy and evidence per acceptance criterion."""

    summary: str
    strategy: list[str] = Field(default_factory=list)
    evidence: list[TestEvidence] = Field(default_factory=list)
    missing_coverage: list[str] = Field(default_factory=list)
    manual_steps: list[str] = Field(default_factory=list)


class Finding(BaseModel):
    title: str
    severity: str = Field(default="medium", description=f"One of: {', '.join(RISK_LEVELS)}")
    evidence: str = ""
    suggested_fix: str = ""
    location: str | None = None


class ReviewReport(BaseModel):
    """Code Reviewer / Security Reviewer: findings with severity and evidence."""

    summary: str
    findings: list[Finding] = Field(default_factory=list)
    blocking: bool = False


class PrDescription(BaseModel):
    """Release Manager: the pull request a reviewer will actually read."""

    title: str
    summary: str
    changes: list[str] = Field(default_factory=list)
    testing: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    checklist: list[str] = Field(default_factory=list)


class ReleaseSummary(BaseModel):
    """Release Manager: what shipped and what to watch."""

    summary: str
    release_notes: list[str] = Field(default_factory=list)
    rollout_checklist: list[str] = Field(default_factory=list)
    migration_notes: list[str] = Field(default_factory=list)
    operational_risks: list[str] = Field(default_factory=list)
    monitoring: list[str] = Field(default_factory=list)
    lessons: list[str] = Field(default_factory=list)


# Task name -> output model. The task name is what a planner asks a runtime for.
SCHEMAS: dict[str, type[BaseModel]] = {
    "task_outcome": TaskOutcome,
    "domain_context": DomainContext,
    "project_brief": ProjectBrief,
    "architecture_plan": ArchitecturePlan,
    "task_breakdown": TaskBreakdown,
    "questions": QuestionSet,
    "approvals": ApprovalSet,
    "test_report": TestReport,
    "review_report": ReviewReport,
    "security_report": ReviewReport,
    "release_summary": ReleaseSummary,
    "pr_description": PrDescription,
}


def schema_for(task: str) -> type[BaseModel]:
    try:
        return SCHEMAS[task]
    except KeyError:
        raise ValueError(f"Unknown agent task {task!r}. Known: {', '.join(sorted(SCHEMAS))}") from None
