"""Human-in-the-loop gates.

Two queues, deliberately separate:

- Decision: an open question that needs judgement.
- ApprovalRequest: a specific action an agent wants to take, which blocks until
  a human answers.

The action lists come from the seeded agent profiles, so the rules a human reads
in the dashboard are the same ones the code enforces.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.profiles import AUTO_APPROVED_ACTIONS
from app.db.models import ApprovalRequest, Decision


class ApprovalRequired(Exception):
    """Raised when a gated action is attempted without an approval."""

    def __init__(self, approval: ApprovalRequest) -> None:
        super().__init__(f"Action {approval.action_type!r} requires approval (request {approval.id})")
        self.approval = approval


def requires_approval(action_type: str) -> bool:
    """Gate anything not explicitly auto-approved.

    Fail closed: an action nobody classified is more likely to be novel and
    risky than routine. APPROVAL_REQUIRED_ACTIONS is the documented list a human
    reads; it is not the boundary the code trusts.
    """
    return action_type not in AUTO_APPROVED_ACTIONS


async def request_approval(
    session: AsyncSession,
    action_type: str,
    action_summary: str,
    project_id: uuid.UUID | None = None,
    task_id: uuid.UUID | None = None,
    risk_level: str = "medium",
    requested_by_agent_id: uuid.UUID | None = None,
) -> tuple[ApprovalRequest, bool]:
    """Create a pending request, or return the matching one already open.

    Returns (request, created). Re-planning must not pile up duplicate gates for
    the same action.
    """
    existing = (
        await session.scalars(
            select(ApprovalRequest).where(
                ApprovalRequest.project_id == project_id,
                ApprovalRequest.action_type == action_type,
                ApprovalRequest.status == "pending",
            )
        )
    ).first()
    if existing is not None:
        return existing, False

    approval = ApprovalRequest(
        project_id=project_id,
        task_id=task_id,
        action_type=action_type,
        action_summary=action_summary,
        risk_level=risk_level,
        status="pending",
        requested_by_agent_id=requested_by_agent_id,
    )
    session.add(approval)
    await session.commit()
    return approval, True


async def check_gate(
    session: AsyncSession,
    action_type: str,
    action_summary: str,
    project_id: uuid.UUID | None = None,
    task_id: uuid.UUID | None = None,
    risk_level: str = "medium",
) -> ApprovalRequest | None:
    """Gate an action. Returns None when it may proceed.

    Raises ApprovalRequired when it may not - either because no request exists
    yet (one is created), or because the open request is still pending or was
    rejected.
    """
    if not requires_approval(action_type):
        return None

    approval = (
        await session.scalars(
            select(ApprovalRequest)
            .where(
                ApprovalRequest.project_id == project_id,
                ApprovalRequest.action_type == action_type,
            )
            .order_by(ApprovalRequest.created_at.desc())
        )
    ).first()

    if approval is not None and approval.status == "approved":
        return None

    if approval is None or approval.status in {"rejected", "cancelled"}:
        approval, _created = await request_approval(
            session, action_type, action_summary, project_id, task_id, risk_level
        )
    raise ApprovalRequired(approval)


async def respond_to_approval(
    session: AsyncSession, approval_id: uuid.UUID, status: str, response: str | None = None
) -> ApprovalRequest:
    if status not in {"approved", "rejected", "cancelled"}:
        raise ValueError("status must be approved, rejected, or cancelled")

    approval = await session.get(ApprovalRequest, approval_id)
    if approval is None:
        raise LookupError("Approval request not found")
    if approval.status != "pending":
        raise ValueError(f"Approval request is already {approval.status}")

    approval.status = status
    approval.response = response
    approval.updated_at = datetime.now(timezone.utc)
    await session.commit()
    return approval


async def record_question(
    session: AsyncSession,
    project_id: uuid.UUID,
    question: str,
    rationale: str | None = None,
    metadata: dict | None = None,
) -> Decision | None:
    """Queue a question for a human. Returns None if it is already queued."""
    existing = (
        await session.scalars(
            select(Decision).where(Decision.project_id == project_id, Decision.question == question)
        )
    ).first()
    if existing is not None:
        return None

    # The options considered and which is recommended: a question handed over
    # without a view is work passed back, not a decision surfaced.
    decision = Decision(
        project_id=project_id, question=question, rationale=rationale, metadata_json=metadata or {}
    )
    session.add(decision)
    await session.commit()
    return decision


async def answer_question(
    session: AsyncSession,
    decision_id: uuid.UUID,
    answer: str,
    decided_by: str = "human",
    rationale: str | None = None,
) -> Decision:
    decision = await session.get(Decision, decision_id)
    if decision is None:
        raise LookupError("Decision not found")
    decision.answer = answer
    decision.decided_by = decided_by
    if rationale:
        decision.rationale = rationale
    await session.commit()
    return decision
