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

    planned = await client.post(f"/projects/{project_id}/plan?gates=false")
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
    await client.post(f"/projects/{project_id}/plan?gates=false")
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
    await client.post(f"/projects/{project_id}/plan?gates=false")
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
    await client.post(f"/projects/{project_id}/plan?gates=false")
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
    response = await client.post(f"/projects/{seeded['project']['id']}/plan?gates=false")
    assert response.status_code == 422
    assert response.json()["status"] == "failed"

    detail = (await client.get(f"/projects/{seeded['project']['id']}")).json()
    assert detail["status"] == "blocked"


async def test_running_the_sdlc_loop_over_the_api(client, seeded):
    project_id = seeded["project"]["id"]
    await client.post(f"/projects/{project_id}/plan?gates=false")

    # A pending gate holds back the roles it governs.
    blocked = (await client.post(f"/projects/{project_id}/run?mode=sync")).json()
    assert blocked["tasks_blocked"] > 0
    assert (await client.get(f"/projects/{project_id}")).json()["status"] == "blocked"

    for approval in (await client.get(f"/projects/{project_id}/approvals")).json():
        await client.post(f"/approvals/{approval['id']}/respond", json={"status": "approved"})

    result = (await client.post(f"/projects/{project_id}/run?mode=sync")).json()
    assert result["tasks_blocked"] == 0
    assert result["tasks_run"] >= 8
    assert result["lessons_stored"] > 0

    artifacts = {a["type"] for a in (await client.get(f"/projects/{project_id}/artifacts")).json()}
    assert {"test_report", "review_report", "security_report", "release_notes", "final_summary"} <= artifacts

    runs = (await client.get(f"/projects/{project_id}/runs")).json()
    assert len(runs) > 10
    assert all(r["status"] == "succeeded" for r in runs)

    memories = (await client.get(f"/topics/{seeded['topic']['id']}/memories")).json()
    assert any(m["metadata_json"].get("origin") == "sdlc_run" for m in memories)


async def test_running_an_unplanned_project_returns_409(client, seeded):
    """Refused up front in either mode - queueing it would fail inside the
    worker where nobody is watching."""
    for mode in ("sync", "async"):
        response = await client.post(f"/projects/{seeded['project']['id']}/run?mode={mode}")
        assert response.status_code == 409
        assert "Run planning first" in response.json()["detail"]


async def test_running_defaults_to_async(client, seeded, monkeypatch):
    """A full run takes tens of minutes; a synchronous request that long dies
    on any client disconnect and strands the project mid-run."""
    project_id = seeded["project"]["id"]
    await client.post(f"/projects/{project_id}/plan?gates=false")

    queued: list = []

    async def fake_enqueue(job_type, payload=None):  # noqa: ANN001, ANN202
        queued.append((job_type, payload))

        class Job:
            id = "job-1"

        return Job()

    monkeypatch.setattr("app.api.routes.projects.enqueue", fake_enqueue)
    response = await client.post(f"/projects/{project_id}/run")

    assert response.status_code == 202
    assert queued[0][0] == "run_project"


async def test_github_status_reports_configuration_without_the_token(client):
    response = await client.get("/github/status")
    assert response.status_code == 200
    body = response.json()
    assert set(body) >= {"enabled", "authenticated", "writes_enabled", "supported_source_types"}
    assert "token" not in response.text.lower() or "GITHUB_TOKEN" not in response.text


async def test_planned_branch_is_exposed(client, seeded):
    response = await client.get(f"/projects/{seeded['project']['id']}/branch")
    assert response.status_code == 200
    assert response.json()["branch"].startswith("agents/self-serve-onboarding-")


async def test_pr_description_endpoint_produces_an_artifact(client, seeded):
    project_id = seeded["project"]["id"]
    response = await client.post(f"/projects/{project_id}/pr-description", json={"base": "develop"})
    assert response.status_code == 200
    body = response.json()
    assert body["base"] == "develop"
    assert "develop" in body["content"]

    artifacts = {a["type"] for a in (await client.get(f"/projects/{project_id}/artifacts")).json()}
    assert "pr_description" in artifacts


async def test_opening_a_pull_request_is_gated(client, seeded):
    from app.config import get_settings

    settings = get_settings()
    settings.github_allow_writes = True
    try:
        response = await client.post(
            f"/projects/{seeded['project']['id']}/pull-request", json={"repo": "o/r"}
        )
        assert response.status_code == 409
        assert response.json()["detail"]["approval_id"]
    finally:
        settings.github_allow_writes = False


async def test_opening_a_pull_request_is_refused_when_writes_are_off(client, seeded):
    response = await client.post(f"/projects/{seeded['project']['id']}/pull-request", json={"repo": "o/r"})
    assert response.status_code == 422
    assert "GITHUB_ALLOW_WRITES" in response.json()["detail"]


async def test_registering_a_github_source(client, seeded):
    response = await client.post(
        f"/topics/{seeded['topic']['id']}/sources",
        json={"type": "github_issue", "name": "invite bug", "uri": "https://github.com/o/r/issues/42"},
    )
    assert response.status_code == 201
    assert response.json()["type"] == "github_issue"
