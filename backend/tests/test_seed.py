"""Default agent profile seeding."""

from __future__ import annotations

from sqlalchemy import select

from app.agents.profiles import DEFAULT_AGENT_PROFILES
from app.db.models import AgentProfile
from app.db.seed import seed_agent_profiles


async def test_seeding_creates_every_default_profile(session):
    written = await seed_agent_profiles(session)
    assert written == len(DEFAULT_AGENT_PROFILES)

    profiles = (await session.scalars(select(AgentProfile))).all()
    assert {p.name for p in profiles} == {d.name for d in DEFAULT_AGENT_PROFILES}
    assert {p.role for p in profiles} >= {
        "lead_pm",
        "architect",
        "developer",
        "qa",
        "code_reviewer",
        "security_reviewer",
        "domain_expert",
        "release_manager",
    }
    assert all(p.system_prompt.strip() for p in profiles)


async def test_seeding_is_idempotent(session):
    await seed_agent_profiles(session)
    written = await seed_agent_profiles(session)
    assert written == 0
    assert len((await session.scalars(select(AgentProfile))).all()) == len(DEFAULT_AGENT_PROFILES)


async def test_seeding_updates_a_changed_prompt(session):
    await seed_agent_profiles(session)
    profile = (await session.scalars(select(AgentProfile).where(AgentProfile.name == "Architect"))).one()
    profile.system_prompt = "stale prompt"
    await session.commit()

    written = await seed_agent_profiles(session)
    assert written == 1

    refreshed = (await session.scalars(select(AgentProfile).where(AgentProfile.name == "Architect"))).one()
    assert refreshed.system_prompt.startswith("You are the Architect agent.")


async def test_default_profiles_carry_approval_rules(session):
    await seed_agent_profiles(session)
    pm = (await session.scalars(select(AgentProfile).where(AgentProfile.name == "Lead PM"))).one()
    rules = pm.approval_rules_json
    assert "merge_pr" in rules["requires_approval"]
    assert "change_database_schema" in rules["requires_approval"]
    assert "semantic_search" in rules["auto_approved"]
