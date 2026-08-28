"""Project planning.

Runs the Discovery -> Planning -> Architecture passes for a project and turns
their structured outputs into the durable things a human works with: a brief,
an architecture plan, a task breakdown, queued questions, and pre-registered
approval gates.

Re-planning is idempotent by design: artifacts are replaced rather than
appended, tasks are matched by title, questions and approvals are deduplicated.
Planning a project twice should sharpen it, not multiply it.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.contracts import ArchitecturePlan, DomainContext, ProjectBrief, TaskBreakdown
from app.agents.runtime.base import AgentContext
from app.approvals.service import record_question, request_approval
from app.artifacts.service import bullets, upsert_artifact
from app.db.models import AGENT_ROLES, Decision, Memory, Project, Task, Topic
from app.memory.search import search_memories
from app.orchestration.runs import AgentRunFailed, execute_run

log = logging.getLogger(__name__)

MEMORY_LIMIT = 40


@dataclass
class PlanningResult:
    project_id: str
    status: str
    memories_used: int = 0
    runs: list[str] = field(default_factory=list)
    tasks_created: int = 0
    tasks_updated: int = 0
    questions_created: int = 0
    approvals_created: int = 0
    artifacts: list[str] = field(default_factory=list)
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "status": self.status,
            "memories_used": self.memories_used,
            "runs": self.runs,
            "tasks_created": self.tasks_created,
            "tasks_updated": self.tasks_updated,
            "questions_created": self.questions_created,
            "approvals_created": self.approvals_created,
            "artifacts": self.artifacts,
            "error": self.error,
        }


class PlanningError(Exception):
    pass


async def gather_context(
    session: AsyncSession, project: Project, limit: int = MEMORY_LIMIT
) -> tuple[AgentContext, list[Memory]]:
    """Retrieve the memory a planning pass should see.

    The retrieval query is the project's own goal, so what surfaces is what is
    relevant to this project rather than everything the topic knows.
    """
    topic: Topic | None = await session.get(Topic, project.topic_id) if project.topic_id else None

    memories: list[Memory] = []
    if project.topic_id:
        query = " ".join(filter(None, [project.name, project.goal or ""]))
        hits = await search_memories(session, query=query, topic_id=project.topic_id, limit=limit)
        memories = [hit.memory for hit in hits]

    # Decisions a human has already made are the highest-authority context
    # there is: the whole point of asking was to act on the answer. Without
    # this, a project re-planned after its questions were answered plans as
    # though they never were.
    decisions = list(
        (
            await session.scalars(
                select(Decision).where(Decision.project_id == project.id).order_by(Decision.created_at)
            )
        ).all()
    )
    answered = [f"{d.question} -> {d.answer}" for d in decisions if d.answer]
    unanswered = [d.question for d in decisions if not d.answer]

    context = AgentContext(
        project_id=str(project.id),
        memories=[
            {
                "id": str(m.id),
                "type": m.type,
                "content": m.content,
                "importance": m.importance,
                "confidence": m.confidence,
            }
            for m in memories
        ],
        extra={
            "project_name": project.name,
            "goal": project.goal or "",
            "topic_name": topic.name if topic else "",
            "decisions_made_by_the_human": answered,
            "questions_still_open": unanswered,
        },
    )
    return context, memories


async def plan_project(session: AsyncSession, project_id: uuid.UUID) -> PlanningResult:
    project = await session.get(Project, project_id)
    if project is None:
        raise PlanningError(f"Project {project_id} not found")

    result = PlanningResult(project_id=str(project.id), status="planning")
    project.status = "planning"
    await session.commit()

    context, memories = await gather_context(session, project)
    result.memories_used = len(memories)

    try:
        domain = await _run(session, project, context, "domain_expert", "domain_context",
                            "Apply the topic's durable memory to this project.", result)
        context.extra["domain_context"] = domain.model_dump(mode="json")

        brief = await _run(session, project, context, "lead_pm", "project_brief",
                           "Turn this goal into a scoped project brief.", result)
        context.extra["project_brief"] = brief.model_dump(mode="json")

        architecture = await _run(session, project, context, "architect", "architecture_plan",
                                  "Propose the implementation design and call out risks.", result)
        context.extra["architecture_plan"] = architecture.model_dump(mode="json")

        breakdown = await _run(session, project, context, "lead_pm", "task_breakdown",
                               "Break this project into tasks with acceptance criteria.", result)

        questions = await _run(session, project, context, "lead_pm", "questions",
                               "Surface only decisions that need human judgement.", result)

        approvals = await _run(session, project, context, "lead_pm", "approvals",
                               "Pre-register the gated actions this plan implies.", result)
    except AgentRunFailed as exc:
        project.status = "blocked"
        result.status = "failed"
        result.error = str(exc)
        await session.commit()
        log.warning("planning failed for project %s: %s", project.name, exc)
        return result

    await _write_artifacts(session, project, domain, brief, architecture, breakdown, result)
    await _sync_tasks(session, project, breakdown, result)

    for question in questions.questions:
        if await record_question(session, project.id, question.question, question.why_it_matters):
            result.questions_created += 1

    for approval in approvals.approvals:
        _request, created = await request_approval(
            session,
            action_type=approval.action_type,
            action_summary=approval.action_summary,
            project_id=project.id,
            risk_level=approval.risk_level,
        )
        if created:
            result.approvals_created += 1

    project.brief = _brief_markdown(project, brief, domain)
    project.status = "ready"
    result.status = "ready"
    await session.commit()
    log.info("planned project %s: %d tasks, %d questions", project.name, result.tasks_created, result.questions_created)
    return result


async def _run(session, project, context, role, task, instruction, result):  # noqa: ANN001, ANN202
    outcome = await execute_run(
        session, role=role, task=task, instruction=instruction, context=context, project_id=project.id
    )
    result.runs.append(str(outcome.run.id))
    return outcome.output


def _risk_lines(risks) -> list[str]:  # noqa: ANN001
    return [f"**{r.severity}** - {r.description}" + (f" (mitigation: {r.mitigation})" if r.mitigation else "") for r in risks]


def _brief_markdown(project: Project, brief: ProjectBrief, domain: DomainContext) -> str:
    return f"""# {project.name}

{brief.summary}

## Goals
{bullets(brief.goals)}

## Non-goals
{bullets(brief.non_goals)}

## Assumptions
{bullets(brief.assumptions)}

## Unknowns
{bullets(brief.unknowns, "_none_")}

## Risks
{bullets(_risk_lines(brief.risks), "_none identified_")}

## Success criteria
{bullets(brief.success_criteria)}

## Domain context
{domain.summary}

### Constraints from topic memory
{bullets(domain.constraints)}

### Prior attempts
{bullets(domain.prior_attempts)}

### Gotchas
{bullets(domain.gotchas)}
"""


def _architecture_markdown(project: Project, plan: ArchitecturePlan) -> str:
    return f"""# Architecture plan - {project.name}

{plan.approach}

## Impacted areas
{bullets(plan.impacted_areas)}

## Data changes
{bullets(plan.data_changes, "_none identified_")}

## APIs
{bullets(plan.apis, "_none identified_")}

## Rollout
{bullets(plan.rollout_notes)}

## Risks
{bullets(_risk_lines(plan.risks), "_none identified_")}
"""


def _breakdown_markdown(project: Project, breakdown: TaskBreakdown) -> str:
    sections = []
    for spec in breakdown.tasks:
        criteria = "\n".join(f"  - [ ] {c}" for c in spec.acceptance_criteria) or "  - [ ] _no criteria_"
        depends = f"\n\n  Depends on: {', '.join(spec.depends_on)}" if spec.depends_on else ""
        sections.append(f"### {spec.title}\n\n`{spec.agent_role}` - {spec.description}\n\n{criteria}{depends}")
    body = "\n\n".join(sections) or "_no tasks generated_"
    return f"# Task breakdown - {project.name}\n\n{len(breakdown.tasks)} tasks.\n\n{body}\n"


async def _write_artifacts(session, project, domain, brief, architecture, breakdown, result):  # noqa: ANN001
    for type_, title, content in (
        ("project_brief", f"Project brief - {project.name}", _brief_markdown(project, brief, domain)),
        ("architecture_plan", f"Architecture plan - {project.name}", _architecture_markdown(project, architecture)),
        ("task_breakdown", f"Task breakdown - {project.name}", _breakdown_markdown(project, breakdown)),
    ):
        await upsert_artifact(session, project.id, type_, title, content)
        result.artifacts.append(type_)


async def _sync_tasks(session: AsyncSession, project: Project, breakdown: TaskBreakdown, result: PlanningResult) -> None:
    """Match tasks by title so re-planning updates rather than duplicates.

    Tasks a human has already moved past `backlog` keep their status - the plan
    does not get to undo work that has started.
    """
    existing = {
        task.title: task
        for task in (await session.scalars(select(Task).where(Task.project_id == project.id))).all()
    }

    for spec in breakdown.tasks:
        role = spec.agent_role if spec.agent_role in AGENT_ROLES else "developer"
        task = existing.get(spec.title)
        if task is None:
            session.add(
                Task(
                    project_id=project.id,
                    title=spec.title,
                    description=spec.description,
                    agent_role=role,
                    # Nothing to wait for means it is ready to pick up now.
                    status="backlog" if spec.depends_on else "ready",
                    acceptance_criteria=spec.acceptance_criteria,
                    metadata_json={"depends_on": spec.depends_on},
                )
            )
            result.tasks_created += 1
        else:
            task.description = spec.description
            task.agent_role = role
            task.acceptance_criteria = spec.acceptance_criteria
            task.metadata_json = {**(task.metadata_json or {}), "depends_on": spec.depends_on}
            result.tasks_updated += 1

    await session.commit()
