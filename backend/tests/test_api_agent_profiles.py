"""Agent profile API."""

from __future__ import annotations

from app.agents.profiles import DEFAULT_AGENT_PROFILES
from app.db.seed import seed_agent_profiles


async def test_list_agent_profiles_is_empty_before_seeding(client):
    response = await client.get("/agent-profiles")
    assert response.status_code == 200
    assert response.json() == []


async def test_list_agent_profiles_after_seeding(client, session):
    await seed_agent_profiles(session)

    response = await client.get("/agent-profiles")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == len(DEFAULT_AGENT_PROFILES)
    assert [p["name"] for p in body] == sorted(p["name"] for p in body)

    first = body[0]
    detail = await client.get(f"/agent-profiles/{first['id']}")
    assert detail.status_code == 200
    assert detail.json()["system_prompt"] == first["system_prompt"]


async def test_unknown_agent_profile_returns_404(client):
    response = await client.get("/agent-profiles/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


async def test_system_summary_counts_rows(client, session):
    await seed_agent_profiles(session)
    response = await client.get("/system/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["phase"] == 1
    assert body["counts"]["agent_profiles"] == len(DEFAULT_AGENT_PROFILES)
    assert body["counts"]["topics"] == 0
