"""The SDLC execution loop.

Walks a planned project's tasks in dependency order, runs each one through its
specialist agent, collects verification evidence and review findings, produces
the delivery artifacts, and writes back what was learned.

Two rules shape everything here:

1. A task is only verified by evidence. A pass finishing moves work to `review`,
   never past it. Promotion to `verified`/`done` needs QA evidence saying each
   acceptance criterion was met and no blocking review finding. With the mock
   runtime nothing can actually be executed, so evidence comes back
   `unverified` and work correctly stalls at review - the loop reports that
   rather than pretending.

2. Unresolved approval gates block the roles that would act on them. Approve
   the gate and re-run; the loop picks up where it stopped.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.contracts import ReleaseSummary, ReviewReport, TestReport
from app.agents.runtime.base import AgentContext
from app.artifacts.service import bullets, upsert_artifact
from app.config import get_settings
from app.db.models import ApprovalRequest, Memory, Project, Task
from app.ingestion.chunk import content_hash
from app.memory.embeddings import get_embedding_provider
from app.orchestration.runs import AgentRunFailed, execute_run
from app.projects.planning import gather_context
from app.orchestration.workspace import read_workspace_diff
from app.projects.tasks import check_transition, path_to

log = logging.getLogger(__name__)

# Which structured output each role produces for a task pass.
ROLE_TASKS: dict[str, str] = {
    "lead_pm": "task_outcome",
    "domain_expert": "task_outcome",
    "architect": "task_outcome",
    "developer": "task_outcome",
    "qa": "test_report",
    "code_reviewer": "review_report",
    "security_reviewer": "security_report",
    "release_manager": "release_summary",
}

# Reports that become artifacts.
TASK_ARTIFACTS: dict[str, str] = {
    "test_report": "test_report",
    "review_report": "review_report",
    "security_report": "security_report",
}

# Roles whose work is what an approval gate exists to control.
GATED_ROLES = {"developer", "architect", "release_manager"}

# Roles that must judge the actual change, not a description of it.
DIFF_READING_ROLES = {"qa", "code_reviewer", "security_reviewer", "release_manager"}

TERMINAL_STATUSES = {"done"}


@dataclass
class SdlcResult:
    project_id: str
    status: str
    tasks_run: int = 0
    tasks_verified: int = 0
    tasks_done: int = 0
    tasks_blocked: int = 0
    tasks_skipped: int = 0
    runs: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    findings: int = 0
    blocking_findings: int = 0
    lessons_stored: int = 0
    notes: list[str] = field(default_factory=list)
    error: str | None = None

    def as_dict(self) -> dict:
        return self.__dict__.copy()


class SdlcError(Exception):
    pass


def order_waves(tasks: list[Task]) -> list[list[Task]]:
    """Group tasks into dependency waves.

    Everything in a wave has all of its dependencies satisfied by earlier waves,
    so a wave can run concurrently. A security review and a QA strategy do not
    depend on each other, and running them one after the other wastes minutes
    per pass when each pass is a whole agent invocation.

    A dependency cycle - or a dependency on a task that no longer exists - must
    not hang or drop work, so anything unresolved becomes a final wave.
    """
    known_titles = {task.title for task in tasks}
    waves: list[list[Task]] = []
    # Keyed by title, not id: ids are unset until flush, and titles are what
    # dependencies are declared against anyway.
    placed: set[str] = set()

    remaining = list(tasks)
    while remaining:
        wave = [
            task
            for task in remaining
            if all(
                d in placed
                for d in ((task.metadata_json or {}).get("depends_on", []))
                if d in known_titles
            )
        ]
        if not wave:
            # Cycle or unsatisfiable dependency: run the rest in creation order.
            waves.append(remaining)
            break
        waves.append(wave)
        placed.update(task.title for task in wave)
        remaining = [task for task in remaining if task not in wave]
    return waves


def order_tasks(tasks: list[Task]) -> list[Task]:
    """Topological order by declared dependencies, stable by creation order."""
    return [task for wave in order_waves(tasks) for task in wave]


async def _pending_approvals(session: AsyncSession, project_id: uuid.UUID) -> list[ApprovalRequest]:
    return list(
        (
            await session.scalars(
                select(ApprovalRequest).where(
                    ApprovalRequest.project_id == project_id, ApprovalRequest.status == "pending"
                )
            )
        ).all()
    )


def _advance(task: Task, target: str) -> None:
    """Walk a task to `target` along the shortest legal route.

    Re-running picks tasks up wherever the last run left them, so the route is
    computed from the current status rather than assumed.
    """
    for step in path_to(task.status, target):
        check_transition(task.status, step)
        task.status = step


async def run_project(session: AsyncSession, project_id: uuid.UUID) -> SdlcResult:
    project = await session.get(Project, project_id)
    if project is None:
        raise SdlcError(f"Project {project_id} not found")

    tasks = list((await session.scalars(select(Task).where(Task.project_id == project_id))).all())
    if not tasks:
        raise SdlcError("Project has no tasks. Run planning first.")

    result = SdlcResult(project_id=str(project.id), status="running")
    project.status = "running"
    await session.commit()

    base_context, _memories = await gather_context(session, project)

    settings = get_settings()
    workspace_diff = await read_workspace_diff(
        settings.claude_code_cwd or None, max_chars=settings.review_diff_max_chars
    )
    if workspace_diff.available and not workspace_diff.is_empty:
        result.notes.append(
            f"Review passes read the workspace diff: {len(workspace_diff.changed_files)} modified, "
            f"{len(workspace_diff.new_files)} new file(s)"
        )
    elif not workspace_diff.available:
        result.notes.append(f"Review passes have no diff to read - {workspace_diff.reason}")

    pending = await _pending_approvals(session, project_id)
    if pending:
        result.notes.append(
            f"{len(pending)} approval gate(s) pending: "
            + ", ".join(sorted({a.action_type for a in pending}))
        )

    blocked_titles: set[str] = set()
    reports: dict[str, object] = {}
    limit = max(1, get_settings().sdlc_max_parallel_tasks)
    semaphore = asyncio.Semaphore(limit)
    maker = _session_factory(session)

    # Snapshot what a task pass needs, so concurrent passes do not touch the
    # caller's session: an AsyncSession is not safe to share across tasks.
    all_criteria = sorted({c for t in tasks for c in t.acceptance_criteria})

    for wave in order_waves(tasks):
        runnable: list[Task] = []
        for task in wave:
            if task.status in TERMINAL_STATUSES:
                result.tasks_skipped += 1
                continue

            depends = (task.metadata_json or {}).get("depends_on", [])
            if any(title in blocked_titles for title in depends):
                blocked_titles.add(task.title)
                result.tasks_skipped += 1
                result.notes.append(f"Skipped '{task.title}': a task it depends on did not complete")
                continue

            role = task.agent_role or "developer"
            if pending and role in GATED_ROLES:
                _advance(task, "blocked")
                blocked_titles.add(task.title)
                result.tasks_blocked += 1
                result.notes.append(
                    f"Blocked '{task.title}': {role} work needs the pending approval gate(s) answered first"
                )
                continue

            runnable.append(task)

        await session.commit()
        if not runnable:
            continue

        done_titles = [t.title for t in tasks if t.status in {"verified", "done"}]
        outcomes = await asyncio.gather(
            *(
                _run_task_isolated(
                    semaphore,
                    maker,
                    project_id=project.id,
                    task_id=task.id,
                    base_context=base_context,
                    all_criteria=all_criteria,
                    completed_titles=done_titles,
                    workspace_diff=workspace_diff,
                )
                for task in runnable
            )
        )

        # Concurrent passes advanced these rows in their own sessions. Every
        # task object this session holds is now stale, including ones from
        # earlier waves - and writing to a stale object flushes its whole row,
        # silently reverting a status another session just set.
        #
        # Reloaded eagerly rather than expired: expiring defers the read to the
        # next attribute access, which happens in sync context and raises
        # MissingGreenlet.
        await session.execute(
            select(Task).where(Task.project_id == project_id).execution_options(populate_existing=True)
        )

        for task, outcome in zip(runnable, outcomes):
            if outcome.error is not None:
                blocked_titles.add(task.title)
                result.tasks_blocked += 1
                result.notes.append(f"Blocked '{task.title}': agent run failed - {outcome.error}")
                continue

            result.runs.append(outcome.run_id)
            result.tasks_run += 1
            reports[outcome.agent_task] = outcome.output
            if outcome.artifact_type:
                result.artifacts.append(outcome.artifact_type)
            if outcome.agent_task == "test_report":
                await _attach_evidence(session, tasks, outcome.output)

    review: ReviewReport | None = reports.get("review_report")  # type: ignore[assignment]
    security: ReviewReport | None = reports.get("security_report")  # type: ignore[assignment]
    for report in (review, security):
        if report is not None:
            result.findings += len(report.findings)
            if report.blocking:
                result.blocking_findings += sum(1 for f in report.findings if f.severity == "high")

    await _promote_verified_tasks(session, tasks, blocking=result.blocking_findings > 0, result=result)

    # Note this before the release pass: the final summary embeds the run notes,
    # so anything added afterwards would be missing from the artifact.
    awaiting = sum(1 for t in tasks if t.status == "review")
    if awaiting:
        result.notes.append(
            f"{awaiting} task(s) are awaiting verification evidence; nothing is marked done without it"
        )

    release = await _run_release_pass(session, project, base_context, tasks, result, workspace_diff)
    if release is not None:
        result.lessons_stored = await _store_lessons(session, project, release, review, security)

    await session.commit()
    result.status = await _finalise_project_status(session, project, tasks, result)
    log.info(
        "sdlc run for %s: status=%s runs=%d verified=%d blocked=%d",
        project.name,
        result.status,
        result.tasks_run,
        result.tasks_verified,
        result.tasks_blocked,
    )
    return result


@dataclass
class _TaskOutcome:
    agent_task: str
    run_id: str = ""
    output: object = None
    artifact_type: str | None = None
    error: str | None = None


def _session_factory(session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    """A factory bound to the caller's own engine.

    Concurrent passes need their own sessions, but they must be on the same
    engine as the caller - reaching for the global one silently talks to a
    different database whenever the caller was handed a session (dependency
    override, test fixture, worker).
    """
    bind = session.bind
    if bind is None:  # pragma: no cover - a session is always bound in practice
        from app.db.session import get_sessionmaker

        return get_sessionmaker()
    return async_sessionmaker(bind, expire_on_commit=False)


async def _run_task_isolated(
    semaphore: asyncio.Semaphore,
    maker: async_sessionmaker[AsyncSession],
    project_id: uuid.UUID,
    task_id: uuid.UUID,
    base_context: AgentContext,
    all_criteria: list[str],
    completed_titles: list[str],
    workspace_diff=None,  # noqa: ANN001 - WorkspaceDiff
) -> _TaskOutcome:
    """Run one task pass in its own session, so a wave can run concurrently."""
    async with semaphore, maker() as session:
        task = await session.get(Task, task_id)
        project = await session.get(Project, project_id)
        if task is None or project is None:
            return _TaskOutcome(agent_task="task_outcome", error="task or project vanished mid-run")

        role = task.agent_role or "developer"
        agent_task = ROLE_TASKS.get(role, "task_outcome")
        # Reviewers and QA judge the change; everyone else would only be
        # distracted by sixty thousand characters of patch.
        diff_context = (
            workspace_diff.as_context() if workspace_diff is not None and role in DIFF_READING_ROLES else {}
        )
        context = AgentContext(
            project_id=str(project_id),
            task_id=str(task_id),
            memories=base_context.memories,
            extra={
                **base_context.extra,
                **diff_context,
                "task_title": task.title,
                "task_role": role,
                # QA verifies the whole project's criteria, not just its own.
                "acceptance_criteria": all_criteria if role == "qa" else list(task.acceptance_criteria),
                "completed_tasks": completed_titles,
            },
        )

        _advance(task, "in_progress")
        await session.commit()

        # A pass that fails is usually transient - a timeout on a long read -
        # and blocking on the first failure takes every dependent task with it.
        attempts = max(1, get_settings().sdlc_task_retries + 1)
        outcome = None
        last_error = ""
        for attempt in range(1, attempts + 1):
            try:
                outcome = await execute_run(
                    session,
                    role=role,
                    task=agent_task,
                    instruction=f"{task.title}. {task.description or ''}".strip(),
                    context=context,
                    project_id=project_id,
                    task_id=task_id,
                )
                break
            except AgentRunFailed as exc:
                last_error = str(exc)
                log.warning(
                    "task pass '%s' failed on attempt %d of %d: %s", task.title, attempt, attempts, exc
                )

        if outcome is None:
            _advance(task, "blocked")
            await session.commit()
            return _TaskOutcome(
                agent_task=agent_task, error=f"{last_error} (after {attempts} attempt(s))"
            )

        artifact_type = TASK_ARTIFACTS.get(agent_task)
        if artifact_type:
            await _write_report_artifact(session, project, task, artifact_type, outcome.output)

        _advance(task, "review")
        await session.commit()
        return _TaskOutcome(
            agent_task=agent_task,
            run_id=str(outcome.run.id),
            output=outcome.output,
            artifact_type=artifact_type,
        )


def _task_context(base: AgentContext, project: Project, task: Task, tasks: list[Task]) -> AgentContext:
    return AgentContext(
        project_id=str(project.id),
        task_id=str(task.id),
        memories=base.memories,
        extra={
            **base.extra,
            "task_title": task.title,
            "task_role": task.agent_role,
            # QA verifies the whole project's criteria, not just its own task's.
            "acceptance_criteria": (
                sorted({c for t in tasks for c in t.acceptance_criteria})
                if task.agent_role == "qa"
                else list(task.acceptance_criteria)
            ),
            "completed_tasks": [t.title for t in tasks if t.status in {"verified", "done"}],
        },
    )


async def _write_report_artifact(
    session: AsyncSession, project: Project, task: Task, artifact_type: str, report
) -> None:  # noqa: ANN001
    if isinstance(report, TestReport):
        lines = [
            f"**{e.criterion}** - `{e.verdict}` - {e.evidence or 'no evidence recorded'}" for e in report.evidence
        ]
        content = f"""# Test report - {project.name}

{report.summary}

## Strategy
{bullets(report.strategy)}

## Evidence
{bullets(lines, "_no acceptance criteria to verify_")}

## Missing coverage
{bullets(report.missing_coverage, "_none identified_")}

## Manual steps
{bullets(report.manual_steps)}
"""
    else:
        findings = [
            f"**{f.severity}** - {f.title}\n  - evidence: {f.evidence or 'none'}\n  - fix: {f.suggested_fix or 'none'}"
            for f in report.findings
        ]
        heading = "Security report" if artifact_type == "security_report" else "Review report"
        content = f"""# {heading} - {project.name}

{report.summary}

Blocking: {"yes" if report.blocking else "no"}

## Findings
{bullets(findings, "_no findings_")}
"""
    await upsert_artifact(session, project.id, artifact_type, f"{artifact_type} - {project.name}", content, task.id)


async def _attach_evidence(session: AsyncSession, tasks: list[Task], report: TestReport) -> None:
    """Route each evidence entry back to the tasks that own that criterion."""
    by_criterion: dict[str, list[Task]] = {}
    for task in tasks:
        for criterion in task.acceptance_criteria:
            by_criterion.setdefault(criterion, []).append(task)

    for entry in report.evidence:
        for task in by_criterion.get(entry.criterion, []):
            existing = [e for e in (task.evidence or []) if e.get("criterion") != entry.criterion]
            task.evidence = [*existing, entry.model_dump(mode="json")]
    await session.commit()


def _all_criteria_met(task: Task) -> bool:
    if not task.acceptance_criteria:
        return False
    verdicts = {e.get("criterion"): e.get("verdict") for e in (task.evidence or []) if isinstance(e, dict)}
    return all(verdicts.get(c) == "met" for c in task.acceptance_criteria)


async def _promote_verified_tasks(
    session: AsyncSession, tasks: list[Task], blocking: bool, result: SdlcResult
) -> None:
    """Move reviewed work forward only where the evidence supports it."""
    for task in tasks:
        if task.status != "review":
            continue
        if not _all_criteria_met(task):
            continue
        if blocking:
            result.notes.append(f"'{task.title}' met its criteria but a blocking finding is unresolved")
            continue
        _advance(task, "verified")
        result.tasks_verified += 1
        _advance(task, "done")
        result.tasks_done += 1
    await session.commit()


async def _run_release_pass(
    session: AsyncSession,
    project: Project,
    base: AgentContext,
    tasks: list[Task],
    result: SdlcResult,
    workspace_diff=None,  # noqa: ANN001 - WorkspaceDiff
) -> ReleaseSummary | None:
    """Always runs: it summarises what actually happened, including shortfalls."""
    context = AgentContext(
        project_id=str(project.id),
        memories=base.memories,
        extra={
            **base.extra,
            **(workspace_diff.as_context() if workspace_diff is not None else {}),
            "completed_tasks": [t.title for t in tasks if t.status == "done"],
        },
    )
    try:
        outcome = await execute_run(
            session,
            role="release_manager",
            task="release_summary",
            instruction="Summarise delivery: release notes, rollout, risks, lessons.",
            context=context,
            project_id=project.id,
        )
    except AgentRunFailed as exc:
        result.notes.append(f"Release pass failed: {exc}")
        return None

    result.runs.append(str(outcome.run.id))
    summary: ReleaseSummary = outcome.output  # type: ignore[assignment]

    notes = f"""# Release notes - {project.name}

{summary.summary}

## What changed
{bullets(summary.release_notes)}

## Rollout checklist
{bullets(summary.rollout_checklist)}

## Migration notes
{bullets(summary.migration_notes, "_none_")}
"""
    outstanding = [t.title for t in tasks if t.status != "done"]
    final = f"""# Final summary - {project.name}

{summary.summary}

## Goal
{project.goal or "_not stated_"}

## Completed
{bullets([t.title for t in tasks if t.status == "done"], "_nothing completed_")}

## Outstanding
{bullets(outstanding, "_nothing outstanding_")}

## Operational risks
{bullets(summary.operational_risks, "_none identified_")}

## Monitoring
{bullets(summary.monitoring)}

## Lessons learned
{bullets(summary.lessons, "_none recorded_")}

## Run notes
{bullets(result.notes, "_none_")}
"""
    await upsert_artifact(session, project.id, "release_notes", f"Release notes - {project.name}", notes)
    await upsert_artifact(session, project.id, "final_summary", f"Final summary - {project.name}", final)
    result.artifacts.extend(["release_notes", "final_summary"])
    return summary


async def _store_lessons(
    session: AsyncSession,
    project: Project,
    release: ReleaseSummary,
    review: ReviewReport | None,
    security: ReviewReport | None,
) -> int:
    """Write what this project learned back to topic memory.

    This is the loop that makes the second project on a topic cheaper than the
    first. Lessons are scoped to the project but stored on the topic, and
    deduplicated against everything the topic already knows.
    """
    if project.topic_id is None:
        return 0

    candidates: list[tuple[str, str]] = [("lesson", text) for text in release.lessons]
    for report, label in ((review, "review"), (security, "security")):
        if report is None:
            continue
        for finding in report.findings:
            if finding.severity == "high":
                candidates.append(("gotcha", f"{label} flagged on {project.name}: {finding.title}"))

    if not candidates:
        return 0

    known = {
        content_hash(c)
        for c in (await session.scalars(select(Memory.content).where(Memory.topic_id == project.topic_id))).all()
    }
    fresh = []
    for type_, content in candidates:
        digest = content_hash(content)
        if digest in known:
            continue
        known.add(digest)
        fresh.append((type_, content))

    if not fresh:
        return 0

    provider = get_embedding_provider()
    vectors = await provider.embed([content for _type, content in fresh])
    for (type_, content), vector in zip(fresh, vectors):
        session.add(
            Memory(
                topic_id=project.topic_id,
                project_id=project.id,
                type=type_,
                content=content,
                confidence=0.7,
                importance=0.7,
                metadata_json={"source_quote": content, "origin": "sdlc_run", "project": project.name},
                embedding=vector,
            )
        )
    await session.commit()
    return len(fresh)


async def _finalise_project_status(
    session: AsyncSession, project: Project, tasks: list[Task], result: SdlcResult
) -> str:
    for task in tasks:
        await session.refresh(task)

    if all(t.status == "done" for t in tasks):
        project.status = "delivered"
    elif any(t.status == "blocked" for t in tasks):
        project.status = "blocked"
    else:
        project.status = "review"
    await session.commit()
    return project.status
