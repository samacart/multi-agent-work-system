"""System summary used by the dashboard shell."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import (
    AgentProfile,
    AgentRun,
    ApprovalRequest,
    Artifact,
    Memory,
    Project,
    Source,
    Task,
    Topic,
)
from app.db.session import get_session

router = APIRouter(prefix="/system", tags=["system"])

_COUNTED = {
    "topics": Topic,
    "sources": Source,
    "memories": Memory,
    "projects": Project,
    "tasks": Task,
    "agent_profiles": AgentProfile,
    "agent_runs": AgentRun,
    "approvals": ApprovalRequest,
    "artifacts": Artifact,
}


@router.get("/summary")
async def summary(session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    counts: dict[str, int] = {}
    for label, model in _COUNTED.items():
        counts[label] = int((await session.execute(select(func.count()).select_from(model))).scalar_one())

    settings = get_settings()
    return {
        "phase": 1,
        "phase_name": "Working Skeleton",
        "app": settings.app_name,
        "env": settings.app_env,
        "agent_runtime": settings.agent_runtime,
        "counts": counts,
    }
