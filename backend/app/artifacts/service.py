"""Artifact persistence.

Artifacts are the deliverables: they are what a human reads, so they are stored
as markdown rather than raw JSON, with the structured run output kept on the
AgentRun that produced it.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Artifact


async def upsert_artifact(
    session: AsyncSession,
    project_id: uuid.UUID,
    type: str,
    title: str,
    content: str,
    task_id: uuid.UUID | None = None,
) -> Artifact:
    """Replace the existing artifact of this type for the project, if any.

    Re-planning should update the brief, not leave three of them behind.
    """
    existing = (
        await session.scalars(
            select(Artifact).where(Artifact.project_id == project_id, Artifact.type == type)
        )
    ).first()

    if existing is not None:
        existing.title = title
        existing.content = content
        existing.task_id = task_id
        await session.commit()
        return existing

    artifact = Artifact(project_id=project_id, task_id=task_id, type=type, title=title, content=content)
    session.add(artifact)
    await session.commit()
    return artifact


def bullets(items: list, empty: str = "_none recorded_") -> str:
    if not items:
        return empty
    return "\n".join(f"- {item}" for item in items)
