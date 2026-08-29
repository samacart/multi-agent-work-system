"""Human-in-the-loop gating."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.agents.profiles import APPROVAL_REQUIRED_ACTIONS, AUTO_APPROVED_ACTIONS
from app.approvals.service import (
    ApprovalRequired,
    answer_question,
    check_gate,
    record_question,
    request_approval,
    requires_approval,
    respond_to_approval,
)
from app.db.models import ApprovalRequest, Decision, Project


@pytest.fixture
async def project(session) -> Project:
    project = Project(name="self-serve onboarding", goal="ship self-serve signup")
    session.add(project)
    await session.commit()
    return project


def test_auto_approved_actions_are_not_gated():
    for action in AUTO_APPROVED_ACTIONS:
        assert requires_approval(action) is False


def test_listed_dangerous_actions_are_gated():
    for action in APPROVAL_REQUIRED_ACTIONS:
        assert requires_approval(action) is True


def test_unknown_actions_fail_closed():
    """An action nobody classified is more likely novel than routine."""
    assert requires_approval("launch_the_missiles") is True
    assert requires_approval("") is True


async def test_a_gated_action_blocks_and_creates_a_request(session, project):
    with pytest.raises(ApprovalRequired) as exc:
        await check_gate(session, "merge_pr", "Merge the onboarding PR", project_id=project.id)

    approval = exc.value.approval
    assert approval.status == "pending"
    assert approval.action_type == "merge_pr"
    assert len((await session.scalars(select(ApprovalRequest))).all()) == 1


async def test_an_ungated_action_passes_without_a_request(session, project):
    assert await check_gate(session, "semantic_search", "search memory", project_id=project.id) is None
    assert (await session.scalars(select(ApprovalRequest))).all() == []


async def test_approval_unblocks_the_action(session, project):
    with pytest.raises(ApprovalRequired) as exc:
        await check_gate(session, "deploy", "Deploy to production", project_id=project.id)

    await respond_to_approval(session, exc.value.approval.id, "approved", "go ahead")
    assert await check_gate(session, "deploy", "Deploy to production", project_id=project.id) is None


async def test_rejection_keeps_blocking_and_reopens_a_fresh_request(session, project):
    with pytest.raises(ApprovalRequired) as first:
        await check_gate(session, "deploy", "Deploy to production", project_id=project.id)
    await respond_to_approval(session, first.value.approval.id, "rejected", "not yet")

    with pytest.raises(ApprovalRequired) as second:
        await check_gate(session, "deploy", "Deploy to production", project_id=project.id)

    assert second.value.approval.id != first.value.approval.id
    assert second.value.approval.status == "pending"


async def test_repeated_requests_do_not_pile_up(session, project):
    first, created_first = await request_approval(session, "deploy", "Deploy", project_id=project.id)
    second, created_second = await request_approval(session, "deploy", "Deploy", project_id=project.id)

    assert created_first is True
    assert created_second is False
    assert first.id == second.id


async def test_an_answered_approval_cannot_be_answered_again(session, project):
    approval, _ = await request_approval(session, "deploy", "Deploy", project_id=project.id)
    await respond_to_approval(session, approval.id, "approved")
    with pytest.raises(ValueError, match="already approved"):
        await respond_to_approval(session, approval.id, "rejected")


async def test_invalid_response_status_is_rejected(session, project):
    approval, _ = await request_approval(session, "deploy", "Deploy", project_id=project.id)
    with pytest.raises(ValueError, match="must be approved"):
        await respond_to_approval(session, approval.id, "maybe")


async def test_questions_are_queued_once_and_answerable(session, project):
    first = await record_question(session, project.id, "How long should invites last?", "affects scope")
    duplicate = await record_question(session, project.id, "How long should invites last?")

    assert first is not None
    assert duplicate is None
    assert len((await session.scalars(select(Decision))).all()) == 1

    answered = await answer_question(session, first.id, "14 days", decided_by="sam")
    assert answered.answer == "14 days"
    assert answered.decided_by == "sam"


async def test_an_approved_gate_is_not_raised_again(session, project):
    """A re-plan raised a fresh copy of every gate the human had just approved -
    sixteen duplicates, which then blocked the run they had just unblocked."""
    first, created = await request_approval(session, "deploy", "Deploy", project_id=project.id)
    assert created is True
    await respond_to_approval(session, first.id, "approved")

    again, created_again = await request_approval(session, "deploy", "Deploy", project_id=project.id)

    assert created_again is False
    assert again.id == first.id
    assert again.status == "approved"


async def test_a_rejected_gate_is_raised_again(session, project):
    """Rejecting is a decision to re-ask, not a standing answer."""
    first, _ = await request_approval(session, "deploy", "Deploy", project_id=project.id)
    await respond_to_approval(session, first.id, "rejected")

    again, created = await request_approval(session, "deploy", "Deploy", project_id=project.id)

    assert created is True
    assert again.id != first.id
    assert again.status == "pending"


async def test_a_cancelled_gate_is_raised_again(session, project):
    first, _ = await request_approval(session, "deploy", "Deploy", project_id=project.id)
    await respond_to_approval(session, first.id, "cancelled")

    _again, created = await request_approval(session, "deploy", "Deploy", project_id=project.id)
    assert created is True
