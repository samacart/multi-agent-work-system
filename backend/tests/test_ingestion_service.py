"""End-to-end ingestion pipeline (offline: hash embeddings, heuristic extractor)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.models import Memory, Source, SourceChunk, Topic
from app.ingestion.service import IngestionError, ingest_source

NOTES = """
# Customer onboarding

We decided that invite links expire after 14 days.
Invites must not be reusable once an account is created.
There is a risk that expired invites fail silently and the user sees a blank page.
Watch out: the invite service caches tokens for 5 minutes after issuance.
An invite token is defined as a signed opaque string tied to one organisation.
The invite service calls the billing API when an account is created.
We learned that the previous attempt failed because tokens were guessable.
"""


@pytest.fixture
async def topic(session) -> Topic:
    topic = Topic(name="customer onboarding")
    session.add(topic)
    await session.commit()
    return topic


@pytest.fixture
async def pasted_source(session, topic) -> Source:
    source = Source(
        topic_id=topic.id, type="pasted_text", name="kickoff notes", metadata_json={"text": NOTES}
    )
    session.add(source)
    await session.commit()
    return source


async def test_ingestion_produces_chunks_and_memories(session, pasted_source):
    summary = await ingest_source(session, pasted_source.id)

    assert summary.status == "ingested"
    assert summary.error is None
    assert summary.chunks_created > 0
    assert summary.memories_created > 0
    assert summary.embedding_provider == "hash"

    chunks = (await session.scalars(select(SourceChunk))).all()
    assert all(c.topic_id == pasted_source.topic_id for c in chunks)
    assert all(c.embedding and len(c.embedding) == 1536 for c in chunks)

    memories = (await session.scalars(select(Memory))).all()
    assert {m.type for m in memories} >= {"decision", "constraint", "risk"}
    assert all(m.source_id == pasted_source.id for m in memories)
    assert all(m.embedding for m in memories)
    assert all(m.metadata_json.get("source_quote") for m in memories)


async def test_source_status_and_summary_are_recorded(session, pasted_source):
    await ingest_source(session, pasted_source.id)
    await session.refresh(pasted_source)

    assert pasted_source.status == "ingested"
    last = pasted_source.metadata_json["last_ingestion"]
    assert last["status"] == "ingested"
    assert last["memories_created"] > 0


async def test_reingesting_is_idempotent(session, pasted_source):
    first = await ingest_source(session, pasted_source.id)
    second = await ingest_source(session, pasted_source.id)

    assert second.chunks_created == 0
    assert second.chunks_skipped_duplicate == first.chunks_created
    assert second.memories_created == 0
    assert second.memories_skipped_duplicate > 0

    assert len((await session.scalars(select(SourceChunk))).all()) == first.chunks_created
    assert len((await session.scalars(select(Memory))).all()) == first.memories_created


async def test_the_same_knowledge_from_two_sources_is_stored_once(session, topic, pasted_source):
    await ingest_source(session, pasted_source.id)
    before = len((await session.scalars(select(Memory))).all())

    duplicate = Source(
        topic_id=topic.id, type="pasted_text", name="copy of notes", metadata_json={"text": NOTES}
    )
    session.add(duplicate)
    await session.commit()
    summary = await ingest_source(session, duplicate.id)

    assert summary.memories_created == 0
    assert summary.memories_skipped_duplicate > 0
    assert len((await session.scalars(select(Memory))).all()) == before


async def test_unreadable_source_fails_without_raising(session, topic):
    source = Source(topic_id=topic.id, type="local_file", name="missing", uri="/nope/missing.md")
    session.add(source)
    await session.commit()

    summary = await ingest_source(session, source.id)

    assert summary.status == "failed"
    assert summary.error
    await session.refresh(source)
    assert source.status == "failed"
    assert source.metadata_json["last_ingestion"]["error"]


async def test_unsupported_source_type_fails_cleanly(session, topic):
    source = Source(topic_id=topic.id, type="github_repo", name="repo", uri="https://github.com/x/y")
    session.add(source)
    await session.commit()

    summary = await ingest_source(session, source.id)
    assert summary.status == "failed"
    assert "Phase 5" in summary.error


async def test_missing_source_raises(session):
    import uuid

    with pytest.raises(IngestionError, match="not found"):
        await ingest_source(session, uuid.uuid4())


async def test_local_folder_ingestion(session, topic, tmp_path, monkeypatch):
    from app.config import get_settings

    root = tmp_path / "sources"
    root.mkdir()
    (root / "a.md").write_text("We decided that onboarding emails are sent within 5 minutes.")
    (root / "b.md").write_text("The signup service must never store raw invite tokens.")
    monkeypatch.setattr(get_settings(), "allowed_source_roots", str(root))

    source = Source(topic_id=topic.id, type="local_folder", name="docs", uri=str(root))
    session.add(source)
    await session.commit()

    summary = await ingest_source(session, source.id)
    assert summary.status == "ingested"
    assert summary.documents == 2
    documents = {c.metadata_json["document"] for c in (await session.scalars(select(SourceChunk))).all()}
    assert documents == {"a.md", "b.md"}


async def test_embedding_failure_marks_the_source_failed(session, pasted_source, monkeypatch):
    from app.memory import embeddings

    class BrokenProvider:
        name = "broken"

        async def embed(self, texts):  # noqa: ANN001, ANN202, ARG002
            raise RuntimeError("provider is down")

    monkeypatch.setattr("app.ingestion.service.get_embedding_provider", lambda: BrokenProvider())
    summary = await ingest_source(session, pasted_source.id)

    assert summary.status == "failed"
    assert "Embedding failed" in summary.error
    assert (await session.scalars(select(SourceChunk))).all() == []
    assert embeddings  # imported for clarity about what was swapped
