"""Idempotent seeding of default rows."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.profiles import DEFAULT_AGENT_PROFILES
from app.db.models import AgentProfile

log = logging.getLogger(__name__)


async def seed_agent_profiles(session: AsyncSession) -> int:
    """Insert or update the default agent profiles. Returns rows written."""
    existing = {p.name: p for p in (await session.scalars(select(AgentProfile))).all()}
    written = 0

    for default in DEFAULT_AGENT_PROFILES:
        profile = existing.get(default.name)
        if profile is None:
            session.add(
                AgentProfile(
                    name=default.name,
                    role=default.role,
                    system_prompt=default.system_prompt,
                    allowed_tools_json=default.allowed_tools,
                    approval_rules_json=default.approval_rules,
                )
            )
            written += 1
            continue

        changed = (
            profile.role != default.role
            or profile.system_prompt != default.system_prompt
            or profile.allowed_tools_json != default.allowed_tools
            or profile.approval_rules_json != default.approval_rules
        )
        if changed:
            profile.role = default.role
            profile.system_prompt = default.system_prompt
            profile.allowed_tools_json = default.allowed_tools
            profile.approval_rules_json = default.approval_rules
            written += 1

    await session.commit()
    log.info("seeded agent profiles (%d written, %d total)", written, len(DEFAULT_AGENT_PROFILES))
    return written
