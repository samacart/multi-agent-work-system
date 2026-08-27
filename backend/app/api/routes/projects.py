"""Projects, tasks, runs, artifacts, approvals, and decisions."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    AgentRunOut,
    ApprovalOut,
    ApprovalResponse,
    ArtifactOut,
    DecisionAnswer,
    DecisionCreate,
    DecisionOut,
    ProjectCreate,
    ProjectDetailOut,
    ProjectOut,
    TaskCreate,
    TaskOut,
    TaskUpdate,
)
from app.approvals.service import answer_question, respond_to_approval
from app.db.models import (
    AGENT_ROLES,
    TASK_STATUSES,
    AgentRun,
    ApprovalRequest,
    Artifact,
    Decision,
    Project,
    Task,
    Topic,
)
from app.db.session import get_session
from app.projects.planning import PlanningError, plan_project
from app.projects.tasks import InvalidTransition, check_transition

router = APIRouter(tags=["projects"])


async def _get_project_or_404(session: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("/projects", response_model=ProjectOut, status_code=201)
async def create_project(payload: ProjectCreate, session: AsyncSession = Depends(get_session)) -> Project:
    if payload.topic_id is not None and await session.get(Topic, payload.topic_id) is None:
        raise HTTPException(status_code=404, detail="Topic not found")

    project = Project(
        topic_id=payload.topic_id, name=payload.name.strip(), goal=payload.goal, status="draft"
    )
    session.add(project)
    await session.commit()
    return project


@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(session: AsyncSession = Depends(get_session)) -> list[Project]:
    return list((await session.scalars(select(Project).order_by(Project.created_at.desc()))).all())


@router.get("/projects/{project_id}", response_model=ProjectDetailOut)
async def get_project(project_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> ProjectDetailOut:
    project = await _get_project_or_404(session, project_id)
    topic = await session.get(Topic, project.topic_id) if project.topic_id else None

    status_rows = (
        await session.execute(
            select(Task.status, func.count()).where(Task.project_id == project_id).group_by(Task.status)
        )
    ).all()

    async def count(model, *conditions) -> int:  # noqa: ANN001
        return int((await session.execute(select(func.count()).select_from(model).where(*conditions))).scalar_one())

    return ProjectDetailOut(
        id=project.id,
        topic_id=project.topic_id,
        name=project.name,
        goal=project.goal,
        status=project.status,
        brief=project.brief,
        created_at=project.created_at,
        updated_at=project.updated_at,
        topic_name=topic.name if topic else None,
        task_counts={row[0]: int(row[1]) for row in status_rows},
        run_count=await count(AgentRun, AgentRun.project_id == project_id),
        artifact_count=await count(Artifact, Artifact.project_id == project_id),
        open_questions=await count(Decision, Decision.project_id == project_id, Decision.answer.is_(None)),
        pending_approvals=await count(
            ApprovalRequest, ApprovalRequest.project_id == project_id, ApprovalRequest.status == "pending"
        ),
    )


@router.post("/projects/{project_id}/plan")
async def run_planning(
    project_id: uuid.UUID, response: Response, session: AsyncSession = Depends(get_session)
) -> dict:
    await _get_project_or_404(session, project_id)
    try:
        result = await plan_project(session, project_id)
    except PlanningError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if result.status == "failed":
        # The failure is recorded on the project and its runs; report it as data.
        response.status_code = 422
    return result.as_dict()


@router.get("/projects/{project_id}/tasks", response_model=list[TaskOut])
async def list_tasks(
    project_id: uuid.UUID,
    status: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[Task]:
    await _get_project_or_404(session, project_id)
    stmt = select(Task).where(Task.project_id == project_id)
    if status:
        if status not in TASK_STATUSES:
            raise HTTPException(status_code=422, detail=f"status must be one of: {', '.join(TASK_STATUSES)}")
        stmt = stmt.where(Task.status == status)
    return list((await session.scalars(stmt.order_by(Task.created_at))).all())


@router.post("/projects/{project_id}/tasks", response_model=TaskOut, status_code=201)
async def create_task(
    project_id: uuid.UUID, payload: TaskCreate, session: AsyncSession = Depends(get_session)
) -> Task:
    await _get_project_or_404(session, project_id)
    if payload.agent_role and payload.agent_role not in AGENT_ROLES:
        raise HTTPException(status_code=422, detail=f"agent_role must be one of: {', '.join(AGENT_ROLES)}")

    task = Task(
        project_id=project_id,
        parent_task_id=payload.parent_task_id,
        title=payload.title.strip(),
        description=payload.description,
        agent_role=payload.agent_role,
        status="backlog",
        acceptance_criteria=payload.acceptance_criteria,
    )
    session.add(task)
    await session.commit()
    return task


@router.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: uuid.UUID, payload: TaskUpdate, session: AsyncSession = Depends(get_session)
) -> Task:
    task = await session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    if payload.status is not None:
        if payload.status not in TASK_STATUSES:
            raise HTTPException(status_code=422, detail=f"status must be one of: {', '.join(TASK_STATUSES)}")
        try:
            check_transition(task.status, payload.status)
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        task.status = payload.status

    if payload.agent_role is not None:
        if payload.agent_role not in AGENT_ROLES:
            raise HTTPException(status_code=422, detail=f"agent_role must be one of: {', '.join(AGENT_ROLES)}")
        task.agent_role = payload.agent_role

    for field in ("title", "description", "acceptance_criteria", "evidence"):
        value = getattr(payload, field)
        if value is not None:
            setattr(task, field, value)

    await session.commit()
    return task


@router.get("/projects/{project_id}/runs", response_model=list[AgentRunOut])
async def list_runs(project_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> list[AgentRun]:
    await _get_project_or_404(session, project_id)
    return list(
        (
            await session.scalars(
                select(AgentRun).where(AgentRun.project_id == project_id).order_by(AgentRun.created_at.desc())
            )
        ).all()
    )


@router.get("/projects/{project_id}/artifacts", response_model=list[ArtifactOut])
async def list_artifacts(project_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> list[Artifact]:
    await _get_project_or_404(session, project_id)
    return list(
        (
            await session.scalars(
                select(Artifact).where(Artifact.project_id == project_id).order_by(Artifact.created_at)
            )
        ).all()
    )


@router.get("/projects/{project_id}/approvals", response_model=list[ApprovalOut])
async def list_approvals(
    project_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[ApprovalRequest]:
    await _get_project_or_404(session, project_id)
    return list(
        (
            await session.scalars(
                select(ApprovalRequest)
                .where(ApprovalRequest.project_id == project_id)
                .order_by(ApprovalRequest.created_at)
            )
        ).all()
    )


@router.post("/approvals/{approval_id}/respond", response_model=ApprovalOut)
async def respond_approval(
    approval_id: uuid.UUID, payload: ApprovalResponse, session: AsyncSession = Depends(get_session)
) -> ApprovalRequest:
    try:
        return await respond_to_approval(session, approval_id, payload.status, payload.response)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/projects/{project_id}/decisions", response_model=list[DecisionOut])
async def list_decisions(project_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> list[Decision]:
    await _get_project_or_404(session, project_id)
    return list(
        (
            await session.scalars(
                select(Decision).where(Decision.project_id == project_id).order_by(Decision.created_at)
            )
        ).all()
    )


@router.post("/projects/{project_id}/decisions", response_model=DecisionOut, status_code=201)
async def create_decision(
    project_id: uuid.UUID, payload: DecisionCreate, session: AsyncSession = Depends(get_session)
) -> Decision:
    await _get_project_or_404(session, project_id)
    decision = Decision(
        project_id=project_id,
        question=payload.question,
        answer=payload.answer,
        rationale=payload.rationale,
        decided_by=payload.decided_by,
    )
    session.add(decision)
    await session.commit()
    return decision


@router.post("/decisions/{decision_id}/answer", response_model=DecisionOut)
async def answer_decision(
    decision_id: uuid.UUID, payload: DecisionAnswer, session: AsyncSession = Depends(get_session)
) -> Decision:
    try:
        return await answer_question(session, decision_id, payload.answer, payload.decided_by, payload.rationale)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
