"""Agent run execution.

One place where an agent is invoked and the attempt is recorded, so every
execution - planning, review, delivery - leaves the same audit trail whether it
succeeded, failed, or returned something the contract rejects.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.contracts import schema_for
from app.agents.runtime import AgentContext, get_runtime
from app.db.models import AgentProfile, AgentRun

log = logging.getLogger(__name__)


class AgentRunFailed(Exception):
    def __init__(self, run: AgentRun, message: str) -> None:
        super().__init__(message)
        self.run = run


@dataclass
class RunOutcome:
    run: AgentRun
    output: BaseModel


async def get_profile_by_role(session: AsyncSession, role: str) -> AgentProfile:
    profile = (
        await session.scalars(select(AgentProfile).where(AgentProfile.role == role).order_by(AgentProfile.name))
    ).first()
    if profile is None:
        raise LookupError(f"No agent profile seeded for role {role!r}")
    return profile


async def execute_run(
    session: AsyncSession,
    role: str,
    task: str,
    instruction: str,
    context: AgentContext,
    project_id: uuid.UUID | None = None,
    task_id: uuid.UUID | None = None,
) -> RunOutcome:
    """Invoke `role` for the named structured `task` and record an AgentRun.

    Raises AgentRunFailed - with the persisted run attached - when the runtime
    fails or returns output the contract rejects.
    """
    profile = await get_profile_by_role(session, role)
    model = schema_for(task)
    runtime = get_runtime()

    payload = {
        "task": task,
        "instruction": instruction,
        "system_prompt": profile.system_prompt,
        # Passes for the same project can share a warm session pool.
        "session_pool": str(project_id) if project_id else "",
    }
    run = AgentRun(
        project_id=project_id,
        task_id=task_id,
        agent_profile_id=profile.id,
        status="running",
        input={"task": task, "instruction": instruction, "runtime": runtime.name},
        started_at=datetime.now(timezone.utc),
    )
    session.add(run)
    await session.commit()

    try:
        result = await runtime.run(profile, payload, context)
    except Exception as exc:  # noqa: BLE001 - a runtime blowing up is a failed run, not a crashed API
        return await _finish_failed(session, run, f"{type(exc).__name__}: {exc}")

    if result.status != "succeeded":
        return await _finish_failed(session, run, result.error or "Runtime reported failure")

    try:
        validated = model.model_validate(result.output)
    except ValidationError as exc:
        # The runtime answered, but not in the shape the contract requires.
        return await _finish_failed(session, run, f"Output did not match the {task} contract: {exc}")

    run.status = "succeeded"
    run.output = validated.model_dump(mode="json")
    run.completed_at = datetime.now(timezone.utc)
    await session.commit()
    log.info("agent run %s (%s/%s) succeeded", run.id, role, task)
    return RunOutcome(run=run, output=validated)


async def _finish_failed(session: AsyncSession, run: AgentRun, error: str) -> RunOutcome:
    run.status = "failed"
    run.error = error
    run.completed_at = datetime.now(timezone.utc)
    await session.commit()
    log.warning("agent run %s failed: %s", run.id, error)
    raise AgentRunFailed(run, error)
