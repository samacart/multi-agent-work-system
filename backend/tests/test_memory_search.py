"""Hybrid memory retrieval."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db.models import Memory, Source, Topic
from app.memory.embeddings import get_embedding_provider
from app.memory.search import (
    RECENCY_HALF_LIFE_DAYS,
    WEIGHTS,
    explain_weights,
    recency_score,
    search_memories,
)


async def _add_memory(session, topic, content, **kwargs):
    provider = get_embedding_provider()
    memory = Memory(
        topic_id=topic.id,
        type=kwargs.pop("type", "fact"),
        content=content,
        confidence=kwargs.pop("confidence", 0.8),
        importance=kwargs.pop("importance", 0.5),
        embedding=await provider.embed_one(content),
        **kwargs,
    )
    session.add(memory)
    await session.commit()
    return memory


@pytest.fixture
async def topic(session) -> Topic:
    topic = Topic(name="onboarding")
    session.add(topic)
    await session.commit()
    return topic


def test_weights_sum_to_one():
    assert sum(WEIGHTS.values()) == pytest.approx(1.0)
    assert explain_weights() == WEIGHTS


def test_recency_decays_by_half_life():
    now = datetime.now(timezone.utc)
    assert recency_score(now, now) == pytest.approx(1.0)
    half = now - timedelta(days=RECENCY_HALF_LIFE_DAYS)
    assert recency_score(half, now) == pytest.approx(0.5, abs=1e-6)
    assert recency_score(None) == 0.0


def test_naive_timestamps_are_treated_as_utc():
    now = datetime.now(timezone.utc)
    naive = now.replace(tzinfo=None)
    assert recency_score(naive, now) == pytest.approx(1.0, abs=1e-3)


async def test_search_ranks_relevant_memories_first(session, topic):
    await _add_memory(session, topic, "Invite links expire after 14 days from issuance.")
    await _add_memory(session, topic, "The nightly billing reconciliation job runs at 03:00 UTC.")
    await _add_memory(session, topic, "Support tickets are triaged by the platform team each morning.")

    hits = await search_memories(session, "how long is an invite link valid", topic_id=topic.id)

    assert hits
    assert "Invite links expire" in hits[0].memory.content
    assert hits[0].score > 0
    assert set(hits[0].components) == set(WEIGHTS)


async def test_empty_store_returns_no_hits(session, topic):
    assert await search_memories(session, "anything", topic_id=topic.id) == []


async def test_limit_is_respected(session, topic):
    for i in range(12):
        await _add_memory(session, topic, f"Onboarding invite rule number {i} applies to new organisations.")
    hits = await search_memories(session, "onboarding invite rule", topic_id=topic.id, limit=5)
    assert len(hits) == 5


async def test_type_filter_narrows_results(session, topic):
    await _add_memory(session, topic, "We decided invite links expire after 14 days.", type="decision")
    await _add_memory(session, topic, "Invite links expire after 14 days, which is a risk for slow signups.", type="risk")

    hits = await search_memories(session, "invite link expiry", topic_id=topic.id, types=["risk"])
    assert hits
    assert all(h.memory.type == "risk" for h in hits)


async def test_importance_breaks_ties_between_equal_text(session, topic):
    low = await _add_memory(session, topic, "Invite tokens are rotated on every deploy.", importance=0.1)
    high = await _add_memory(session, topic, "Invite tokens are rotated on every deploy!", importance=0.95)

    hits = await search_memories(session, "invite token rotation", topic_id=topic.id)
    ranked = [h.memory.id for h in hits]
    assert ranked.index(high.id) < ranked.index(low.id)


async def test_topic_scoping_excludes_other_topics(session, topic):
    other = Topic(name="billing")
    session.add(other)
    await session.commit()
    await _add_memory(session, topic, "Invite links expire after 14 days.")
    await _add_memory(session, other, "Invite links expire after 14 days.")

    hits = await search_memories(session, "invite link expiry", topic_id=topic.id)
    assert len(hits) == 1
    assert hits[0].memory.topic_id == topic.id


async def test_source_reliability_influences_score(session, topic):
    trusted = Source(topic_id=topic.id, type="pasted_text", name="handbook", metadata_json={"reliability": 1.0})
    shaky = Source(topic_id=topic.id, type="url", name="random blog", metadata_json={"reliability": 0.0})
    session.add_all([trusted, shaky])
    await session.commit()

    good = await _add_memory(session, topic, "Invite links expire after 14 days.", source_id=trusted.id)
    bad = await _add_memory(session, topic, "Invite links expire after 14 days!", source_id=shaky.id)

    hits = await search_memories(session, "invite link expiry", topic_id=topic.id)
    ranked = [h.memory.id for h in hits]
    assert ranked.index(good.id) < ranked.index(bad.id)


async def test_project_memories_outrank_topic_memories_for_that_project(session, topic):
    from app.db.models import Project

    project = Project(topic_id=topic.id, name="self-serve onboarding")
    session.add(project)
    await session.commit()

    scoped = await _add_memory(session, topic, "Invite links expire after 14 days.", project_id=project.id)
    hits = await search_memories(session, "invite link expiry", topic_id=topic.id, project_id=project.id)
    assert [h.memory.id for h in hits] == [scoped.id]


async def test_memories_without_embeddings_do_not_crash_search(session, topic):
    session.add(Memory(topic_id=topic.id, type="fact", content="No embedding here.", embedding=None))
    await session.commit()
    await _add_memory(session, topic, "Invite links expire after 14 days.")

    hits = await search_memories(session, "invite link expiry", topic_id=topic.id)
    assert hits[0].memory.content.startswith("Invite links")
