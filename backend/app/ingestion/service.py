"""Ingestion pipeline.

  source -> documents -> chunks -> embeddings -> stored chunks
                                              -> extracted memories -> stored memories

Re-ingesting a source is safe: chunks and memories are deduplicated by content
hash, so nothing is duplicated and unchanged content costs nothing.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import asdict, dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Memory, Source, SourceChunk
from app.ingestion.chunk import Chunk, chunk_text, content_hash
from app.ingestion.extract import SourceAccessError, UnsupportedSourceType, extract_documents
from app.memory.embeddings import get_embedding_provider
from app.memory.extraction import get_memory_extractor

log = logging.getLogger(__name__)


@dataclass
class IngestionSummary:
    source_id: str
    source_name: str
    status: str
    documents: int = 0
    chunks_created: int = 0
    chunks_skipped_duplicate: int = 0
    memories_created: int = 0
    memories_skipped_duplicate: int = 0
    memory_types: dict[str, int] = field(default_factory=dict)
    embedding_provider: str = ""
    memory_extractor: str = ""
    error: str | None = None
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


class IngestionError(Exception):
    pass


async def ingest_source(
    session: AsyncSession, source_id: uuid.UUID, github_client=None  # noqa: ANN001 - adapter, injected in tests
) -> IngestionSummary:
    """Ingest one registered source. Never raises for expected failures - the
    failure is recorded on the source and returned in the summary."""
    source = await session.get(Source, source_id)
    if source is None:
        raise IngestionError(f"Source {source_id} not found")

    settings = get_settings()
    summary = IngestionSummary(
        source_id=str(source.id),
        source_name=source.name,
        status="ingesting",
        embedding_provider=settings.embedding_provider,
        memory_extractor=settings.memory_extractor,
    )

    source.status = "ingesting"
    await session.commit()

    try:
        documents = await extract_documents(
            source.type, source.uri, source.metadata_json, github_client=github_client
        )
    except (SourceAccessError, UnsupportedSourceType) as exc:
        return await _fail(session, source_id, summary, str(exc))

    summary.documents = len(documents)
    for document in documents:
        if document.metadata.get("skipped"):
            summary.notes.extend(str(s) for s in document.metadata["skipped"])

    chunks: list[tuple[Chunk, dict]] = []
    for document in documents:
        for chunk in chunk_text(document.text, metadata={"document": document.name, **document.metadata}):
            chunks.append((chunk, {"document": document.name, "chunk_index": chunk.index, **document.metadata}))

    if not chunks:
        return await _fail(session, source_id, summary, "Source produced no chunks")

    existing_hashes = set(
        (await session.scalars(select(SourceChunk.content_hash).where(SourceChunk.source_id == source.id))).all()
    )
    new_chunks = []
    for chunk, metadata in chunks:
        digest = chunk.content_hash
        if digest in existing_hashes:
            summary.chunks_skipped_duplicate += 1
            continue
        existing_hashes.add(digest)
        new_chunks.append((chunk, metadata, digest))

    provider = get_embedding_provider()

    if new_chunks:
        try:
            vectors = await provider.embed([c.content for c, _, _ in new_chunks])
        except Exception as exc:  # noqa: BLE001 - provider failures are expected operationally
            return await _fail(session, source_id, summary, f"Embedding failed: {type(exc).__name__}: {exc}")

        for (chunk, metadata, digest), vector in zip(new_chunks, vectors):
            session.add(
                SourceChunk(
                    source_id=source.id,
                    topic_id=source.topic_id,
                    content=chunk.content,
                    content_hash=digest,
                    metadata_json=metadata,
                    embedding=vector,
                )
            )
            summary.chunks_created += 1

    # Memories are extracted per document, so a quote keeps its document context.
    extractor = get_memory_extractor()
    extracted = []
    for document in documents:
        extracted.extend(
            await extractor.extract(
                document.text,
                metadata={"document": document.name, "source_name": source.name},
            )
        )

    # Cap across the whole source, not per document: a folder of 38 files was
    # silently allowed 38x the configured limit.
    if len(extracted) > settings.max_memories_per_source:
        summary.notes.append(
            f"Kept the {settings.max_memories_per_source} strongest of {len(extracted)} extracted memories "
            f"(MAX_MEMORIES_PER_SOURCE)"
        )
        extracted = _cap_evenly(extracted, settings.max_memories_per_source)

    if extracted:
        # Deduplicate against what the topic already knows, not just this source:
        # the same decision written in two places should be one memory.
        existing_memory_hashes = {
            content_hash(c)
            for c in (
                await session.scalars(select(Memory.content).where(Memory.topic_id == source.topic_id))
            ).all()
        }
        fresh = []
        for memory in extracted:
            digest = content_hash(memory.content)
            if digest in existing_memory_hashes:
                summary.memories_skipped_duplicate += 1
                continue
            existing_memory_hashes.add(digest)
            fresh.append(memory)

        if fresh:
            try:
                vectors = await provider.embed([m.content for m in fresh])
            except Exception as exc:  # noqa: BLE001
                return await _fail(session, source_id, summary, f"Embedding failed: {type(exc).__name__}: {exc}")

            for memory, vector in zip(fresh, vectors):
                session.add(
                    Memory(
                        topic_id=source.topic_id,
                        source_id=source.id,
                        type=memory.type,
                        content=memory.content,
                        confidence=memory.confidence,
                        importance=memory.importance,
                        metadata_json=memory.metadata,
                        embedding=vector,
                    )
                )
                summary.memories_created += 1
                summary.memory_types[memory.type] = summary.memory_types.get(memory.type, 0) + 1

    source.status = "ingested"
    summary.status = "ingested"
    source.metadata_json = {**(source.metadata_json or {}), "last_ingestion": summary.as_dict()}
    await session.commit()
    log.info(
        "ingested source %s: %d chunks, %d memories", source.name, summary.chunks_created, summary.memories_created
    )
    return summary


def _cap_evenly(memories: list, limit: int) -> list:
    """Take the strongest, round-robin across types.

    Ranking purely by importance lets one loud type take the whole budget -
    a technical corpus is full of constraints, and open questions (exactly what
    a planner needs) score lower and vanish entirely.
    """
    by_type: dict[str, list] = {}
    for memory in sorted(memories, key=lambda m: (m.importance, m.confidence), reverse=True):
        by_type.setdefault(memory.type, []).append(memory)

    kept: list = []
    while len(kept) < limit and any(by_type.values()):
        for bucket in by_type.values():
            if not bucket:
                continue
            kept.append(bucket.pop(0))
            if len(kept) >= limit:
                break
    return kept


async def _fail(
    session: AsyncSession, source_id: uuid.UUID, summary: IngestionSummary, message: str
) -> IngestionSummary:
    """Record the failure on the source and return it in the summary.

    Takes the id rather than the instance on purpose: rollback() expires every
    object in the session, so reading `source.id` afterwards would trigger a
    lazy load from a sync context and blow up with MissingGreenlet.
    """
    await session.rollback()
    source = await session.get(Source, source_id)
    if source is not None:
        source.status = "failed"
        summary.status = "failed"
        summary.error = message
        source.metadata_json = {**(source.metadata_json or {}), "last_ingestion": summary.as_dict()}
        await session.commit()
    log.warning("ingestion failed for source %s: %s", summary.source_name, message)
    summary.status = "failed"
    summary.error = message
    return summary
