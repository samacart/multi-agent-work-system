"""Read-only view of seeded agent profiles."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentProfile
from app.db.session import get_session

router = APIRouter(prefix="/agent-profiles", tags=["agents"])


class AgentProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    role: str
    system_prompt: str
    allowed_tools_json: list
    approval_rules_json: dict
    created_at: datetime
    updated_at: datetime


@router.get("", response_model=list[AgentProfileOut])
async def list_agent_profiles(session: AsyncSession = Depends(get_session)) -> list[AgentProfile]:
    return list((await session.scalars(select(AgentProfile).order_by(AgentProfile.name))).all())


@router.get("/{profile_id}", response_model=AgentProfileOut)
async def get_agent_profile(profile_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> AgentProfile:
    profile = await session.get(AgentProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Agent profile not found")
    return profile
