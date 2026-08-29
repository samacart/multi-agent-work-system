"""Project planning end to end, on the deterministic runtime."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.models import AgentRun, ApprovalRequest, Artifact, Decision, Memory, Project, Task, Topic
from app.db.seed import seed_agent_profiles
from app.memory.embeddings import get_embedding_provider
from app.projects.planning import PlanningError, gather_context, plan_project

MEMORIES = [
    ("decision", "We decided that invite links expire after 14 days.", 0.85),
    ("constraint", "Invites must not be reusable once an account is created.", 0.8),
    ("risk", "Expired invites fail silently and the user sees a blank page.", 0.9),
    ("gotcha", "The invite service caches tokens for 5 minutes after issuance.", 0.7),
    ("architecture", "The invite service calls the billing API and writes to the invites table.", 0.7),
    ("open_question", "Who owns the reminder email copy?", 0.7),
    ("lesson", "The previous attempt failed because tokens were guessable.", 0.75),
]


@pytest.fixture
async def planned(session):
    await seed_agent_profiles(session)
    topic = Topic(name="customer onboarding")
    session.add(topic)
    await session.commit()

    provider = get_embedding_provider()
    for type_, content, importance in MEMORIES:
        session.add(
            Memory(
                topic_id=topic.id,
                type=type_,
                content=content,
                importance=importance,
                confidence=0.8,
                embedding=await provider.embed_one(content),
            )
        )
    project = Project(
        topic_id=topic.id,
        name="self-serve onboarding",
        goal="let a new organisation sign up and invite teammates without support",
    )
    session.add(project)
    await session.commit()
    return project


async def test_planning_produces_a_ready_project(session, planned):
    result = await plan_project(session, planned.id, use_gates=False)

    assert result.status == "ready"
    assert result.error is None
    assert result.memories_used == len(MEMORIES)
    await session.refresh(planned)
    assert planned.status == "ready"
    assert planned.brief and "# self-serve onboarding" in planned.brief


async def test_every_pass_records_an_agent_run(session, planned):
    result = await plan_project(session, planned.id, use_gates=False)

    runs = (await session.scalars(select(AgentRun).where(AgentRun.project_id == planned.id))).all()
    assert len(runs) == len(result.runs) == 6
    assert all(r.status == "succeeded" for r in runs)
    assert all(r.started_at and r.completed_at for r in runs)
    assert {r.input["task"] for r in runs} == {
        "domain_context",
        "project_brief",
        "architecture_plan",
        "task_breakdown",
        "questions",
        "approvals",
    }


async def test_tasks_are_created_with_acceptance_criteria(session, planned):
    await plan_project(session, planned.id, use_gates=False)

    tasks = (await session.scalars(select(Task).where(Task.project_id == planned.id))).all()
    assert len(tasks) >= 8
    assert all(t.acceptance_criteria for t in tasks)
    # The SDLC spine is covered by the right specialists.
    assert {t.agent_role for t in tasks} >= {
        "lead_pm",
        "domain_expert",
        "architect",
        "developer",
        "qa",
        "code_reviewer",
        "security_reviewer",
        "release_manager",
    }
    # Only work with nothing to wait for starts ready.
    roots = [t for t in tasks if not t.metadata_json.get("depends_on")]
    assert roots and all(t.status == "ready" for t in roots)
    assert all(t.status == "backlog" for t in tasks if t.metadata_json.get("depends_on"))


async def test_high_severity_risks_become_their_own_tasks(session, planned):
    await plan_project(session, planned.id, use_gates=False)
    titles = [t.title for t in (await session.scalars(select(Task))).all()]
    assert any(title.startswith("Mitigate risk:") for title in titles)


async def test_brief_records_assumptions_risks_and_unknowns(session, planned):
    await plan_project(session, planned.id, use_gates=False)
    await session.refresh(planned)

    assert "## Assumptions" in planned.brief
    assert "## Risks" in planned.brief
    assert "## Unknowns" in planned.brief
    assert "expire after 14 days" in planned.brief
    assert "Who owns the reminder email copy?" in planned.brief


async def test_artifacts_are_persisted(session, planned):
    await plan_project(session, planned.id, use_gates=False)

    artifacts = (await session.scalars(select(Artifact).where(Artifact.project_id == planned.id))).all()
    assert {a.type for a in artifacts} == {"project_brief", "architecture_plan", "task_breakdown"}
    assert all(a.content.strip() for a in artifacts)


async def test_open_questions_reach_the_human_queue(session, planned):
    await plan_project(session, planned.id, use_gates=False)

    decisions = (await session.scalars(select(Decision).where(Decision.project_id == planned.id))).all()
    assert decisions
    assert all(d.answer is None for d in decisions)
    assert any("reminder email copy" in d.question for d in decisions)


async def test_implied_gated_actions_are_pre_registered(session, planned):
    await plan_project(session, planned.id, use_gates=False)

    approvals = (await session.scalars(select(ApprovalRequest).where(ApprovalRequest.project_id == planned.id))).all()
    action_types = {a.action_type for a in approvals}
    # Topic memory mentions tokens and a table, so both gates apply.
    assert "modify_auth_billing_permissions_security_retention" in action_types
    assert all(a.status == "pending" for a in approvals)


async def test_replanning_sharpens_rather_than_duplicates(session, planned):
    first = await plan_project(session, planned.id, use_gates=False)
    second = await plan_project(session, planned.id, use_gates=False)

    assert second.tasks_created == 0
    assert second.tasks_updated == first.tasks_created
    assert second.questions_created == 0
    assert second.approvals_created == 0

    assert len((await session.scalars(select(Task))).all()) == first.tasks_created
    assert len((await session.scalars(select(Artifact))).all()) == 3
    assert len((await session.scalars(select(Decision))).all()) == first.questions_created


async def test_replanning_does_not_undo_started_work(session, planned):
    await plan_project(session, planned.id, use_gates=False)
    task = (await session.scalars(select(Task).where(Task.status == "ready"))).first()
    task.status = "in_progress"
    await session.commit()

    await plan_project(session, planned.id, use_gates=False)
    await session.refresh(task)
    assert task.status == "in_progress"


async def test_planning_without_a_topic_still_works(session):
    await seed_agent_profiles(session)
    project = Project(name="orphan project", goal="do a thing")
    session.add(project)
    await session.commit()

    result = await plan_project(session, project.id, use_gates=False)

    assert result.status == "ready"
    assert result.memories_used == 0
    # With no memory to plan against, that itself becomes the question to ask.
    decisions = (await session.scalars(select(Decision))).all()
    assert any("No topic memory" in d.question for d in decisions)


async def test_a_failing_runtime_blocks_the_project(session, planned, monkeypatch):
    from app.agents.runtime.base import AgentRunResult, AgentRuntime

    class BrokenRuntime(AgentRuntime):
        name = "broken"

        async def run(self, agent_profile, input, context=None):  # noqa: ANN001, ARG002
            return AgentRunResult(status="failed", error="model provider unreachable")

    monkeypatch.setattr("app.orchestration.runs.get_runtime", lambda: BrokenRuntime())
    result = await plan_project(session, planned.id, use_gates=False)

    assert result.status == "failed"
    assert "model provider unreachable" in result.error
    await session.refresh(planned)
    assert planned.status == "blocked"

    runs = (await session.scalars(select(AgentRun))).all()
    assert len(runs) == 1
    assert runs[0].status == "failed"


async def test_output_violating_the_contract_fails_the_run(session, planned, monkeypatch):
    from app.agents.runtime.base import AgentRunResult, AgentRuntime

    class SloppyRuntime(AgentRuntime):
        name = "sloppy"

        async def run(self, agent_profile, input, context=None):  # noqa: ANN001, ARG002
            return AgentRunResult(status="succeeded", output={"not": "the right shape"})

    monkeypatch.setattr("app.orchestration.runs.get_runtime", lambda: SloppyRuntime())
    result = await plan_project(session, planned.id, use_gates=False)

    assert result.status == "failed"
    assert "did not match the domain_context contract" in result.error


async def test_missing_project_raises(session):
    import uuid

    with pytest.raises(PlanningError, match="not found"):
        await plan_project(session, uuid.uuid4())


async def test_retrieval_is_scoped_to_the_project_goal(session, planned):
    context, memories = await gather_context(session, planned)

    assert len(memories) == len(MEMORIES)
    assert context.extra["project_name"] == "self-serve onboarding"
    assert context.extra["topic_name"] == "customer onboarding"
    assert all("id" in m and "type" in m for m in context.memories)


async def test_answers_a_human_gave_reach_the_agents(session, planned):
    """The point of asking is to act on the answer. Without this, a project
    re-planned after its questions were answered plans as though they were not."""
    from app.approvals.service import answer_question, record_question
    from app.projects.planning import gather_context

    decision = await record_question(session, planned.id, "Should invites be org-scoped?", "affects billing")
    await answer_question(session, decision.id, "Yes, org-scoped", decided_by="sam")
    await record_question(session, planned.id, "What about SSO?", "may change auth")

    context, _memories = await gather_context(session, planned)

    assert context.extra["decisions_made_by_the_human"] == ["Should invites be org-scoped? -> Yes, org-scoped"]
    assert context.extra["questions_still_open"] == ["What about SSO?"]


async def test_a_human_answer_becomes_a_stated_assumption(session, planned):
    from sqlalchemy import select as sa_select

    from app.approvals.service import answer_question
    from app.db.models import Artifact, Decision

    await plan_project(session, planned.id, use_gates=False)
    decision = (await session.scalars(sa_select(Decision))).first()
    await answer_question(session, decision.id, "The growth team owns it", decided_by="sam")

    await plan_project(session, planned.id, use_gates=False)

    brief = (
        await session.scalars(sa_select(Artifact).where(Artifact.type == "project_brief"))
    ).one()
    assert "The growth team owns it" in brief.content


async def test_an_answered_question_is_not_asked_again(session, planned):
    from sqlalchemy import select as sa_select

    from app.approvals.service import answer_question
    from app.db.models import Decision

    await plan_project(session, planned.id, use_gates=False)
    decisions = (await session.scalars(sa_select(Decision))).all()
    for decision in decisions:
        await answer_question(session, decision.id, "settled", decided_by="sam")

    await plan_project(session, planned.id, use_gates=False)

    reopened = [d for d in (await session.scalars(sa_select(Decision))).all() if not d.answer]
    assert reopened == []


# --- stage gating ---


async def _approve(session, project_id, action_type):
    from sqlalchemy import select as sa_select

    from app.approvals.service import respond_to_approval
    from app.db.models import ApprovalRequest

    approval = (
        await session.scalars(
            sa_select(ApprovalRequest).where(
                ApprovalRequest.project_id == project_id, ApprovalRequest.action_type == action_type
            )
        )
    ).one()
    await respond_to_approval(session, approval.id, "approved")


async def test_planning_stops_after_the_brief_for_approval(session, planned):
    """A wrong brief should be caught before an architecture plan and a task
    breakdown are built on top of it."""
    from sqlalchemy import select as sa_select

    from app.db.models import Artifact, Task

    result = await plan_project(session, planned.id)

    assert result.status == "awaiting_approval"
    assert result.stage == "brief"
    assert result.awaiting_approval == "approve_project_brief"
    assert result.stages_completed == ["brief"]

    types = {a.type for a in (await session.scalars(sa_select(Artifact))).all()}
    assert types == {"project_brief"}
    assert (await session.scalars(sa_select(Task))).all() == []

    await session.refresh(planned)
    assert planned.status == "planning"
    assert planned.brief


async def test_approving_a_stage_lets_the_next_one_run(session, planned):
    from sqlalchemy import select as sa_select

    from app.db.models import Artifact

    await plan_project(session, planned.id)
    await _approve(session, planned.id, "approve_project_brief")

    second = await plan_project(session, planned.id)

    assert second.stage == "architecture"
    assert second.awaiting_approval == "approve_architecture_plan"
    assert second.stages_completed == ["brief", "architecture"]

    types = {a.type for a in (await session.scalars(sa_select(Artifact))).all()}
    assert types == {"project_brief", "architecture_plan"}


async def test_the_full_gated_sequence_reaches_ready(session, planned):
    from sqlalchemy import select as sa_select

    from app.db.models import Artifact, Task

    await plan_project(session, planned.id)
    await _approve(session, planned.id, "approve_project_brief")
    await plan_project(session, planned.id)
    await _approve(session, planned.id, "approve_architecture_plan")
    third = await plan_project(session, planned.id)

    assert third.stage == "tasks"
    assert third.tasks_created > 0
    assert third.questions_created > 0

    await _approve(session, planned.id, "approve_task_breakdown")
    final = await plan_project(session, planned.id)

    assert final.status == "ready"
    assert final.stage is None
    assert final.stages_completed == ["brief", "architecture", "tasks"]

    types = {a.type for a in (await session.scalars(sa_select(Artifact))).all()}
    assert types == {"project_brief", "architecture_plan", "task_breakdown"}
    assert (await session.scalars(sa_select(Task))).all()

    await session.refresh(planned)
    assert planned.status == "ready"


async def test_an_approved_stage_is_not_re_run(session, planned):
    from sqlalchemy import select as sa_select

    from app.db.models import AgentRun

    await plan_project(session, planned.id)
    await _approve(session, planned.id, "approve_project_brief")
    runs_after_brief = len((await session.scalars(sa_select(AgentRun))).all())

    await plan_project(session, planned.id)
    runs_after_architecture = len((await session.scalars(sa_select(AgentRun))).all())

    # Domain context, the architecture pass, and the briefing that reviews it -
    # the brief itself is not redone.
    assert runs_after_architecture - runs_after_brief == 3


async def test_gates_can_be_skipped_for_a_straight_through_plan(session, planned):
    result = await plan_project(session, planned.id, use_gates=False)

    assert result.status == "ready"
    assert result.awaiting_approval is None
    assert result.stages_completed == ["brief", "architecture", "tasks"]
    assert result.tasks_created > 0


async def test_the_gated_flow_over_the_api(client, session):
    from app.db.seed import seed_agent_profiles

    await seed_agent_profiles(session)
    project = (await client.post("/projects", json={"name": "gated", "goal": "ship it"})).json()

    first = (await client.post(f"/projects/{project['id']}/plan")).json()
    assert first["status"] == "awaiting_approval"
    assert first["awaiting_approval"] == "approve_project_brief"

    approvals = (await client.get(f"/projects/{project['id']}/approvals")).json()
    gate = next(a for a in approvals if a["action_type"] == "approve_project_brief")
    assert gate["risk_level"] == "low"

    await client.post(f"/approvals/{gate['id']}/respond", json={"status": "approved"})
    second = (await client.post(f"/projects/{project['id']}/plan")).json()
    assert second["stage"] == "architecture"


# --- a decision handed over should come with a view ---


async def test_a_stage_gate_carries_a_briefing_from_another_role(session, planned):
    """An agent recommending its own work is not a review."""
    from sqlalchemy import select as sa_select

    from app.db.models import ApprovalRequest
    from app.projects.planning import STAGE_REVIEWERS

    await plan_project(session, planned.id)

    gate = (
        await session.scalars(
            sa_select(ApprovalRequest).where(ApprovalRequest.action_type == "approve_project_brief")
        )
    ).one()

    assert gate.metadata_json.get("reviewed_by") == STAGE_REVIEWERS["brief"] == "domain_expert"
    briefing = gate.metadata_json["briefing"]
    assert briefing["summary"]
    assert briefing["recommendation"] in {"approve", "approve_with_changes", "revise"}
    assert "key_points" in briefing


async def test_the_task_breakdown_is_reviewed_by_the_architect(session, planned):
    """The pairing that catches a breakdown drifting from the plan it came from
    - which is exactly what happened on a real project."""
    from app.projects.planning import STAGE_REVIEWERS

    assert STAGE_REVIEWERS["tasks"] == "architect"
    assert STAGE_REVIEWERS["architecture"] != "architect"
    assert STAGE_REVIEWERS["brief"] != "lead_pm"


async def test_questions_carry_their_options_and_recommendation(session, planned):
    from sqlalchemy import select as sa_select

    from app.db.models import Decision

    await plan_project(session, planned.id, use_gates=False)

    decisions = (await session.scalars(sa_select(Decision))).all()
    assert decisions
    with_view = [d for d in decisions if d.metadata_json.get("recommendation")]
    assert with_view, "no question offered a recommendation"
    assert with_view[0].metadata_json["options"]


async def test_a_failed_briefing_does_not_block_the_gate(session, planned, monkeypatch):
    """The human can still read the artifact themselves."""
    from sqlalchemy import select as sa_select

    from app.agents.runtime.base import AgentRunResult, AgentRuntime
    from app.agents.runtime.mock import MockAgentRuntime
    from app.db.models import ApprovalRequest

    class NoBriefings(AgentRuntime):
        name = "no-briefings"

        async def run(self, agent_profile, input, context=None):  # noqa: ANN001
            if input.get("task") == "approval_briefing":
                return AgentRunResult(status="failed", error="briefing unavailable")
            return await MockAgentRuntime().run(agent_profile, input, context)

    import app.orchestration.runs as runs_module

    original = runs_module.get_runtime
    runs_module.get_runtime = lambda: NoBriefings()
    try:
        result = await plan_project(session, planned.id)
    finally:
        runs_module.get_runtime = original

    assert result.status == "awaiting_approval"
    gate = (await session.scalars(sa_select(ApprovalRequest).where(ApprovalRequest.action_type == "approve_project_brief"))).one()
    assert "briefing_error" in gate.metadata_json


async def test_a_resumed_stage_sees_the_stages_already_approved(session, planned):
    """A task breakdown proposed backend work against an architecture plan that
    said frontend-only, because skipping an approved stage dropped its artifact:
    only the call that produced one ever put it in context."""
    seen: dict[str, dict] = {}

    from app.agents.runtime.base import AgentRuntime
    from app.agents.runtime.mock import MockAgentRuntime

    class Recording(AgentRuntime):
        name = "recording"

        async def run(self, agent_profile, input, context=None):  # noqa: ANN001
            seen[str(input.get("task"))] = dict(context.extra) if context else {}
            return await MockAgentRuntime().run(agent_profile, input, context)

    import app.orchestration.runs as runs_module

    original = runs_module.get_runtime
    runs_module.get_runtime = lambda: Recording()
    try:
        await plan_project(session, planned.id)
        await _approve(session, planned.id, "approve_project_brief")
        await plan_project(session, planned.id)
        await _approve(session, planned.id, "approve_architecture_plan")
        seen.clear()
        await plan_project(session, planned.id)
    finally:
        runs_module.get_runtime = original

    breakdown_context = seen["task_breakdown"]
    assert "approved_project_brief" in breakdown_context
    assert "approved_architecture_plan" in breakdown_context
    assert "# Architecture plan" in breakdown_context["approved_architecture_plan"]


async def test_replanning_removes_tasks_the_new_plan_dropped(session, planned):
    """Re-planning replaced a drifted breakdown and left its seventeen tasks
    sitting beside the twenty that replaced them."""
    from sqlalchemy import select as sa_select

    from app.db.models import Task

    await plan_project(session, planned.id, use_gates=False)
    stale = Task(project_id=planned.id, title="A task no plan asks for", status="backlog")
    session.add(stale)
    await session.commit()

    result = await plan_project(session, planned.id, use_gates=False)

    titles = {t.title for t in (await session.scalars(sa_select(Task))).all()}
    assert "A task no plan asks for" not in titles
    assert result.tasks_removed == 1


async def test_replanning_keeps_work_that_has_already_started(session, planned):
    """A plan does not get to delete work in flight."""
    from sqlalchemy import select as sa_select

    from app.db.models import Task

    await plan_project(session, planned.id, use_gates=False)
    started = Task(project_id=planned.id, title="Started but off-plan", status="in_progress")
    session.add(started)
    await session.commit()

    result = await plan_project(session, planned.id, use_gates=False)

    kept = (await session.scalars(sa_select(Task).where(Task.title == "Started but off-plan"))).one()
    assert kept.status == "in_progress"
    assert kept.metadata_json["dropped_from_plan"]
    assert any("no longer in the plan but has started" in n for n in result.notes)
    assert result.tasks_removed == 0
