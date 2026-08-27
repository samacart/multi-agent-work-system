"""GitHub delivery endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.approvals.service import ApprovalRequired
from app.config import get_settings
from app.db.models import Project
from app.db.session import get_session
from app.github.delivery import DeliveryError, branch_name, create_pull_request, generate_pr_description
from app.github.urls import InvalidGitHubReference

router = APIRouter(tags=["github"])


class PrDescriptionRequest(BaseModel):
    base: str = Field(default="main", description="Branch the PR would target")


class PullRequestRequest(BaseModel):
    repo: str = Field(description="owner/repo, or any GitHub repository URL")
    base: str = "main"
    head: str | None = Field(default=None, description="Defaults to the project's planned branch")


@router.get("/github/status")
async def github_status() -> dict:
    """Whether the integration is usable, without revealing the token."""
    settings = get_settings()
    return {
        "enabled": settings.github_enabled,
        "authenticated": bool(settings.github_token),
        "writes_enabled": settings.github_allow_writes,
        "api_url": settings.github_api_url,
        "supported_source_types": ["github_repo", "github_issue", "github_pr"],
    }


@router.get("/projects/{project_id}/branch")
async def planned_branch(project_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> dict:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"branch": branch_name(project), "project": project.name}


@router.post("/projects/{project_id}/pr-description")
async def pr_description(
    project_id: uuid.UUID,
    payload: PrDescriptionRequest | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    base = (payload or PrDescriptionRequest()).base
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        artifact, description = await generate_pr_description(session, project_id, base)
    except DeliveryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "artifact_id": str(artifact.id),
        "title": description.title,
        "branch": branch_name(project),
        "base": base,
        "content": artifact.content,
    }


@router.post("/projects/{project_id}/pull-request")
async def open_pull_request(
    project_id: uuid.UUID, payload: PullRequestRequest, session: AsyncSession = Depends(get_session)
) -> dict:
    try:
        return await create_pull_request(session, project_id, payload.repo, payload.base, payload.head)
    except ApprovalRequired as exc:
        # Not an error: a human has to answer this first.
        raise HTTPException(
            status_code=409,
            detail={
                "message": str(exc),
                "approval_id": str(exc.approval.id),
                "status": exc.approval.status,
            },
        ) from exc
    except InvalidGitHubReference as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DeliveryError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc) else 422, detail=str(exc)) from exc
