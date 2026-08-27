"""Core model creation and constraints."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, StatementError

from app.db.models import (
    AgentProfile,
    AgentRun,
    ApprovalRequest,
    Artifact,
    Decision,
    Memory,
    Project,
    Source,
    SourceChunk,
    Task,
    Topic,
)


async def test_full_object_graph_persists(session):
    topic = Topic(name="customer onboarding", description="Everything about onboarding")
    session.add(topic)
    await session.flush()

    source = Source(topic_id=topic.id, type="pasted_text", name="kickoff notes", metadata_json={"author": "sam"})
    session.add(source)
    await session.flush()

    chunk = SourceChunk(
        source_id=source.id,
        topic_id=topic.id,
        content="Invite links should expire after two weeks.",
        content_hash="a" * 64,
        embedding=[0.1] * 1536,
    )
    memory = Memory(
        topic_id=topic.id,
        source_id=source.id,
        type="decision",
        content="Invite links expire after 14 days.",
        confidence=0.91,
        importance=0.77,
        embedding=[0.2] * 1536,
    )
    project = Project(topic_id=topic.id, name="Self-serve onboarding", goal="Ship self-serve signup", status="planning")
    session.add_all([chunk, memory, project])
    await session.flush()

    task = Task(
        project_id=project.id,
        title="Design invite link data model",
        agent_role="architect",
        status="ready",
        acceptance_criteria=["Token expiry behavior is defined", "Security risks are identified"],
    )
    profile = AgentProfile(name="Test Architect", role="architect", system_prompt="be useful")
    session.add_all([task, profile])
    await session.flush()

    session.add_all(
        [
            AgentRun(project_id=project.id, task_id=task.id, agent_profile_id=profile.id, input={"instruction": "plan"}),
            Decision(project_id=project.id, question="Expiry window?", answer="14 days", decided_by="sam"),
            ApprovalRequest(
                project_id=project.id,
                action_type="change_database_schema",
                action_summary="Add invite_tokens table",
                risk_level="high",
                requested_by_agent_id=profile.id,
            ),
            Artifact(project_id=project.id, type="project_brief", title="Brief", content="# Brief"),
        ]
    )
    await session.commit()

    stored_chunk = (await session.scalars(select(SourceChunk))).one()
    assert len(stored_chunk.embedding) == 1536

    stored_task = (await session.scalars(select(Task))).one()
    assert stored_task.acceptance_criteria[0] == "Token expiry behavior is defined"
    assert stored_task.evidence == []

    stored_approval = (await session.scalars(select(ApprovalRequest))).one()
    assert stored_approval.status == "pending"


async def test_topic_name_is_unique(session):
    session.add(Topic(name="duplicate"))
    await session.commit()
    session.add(Topic(name="duplicate"))
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_invalid_status_is_rejected(session):
    """Statuses are constrained, so a typo fails loudly instead of silently
    creating an unreachable state."""
    session.add(Project(name="bad status", status="totally-made-up"))
    with pytest.raises((IntegrityError, StatementError, LookupError, ValueError)):
        await session.commit()
    await session.rollback()


async def test_deleting_topic_cascades_to_sources_and_memories(session):
    topic = Topic(name="cascade")
    session.add(topic)
    await session.flush()
    session.add(Source(topic_id=topic.id, type="local_file", name="f.md"))
    session.add(Memory(topic_id=topic.id, type="fact", content="x"))
    await session.commit()

    await session.delete(topic)
    await session.commit()

    assert (await session.scalars(select(Source))).all() == []
    assert (await session.scalars(select(Memory))).all() == []
