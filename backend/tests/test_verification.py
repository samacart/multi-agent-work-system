"""Criteria, evidence, and why work is blocked.

Evidence-based promotion is the system's strongest property. These tests exist
mostly to stop it being eroded quietly.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.models import Project, Task
from app.db.seed import seed_agent_profiles


@pytest.fixture
async def project_with_task(client, session):
    await seed_agent_profiles(session)
    project = Project(name="verification")
    session.add(project)
    await session.commit()
    task = Task(
        project_id=project.id,
        title="Do the thing",
        agent_role="developer",
        status="review",
        acceptance_criteria=["It works", "It is tested"],
    )
    session.add(task)
    await session.commit()
    return {"project": project, "task": task}


# --- criteria as the unit of verification ---


async def test_criteria_are_listed_with_their_verdicts(client, project_with_task):
    project = project_with_task["project"]
    rows = (await client.get(f"/projects/{project.id}/criteria")).json()

    assert [r["criterion"] for r in rows] == ["It works", "It is tested"]
    assert all(r["verdict"] == "unverified" for r in rows)
    assert all(r["task_title"] == "Do the thing" for r in rows)


async def test_criteria_can_be_filtered_to_what_still_needs_work(client, project_with_task):
    project, task = project_with_task["project"], project_with_task["task"]
    await client.patch(
        f"/tasks/{task.id}/evidence",
        json={"criterion": "It works", "verdict": "met", "evidence": "ran it"},
    )

    unverified = (await client.get(f"/projects/{project.id}/criteria?verdict=unverified")).json()
    assert [r["criterion"] for r in unverified] == ["It is tested"]


# --- human evidence: allowed, but never anonymous ---


async def test_a_human_can_verify_what_the_agent_could_not(client, project_with_task):
    task = project_with_task["task"]
    response = await client.patch(
        f"/tasks/{task.id}/evidence",
        json={
            "criterion": "It works",
            "verdict": "met",
            "evidence": "Checked by hand against the real record",
            "rationale": "The suite cannot reach the device",
        },
    )
    assert response.status_code == 200
    entry = next(e for e in response.json()["evidence"] if e["criterion"] == "It works")
    assert entry["verdict"] == "met"
    assert entry["attributed_to"] == "human"
    assert entry["rationale"]


async def test_human_and_agent_evidence_are_distinguishable(client, session, project_with_task):
    """A human marking a criterion met is the obvious way to erode the model,
    so who said so travels with the claim."""
    from app.agents.contracts import TestEvidence
    from app.orchestration.sdlc import _attach_evidence

    task = project_with_task["task"]
    await client.patch(
        f"/tasks/{task.id}/evidence",
        json={"criterion": "It works", "verdict": "met", "evidence": "by hand"},
    )

    class Report:
        evidence = [TestEvidence(criterion="It is tested", verdict="met", evidence="suite passed")]

    await _attach_evidence(session, [task], Report())

    reloaded = (
        await session.scalars(
            select(Task).where(Task.id == task.id).execution_options(populate_existing=True)
        )
    ).one()
    by_criterion = {e["criterion"]: e for e in reloaded.evidence}
    assert by_criterion["It works"]["attributed_to"] == "human"
    assert by_criterion["It is tested"]["attributed_to"] == "agent"


async def test_met_requires_evidence(client, project_with_task):
    """"Met" is a claim with backing, or it is nothing."""
    task = project_with_task["task"]
    response = await client.patch(
        f"/tasks/{task.id}/evidence", json={"criterion": "It works", "verdict": "met", "evidence": "  "}
    )
    assert response.status_code == 422
    assert "Evidence is required" in response.json()["detail"]


async def test_evidence_must_name_a_real_criterion(client, project_with_task):
    task = project_with_task["task"]
    response = await client.patch(
        f"/tasks/{task.id}/evidence",
        json={"criterion": "Something nobody asked for", "verdict": "met", "evidence": "x"},
    )
    assert response.status_code == 422


async def test_amending_a_verdict_replaces_it_rather_than_appending(client, project_with_task):
    task = project_with_task["task"]
    for verdict, evidence in (("met", "first look"), ("not_met", "second look, it regressed")):
        await client.patch(
            f"/tasks/{task.id}/evidence",
            json={"criterion": "It works", "verdict": verdict, "evidence": evidence},
        )
    entries = (await client.get(f"/projects/{project_with_task['project'].id}/criteria")).json()
    works = [e for e in entries if e["criterion"] == "It works"]
    assert len(works) == 1
    assert works[0]["verdict"] == "not_met"


async def test_human_evidence_promotes_through_the_same_rule_as_agent_evidence(
    session, project_with_task, client
):
    """One promotion rule, not two - two would be two chances to disagree."""
    from app.orchestration.sdlc import SdlcResult, _promote_verified_tasks

    task = project_with_task["task"]
    for criterion in ("It works", "It is tested"):
        await client.patch(
            f"/tasks/{task.id}/evidence",
            json={"criterion": criterion, "verdict": "met", "evidence": "checked by hand"},
        )

    reloaded = (
        await session.scalars(
            select(Task).where(Task.id == task.id).execution_options(populate_existing=True)
        )
    ).one()
    result = SdlcResult(project_id=str(reloaded.project_id), status="running")
    await _promote_verified_tasks(session, [reloaded], blocking=False, result=result)

    assert result.tasks_done == 1
    assert reloaded.status == "done"


# --- blockers as something addressable ---


async def test_a_gate_blocked_task_names_the_approval(client, session, project_with_task):
    from app.approvals.service import request_approval

    task = project_with_task["task"]
    approval, _ = await request_approval(
        session, "deploy", "Deploy it", project_id=task.project_id, risk_level="high"
    )
    task.status = "blocked"
    task.metadata_json = {
        "blocked_reason": "developer work needs the pending approval gate(s) answered first",
        "blocked_by": {"approvals": [str(approval.id)]},
    }
    await session.commit()

    body = (await client.get(f"/tasks/{task.id}/blockers")).json()
    assert body["reason"].startswith("developer work needs")
    assert [a["id"] for a in body["approvals"]] == [str(approval.id)]


async def test_an_answered_gate_stops_reading_as_the_blocker(client, session, project_with_task):
    from app.approvals.service import request_approval, respond_to_approval

    task = project_with_task["task"]
    approval, _ = await request_approval(session, "deploy", "Deploy", project_id=task.project_id)
    task.status = "blocked"
    task.metadata_json = {"blocked_by": {"approvals": [str(approval.id)]}}
    await session.commit()
    await respond_to_approval(session, approval.id, "approved")

    body = (await client.get(f"/tasks/{task.id}/blockers")).json()
    assert body["approvals"] == []


async def test_blockers_report_unmet_criteria(client, project_with_task):
    task = project_with_task["task"]
    await client.patch(
        f"/tasks/{task.id}/evidence",
        json={"criterion": "It works", "verdict": "met", "evidence": "ran it"},
    )
    body = (await client.get(f"/tasks/{task.id}/blockers")).json()
    assert body["unmet_criteria"] == ["It is tested"]


# --- the state machine, served rather than duplicated ---


async def test_transitions_are_served_so_the_ui_cannot_drift(client):
    from app.projects.tasks import ALLOWED_TRANSITIONS

    body = (await client.get("/tasks/transitions")).json()
    assert body == {status: sorted(nxt) for status, nxt in ALLOWED_TRANSITIONS.items()}


async def test_a_run_does_not_discard_evidence_attached_while_it_was_working(
    client, session, project_with_task
):
    """QA merges onto task objects the run loaded at its start. Writing the
    whole evidence list from that stale copy would silently drop anything a
    human attached in the meantime."""
    from app.agents.contracts import TestEvidence
    from app.orchestration.sdlc import _attach_evidence

    task = project_with_task["task"]
    stale = task  # what a run would be holding

    await client.patch(
        f"/tasks/{task.id}/evidence",
        json={"criterion": "It works", "verdict": "met", "evidence": "verified by hand"},
    )

    class Report:
        evidence = [TestEvidence(criterion="It is tested", verdict="met", evidence="suite passed")]

    await _attach_evidence(session, [stale], Report())

    rows = (await client.get(f"/projects/{project_with_task['project'].id}/criteria")).json()
    by_criterion = {r["criterion"]: r for r in rows}
    assert by_criterion["It works"]["attributed_to"] == "human"
    assert by_criterion["It is tested"]["attributed_to"] == "agent"
