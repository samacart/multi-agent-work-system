"""Projects, tasks, runs, artifacts, approvals, and decisions over the API."""

from __future__ import annotations

import pytest

from app.db.seed import seed_agent_profiles

NOTES = """
We decided that invite links expire after 14 days.
Invites must not be reusable once an account is created.
There is a risk that expired invites fail silently and the user sees a blank page.
The invite service writes to the invites table and calls the billing API.
Who owns the reminder email copy?
"""


@pytest.fixture
async def seeded(client, session):
    await seed_agent_profiles(session)
    topic = (await client.post("/topics", json={"name": "customer onboarding"})).json()
    source = (
        await client.post(
            f"/topics/{topic['id']}/sources",
            json={"type": "pasted_text", "name": "kickoff", "text": NOTES},
        )
    ).json()
    await client.post(f"/sources/{source['id']}/ingest?mode=sync")
    project = (
        await client.post(
            "/projects",
            json={
                "name": "self-serve onboarding",
                "goal": "let an organisation sign up and invite teammates without support",
                "topic_id": topic["id"],
            },
        )
    ).json()
    return {"topic": topic, "project": project}


async def test_create_and_list_projects(client, seeded):
    listed = await client.get("/projects")
    assert listed.status_code == 200
    assert [p["id"] for p in listed.json()] == [seeded["project"]["id"]]
    assert seeded["project"]["status"] == "draft"


async def test_project_with_unknown_topic_is_rejected(client):
    response = await client.post(
        "/projects", json={"name": "x", "topic_id": "00000000-0000-0000-0000-000000000000"}
    )
    assert response.status_code == 404


async def test_planning_populates_the_whole_project(client, seeded):
    project_id = seeded["project"]["id"]

    planned = await client.post(f"/projects/{project_id}/plan")
    assert planned.status_code == 200
    result = planned.json()
    assert result["status"] == "ready"
    assert result["memories_used"] > 0
    assert result["tasks_created"] >= 8
    assert sorted(result["artifacts"]) == ["architecture_plan", "project_brief", "task_breakdown"]

    detail = (await client.get(f"/projects/{project_id}")).json()
    assert detail["status"] == "ready"
    assert detail["topic_name"] == "customer onboarding"
    assert detail["brief"].startswith("# self-serve onboarding")
    assert detail["run_count"] == 6
    assert detail["artifact_count"] == 3
    assert detail["open_questions"] > 0
    assert sum(detail["task_counts"].values()) == result["tasks_created"]

    tasks = (await client.get(f"/projects/{project_id}/tasks")).json()
    assert all(t["acceptance_criteria"] for t in tasks)

    runs = (await client.get(f"/projects/{project_id}/runs")).json()
    assert len(runs) == 6
    assert all(r["status"] == "succeeded" and r["output"] for r in runs)

    artifacts = (await client.get(f"/projects/{project_id}/artifacts")).json()
    assert {a["type"] for a in artifacts} == {"project_brief", "architecture_plan", "task_breakdown"}

    decisions = (await client.get(f"/projects/{project_id}/decisions")).json()
    assert any("reminder email copy" in d["question"] for d in decisions)

    approvals = (await client.get(f"/projects/{project_id}/approvals")).json()
    assert approvals
    assert all(a["status"] == "pending" for a in approvals)


async def test_task_status_transitions_over_the_api(client, seeded):
    project_id = seeded["project"]["id"]
    await client.post(f"/projects/{project_id}/plan")
    task = (await client.get(f"/projects/{project_id}/tasks?status=ready")).json()[0]

    ok = await client.patch(f"/tasks/{task['id']}", json={"status": "in_progress"})
    assert ok.status_code == 200
    assert ok.json()["status"] == "in_progress"

    skipped = await client.patch(f"/tasks/{task['id']}", json={"status": "done"})
    assert skipped.status_code == 409
    assert "Allowed from 'in_progress'" in skipped.json()["detail"]

    for status in ("review", "verified", "done"):
        response = await client.patch(f"/tasks/{task['id']}", json={"status": status})
        assert response.status_code == 200

    terminal = await client.patch(f"/tasks/{task['id']}", json={"status": "in_progress"})
    assert terminal.status_code == 409


async def test_task_evidence_can_be_attached(client, seeded):
    project_id = seeded["project"]["id"]
    await client.post(f"/projects/{project_id}/plan")
    task = (await client.get(f"/projects/{project_id}/tasks")).json()[0]

    response = await client.patch(
        f"/tasks/{task['id']}",
        json={"evidence": [{"criterion": "scope is written down", "verdict": "met", "evidence": "see brief"}]},
    )
    assert response.status_code == 200
    assert response.json()["evidence"][0]["verdict"] == "met"


async def test_manual_task_creation_and_validation(client, seeded):
    project_id = seeded["project"]["id"]

    created = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "Write the migration", "agent_role": "architect", "acceptance_criteria": ["applies cleanly"]},
    )
    assert created.status_code == 201
    assert created.json()["status"] == "backlog"

    bad_role = await client.post(
        f"/projects/{project_id}/tasks", json={"title": "x", "agent_role": "wizard"}
    )
    assert bad_role.status_code == 422


async def test_unknown_task_status_filter_is_rejected(client, seeded):
    response = await client.get(f"/projects/{seeded['project']['id']}/tasks?status=nonsense")
    assert response.status_code == 422


async def test_approval_can_be_answered_once(client, seeded):
    project_id = seeded["project"]["id"]
    await client.post(f"/projects/{project_id}/plan")
    approval = (await client.get(f"/projects/{project_id}/approvals")).json()[0]

    approved = await client.post(
        f"/approvals/{approval['id']}/respond", json={"status": "approved", "response": "go ahead"}
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    again = await client.post(f"/approvals/{approval['id']}/respond", json={"status": "rejected"})
    assert again.status_code == 409


async def test_decisions_can_be_raised_and_answered(client, seeded):
    project_id = seeded["project"]["id"]

    created = await client.post(
        f"/projects/{project_id}/decisions", json={"question": "Should invites be org-scoped?"}
    )
    assert created.status_code == 201
    assert created.json()["answer"] is None

    answered = await client.post(
        f"/decisions/{created.json()['id']}/answer",
        json={"answer": "Yes", "rationale": "matches the billing model", "decided_by": "sam"},
    )
    assert answered.status_code == 200
    assert answered.json()["answer"] == "Yes"
    assert answered.json()["decided_by"] == "sam"


async def test_planning_an_unknown_project_returns_404(client):
    response = await client.post("/projects/00000000-0000-0000-0000-000000000000/plan")
    assert response.status_code == 404


async def test_failed_planning_reports_422(client, seeded, monkeypatch):
    from app.agents.runtime.base import AgentRunResult, AgentRuntime

    class BrokenRuntime(AgentRuntime):
        name = "broken"

        async def run(self, agent_profile, input, context=None):  # noqa: ANN001, ARG002
            return AgentRunResult(status="failed", error="provider unreachable")

    monkeypatch.setattr("app.orchestration.runs.get_runtime", lambda: BrokenRuntime())
    response = await client.post(f"/projects/{seeded['project']['id']}/plan")
    assert response.status_code == 422
    assert response.json()["status"] == "failed"

    detail = (await client.get(f"/projects/{seeded['project']['id']}")).json()
    assert detail["status"] == "blocked"
