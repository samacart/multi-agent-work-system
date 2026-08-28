"""The SDLC execution loop."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.models import AgentRun, ApprovalRequest, Artifact, Memory, Project, Task, Topic
from app.db.seed import seed_agent_profiles
from app.memory.embeddings import get_embedding_provider
from app.orchestration.sdlc import SdlcError, order_tasks, run_project
from app.projects.planning import plan_project

MEMORIES = [
    ("decision", "We decided that invite links expire after 14 days.", 0.85),
    ("risk", "Expired invites fail silently and the user sees a blank page.", 0.9),
    ("architecture", "The invite service writes to the invites table.", 0.7),
    ("lesson", "The previous attempt failed because tokens were guessable.", 0.75),
]


@pytest.fixture
async def project(session) -> Project:
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
    project = Project(topic_id=topic.id, name="self-serve onboarding", goal="let an org sign up unaided")
    session.add(project)
    await session.commit()

    await plan_project(session, project.id, use_gates=False)
    return project


async def _clear_approvals(session, project):
    for approval in (await session.scalars(select(ApprovalRequest).where(ApprovalRequest.project_id == project.id))).all():
        approval.status = "approved"
    await session.commit()


# --- ordering ---


def _task(title, depends=()):  # noqa: ANN001, ANN202
    return Task(project_id=None, title=title, metadata_json={"depends_on": list(depends)})


def test_tasks_run_in_dependency_order():
    a, b, c = _task("a"), _task("b", ["a"]), _task("c", ["b"])
    ordered = [t.title for t in order_tasks([c, b, a])]
    assert ordered == ["a", "b", "c"]


def test_a_dependency_cycle_does_not_hang():
    a, b = _task("a", ["b"]), _task("b", ["a"])
    assert {t.title for t in order_tasks([a, b])} == {"a", "b"}


def test_unknown_dependencies_are_ignored():
    a = _task("a", ["does not exist"])
    assert [t.title for t in order_tasks([a])] == ["a"]


# --- the loop ---


async def test_a_pending_gate_blocks_the_roles_it_governs(session, project):
    result = await run_project(session, project.id)

    assert result.tasks_blocked > 0
    assert any("approval gate" in note for note in result.notes)

    blocked = [t for t in (await session.scalars(select(Task))).all() if t.status == "blocked"]
    assert {t.agent_role for t in blocked} <= {"developer", "architect", "release_manager"}

    await session.refresh(project)
    assert project.status == "blocked"


async def test_every_role_runs_once_the_gate_is_approved(session, project):
    await _clear_approvals(session, project)
    result = await run_project(session, project.id)

    assert result.tasks_blocked == 0
    assert result.tasks_run >= 8

    runs = (await session.scalars(select(AgentRun).where(AgentRun.project_id == project.id))).all()
    roles_run = set()
    for run in runs:
        if run.task_id is not None:
            task = await session.get(Task, run.task_id)
            roles_run.add(task.agent_role)
    assert roles_run >= {
        "lead_pm",
        "domain_expert",
        "architect",
        "developer",
        "qa",
        "code_reviewer",
        "security_reviewer",
        "release_manager",
    }
    assert all(r.status == "succeeded" for r in runs)


async def test_review_outputs_become_artifacts(session, project):
    await _clear_approvals(session, project)
    await run_project(session, project.id)

    artifacts = {a.type for a in (await session.scalars(select(Artifact).where(Artifact.project_id == project.id))).all()}
    assert {"test_report", "review_report", "security_report", "release_notes", "final_summary"} <= artifacts


async def test_qa_evidence_is_attached_to_the_tasks_that_own_each_criterion(session, project):
    await _clear_approvals(session, project)
    await run_project(session, project.id)

    tasks = (await session.scalars(select(Task).where(Task.project_id == project.id))).all()
    with_evidence = [t for t in tasks if t.evidence]
    assert with_evidence
    for task in with_evidence:
        criteria = {e["criterion"] for e in task.evidence}
        assert criteria <= set(task.acceptance_criteria)


async def test_work_is_not_marked_done_without_evidence(session, project):
    """The mock runtime cannot execute anything, so QA reports every criterion
    as unverified and work must stall at review rather than be claimed."""
    await _clear_approvals(session, project)
    result = await run_project(session, project.id)

    assert result.tasks_done == 0
    assert result.tasks_verified == 0
    assert any("awaiting verification evidence" in note for note in result.notes)

    await session.refresh(project)
    assert project.status == "review"
    assert all(t.status != "done" for t in (await session.scalars(select(Task))).all())


async def test_met_evidence_promotes_work_to_done(session, project, monkeypatch):
    """With a runtime that actually verifies, the same loop delivers."""
    from app.agents.runtime import mock as mock_module

    original = mock_module._test_report

    def verified_report(context):  # noqa: ANN001, ANN202
        report = original(context)
        for entry in report["evidence"]:
            entry["verdict"] = "met"
            entry["evidence"] = "suite passed"
        return report

    monkeypatch.setitem(mock_module._GENERATORS, "test_report", verified_report)
    # A blocking finding would still hold work back; clear the risk memories.
    for memory in (await session.scalars(select(Memory).where(Memory.type == "risk"))).all():
        await session.delete(memory)
    await session.commit()
    await _clear_approvals(session, project)

    result = await run_project(session, project.id)

    assert result.tasks_verified > 0
    assert result.tasks_done == result.tasks_verified
    await session.refresh(project)
    assert project.status in {"delivered", "review"}


async def test_a_blocking_finding_holds_back_promotion(session, project, monkeypatch):
    from app.agents.runtime import mock as mock_module

    original = mock_module._test_report

    def verified_report(context):  # noqa: ANN001, ANN202
        report = original(context)
        for entry in report["evidence"]:
            entry["verdict"] = "met"
        return report

    monkeypatch.setitem(mock_module._GENERATORS, "test_report", verified_report)
    await _clear_approvals(session, project)

    result = await run_project(session, project.id)

    # The high-severity risk memory makes the review report blocking.
    assert result.blocking_findings > 0
    assert result.tasks_done == 0
    assert any("blocking finding is unresolved" in note for note in result.notes)


async def test_lessons_are_written_back_to_topic_memory(session, project):
    await _clear_approvals(session, project)
    before = len((await session.scalars(select(Memory))).all())

    result = await run_project(session, project.id)

    assert result.lessons_stored > 0
    learned = (await session.scalars(select(Memory).where(Memory.project_id == project.id))).all()
    assert learned
    assert {m.type for m in learned} <= {"lesson", "gotcha"}
    assert all(m.topic_id == project.topic_id for m in learned)
    assert all(m.embedding for m in learned)
    assert len((await session.scalars(select(Memory))).all()) == before + result.lessons_stored


async def test_rerunning_does_not_duplicate_lessons_or_artifacts(session, project):
    await _clear_approvals(session, project)
    first = await run_project(session, project.id)
    artifacts_after_first = len((await session.scalars(select(Artifact))).all())

    second = await run_project(session, project.id)

    assert second.lessons_stored == 0
    assert len((await session.scalars(select(Artifact))).all()) == artifacts_after_first
    assert first.artifacts and second.artifacts


async def test_a_failing_agent_blocks_its_task_and_its_dependents(session, project, monkeypatch):
    await _clear_approvals(session, project)

    from app.agents.runtime.base import AgentRunResult, AgentRuntime

    class FlakyRuntime(AgentRuntime):
        name = "flaky"

        async def run(self, agent_profile, input, context=None):  # noqa: ANN001, ARG002
            if agent_profile.role == "architect":
                return AgentRunResult(status="failed", error="architect runtime exploded")
            from app.agents.runtime.mock import MockAgentRuntime

            return await MockAgentRuntime().run(agent_profile, input, context)

    monkeypatch.setattr("app.orchestration.runs.get_runtime", lambda: FlakyRuntime())
    result = await run_project(session, project.id)

    assert result.tasks_blocked >= 1
    assert any("architect runtime exploded" in note for note in result.notes)
    # Everything downstream of the architect task is skipped rather than run.
    assert result.tasks_skipped > 0


async def test_running_an_unplanned_project_is_refused(session):
    await seed_agent_profiles(session)
    project = Project(name="unplanned")
    session.add(project)
    await session.commit()

    with pytest.raises(SdlcError, match="no tasks"):
        await run_project(session, project.id)


async def test_missing_project_raises(session):
    import uuid

    with pytest.raises(SdlcError, match="not found"):
        await run_project(session, uuid.uuid4())


async def test_a_project_without_a_topic_stores_no_lessons(session):
    await seed_agent_profiles(session)
    project = Project(name="orphan", goal="do a thing")
    session.add(project)
    await session.commit()
    await plan_project(session, project.id, use_gates=False)
    await _clear_approvals(session, project)

    result = await run_project(session, project.id)
    assert result.lessons_stored == 0


async def test_the_final_summary_records_the_run_notes(session, project):
    """The artifact is the record; a note added after it is written is lost."""
    from sqlalchemy import select as sa_select

    await _clear_approvals(session, project)
    result = await run_project(session, project.id)

    final = (
        await session.scalars(
            sa_select(Artifact).where(Artifact.project_id == project.id, Artifact.type == "final_summary")
        )
    ).one()

    assert result.notes
    for note in result.notes:
        assert note in final.content
    assert "_none_" not in final.content.split("## Run notes")[1]


# --- concurrency ---


def test_waves_group_independent_work_together():
    """A security review and a QA strategy do not depend on each other; running
    them one after the other wastes a whole agent invocation of wall clock."""
    from app.orchestration.sdlc import order_waves

    a = _task("a")
    b = _task("b", ["a"])
    c = _task("c", ["a"])
    d = _task("d", ["b", "c"])

    waves = [[t.title for t in wave] for wave in order_waves([d, c, b, a])]
    assert waves == [["a"], ["c", "b"], ["d"]] or waves == [["a"], ["b", "c"], ["d"]]


def test_waves_still_terminate_on_a_cycle():
    from app.orchestration.sdlc import order_waves

    a, b = _task("a", ["b"]), _task("b", ["a"])
    waves = order_waves([a, b])
    assert sum(len(w) for w in waves) == 2


def test_ordering_is_unchanged_by_the_wave_refactor():
    a, b, c = _task("a"), _task("b", ["a"]), _task("c", ["b"])
    assert [t.title for t in order_tasks([c, b, a])] == ["a", "b", "c"]


async def test_independent_tasks_in_a_wave_run_concurrently(session, project):
    """The point of the refactor: proven by overlap, not by wall-clock timing."""
    import asyncio as aio

    from app.agents.runtime.base import AgentRunResult, AgentRuntime
    from app.agents.runtime.mock import MockAgentRuntime

    await _clear_approvals(session, project)

    active = 0
    peak = 0

    class SlowRuntime(AgentRuntime):
        name = "slow"

        async def run(self, agent_profile, input, context=None):  # noqa: ANN001
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            try:
                await aio.sleep(0.05)
                return await MockAgentRuntime().run(agent_profile, input, context)
            finally:
                active -= 1

    import app.orchestration.runs as runs_module

    original = runs_module.get_runtime
    runs_module.get_runtime = lambda: SlowRuntime()
    try:
        result = await run_project(session, project.id)
    finally:
        runs_module.get_runtime = original

    assert result.tasks_run > 0
    assert peak > 1, "independent tasks in a wave should overlap"
    assert isinstance(AgentRunResult(status="succeeded"), AgentRunResult)


async def test_concurrency_respects_the_configured_limit(session, project, monkeypatch):
    import asyncio as aio

    from app.agents.runtime.base import AgentRuntime
    from app.agents.runtime.mock import MockAgentRuntime
    from app.config import get_settings

    await _clear_approvals(session, project)
    monkeypatch.setattr(get_settings(), "sdlc_max_parallel_tasks", 2)

    active = 0
    peak = 0

    class SlowRuntime(AgentRuntime):
        name = "slow"

        async def run(self, agent_profile, input, context=None):  # noqa: ANN001
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            try:
                await aio.sleep(0.05)
                return await MockAgentRuntime().run(agent_profile, input, context)
            finally:
                active -= 1

    import app.orchestration.runs as runs_module

    original = runs_module.get_runtime
    runs_module.get_runtime = lambda: SlowRuntime()
    try:
        await run_project(session, project.id)
    finally:
        runs_module.get_runtime = original

    assert peak <= 2


async def test_a_transient_failure_is_retried_before_blocking(session, project, monkeypatch):
    """One timeout blocked a task and cascaded to six skipped dependents on a
    real run. A pass that fails once is usually transient."""
    from app.agents.runtime.base import AgentRunResult, AgentRuntime
    from app.agents.runtime.mock import MockAgentRuntime
    from app.config import get_settings

    await _clear_approvals(session, project)
    monkeypatch.setattr(get_settings(), "sdlc_task_retries", 1)

    failed_once: set[str] = set()

    class FlakyOnce(AgentRuntime):
        name = "flaky-once"

        async def run(self, agent_profile, input, context=None):  # noqa: ANN001
            key = str(input.get("instruction", ""))[:40]
            if key not in failed_once:
                failed_once.add(key)
                return AgentRunResult(status="failed", error="Claude Code timed out after 900s")
            return await MockAgentRuntime().run(agent_profile, input, context)

    import app.orchestration.runs as runs_module

    original = runs_module.get_runtime
    runs_module.get_runtime = lambda: FlakyOnce()
    try:
        result = await run_project(session, project.id)
    finally:
        runs_module.get_runtime = original

    # Every task failed its first attempt and succeeded on the retry.
    assert result.tasks_blocked == 0
    assert result.tasks_skipped == 0
    assert result.tasks_run >= 8


async def test_a_persistent_failure_still_blocks_and_says_how_many_tries(session, project, monkeypatch):
    from app.agents.runtime.base import AgentRunResult, AgentRuntime
    from app.config import get_settings

    await _clear_approvals(session, project)
    monkeypatch.setattr(get_settings(), "sdlc_task_retries", 2)

    class AlwaysFails(AgentRuntime):
        name = "always-fails"

        async def run(self, agent_profile, input, context=None):  # noqa: ANN001, ARG002
            return AgentRunResult(status="failed", error="provider unreachable")

    import app.orchestration.runs as runs_module

    original = runs_module.get_runtime
    runs_module.get_runtime = lambda: AlwaysFails()
    try:
        result = await run_project(session, project.id)
    finally:
        runs_module.get_runtime = original

    assert result.tasks_blocked > 0
    assert any("after 3 attempt(s)" in note for note in result.notes)
