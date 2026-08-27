"""Topics, their sources, and their memories."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    MemoryOut,
    SourceCreate,
    SourceOut,
    TopicCreate,
    TopicDetailOut,
    TopicOut,
)
from app.db.models import MEMORY_TYPES, SOURCE_TYPES, Memory, Project, Source, SourceChunk, Topic
from app.db.session import get_session

router = APIRouter(prefix="/topics", tags=["topics"])


async def _get_topic_or_404(session: AsyncSession, topic_id: uuid.UUID) -> Topic:
    topic = await session.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    return topic


@router.post("", response_model=TopicOut, status_code=201)
async def create_topic(payload: TopicCreate, session: AsyncSession = Depends(get_session)) -> Topic:
    topic = Topic(name=payload.name.strip(), description=payload.description)
    session.add(topic)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail=f"A topic named {payload.name!r} already exists") from None
    return topic


@router.get("", response_model=list[TopicOut])
async def list_topics(session: AsyncSession = Depends(get_session)) -> list[Topic]:
    return list((await session.scalars(select(Topic).order_by(Topic.created_at.desc()))).all())


@router.get("/{topic_id}", response_model=TopicDetailOut)
async def get_topic(topic_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> TopicDetailOut:
    topic = await _get_topic_or_404(session, topic_id)

    async def count(model, column) -> int:  # noqa: ANN001
        return int((await session.execute(select(func.count()).select_from(model).where(column == topic_id))).scalar_one())

    type_rows = (
        await session.execute(
            select(Memory.type, func.count()).where(Memory.topic_id == topic_id).group_by(Memory.type)
        )
    ).all()

    return TopicDetailOut(
        id=topic.id,
        name=topic.name,
        description=topic.description,
        created_at=topic.created_at,
        updated_at=topic.updated_at,
        source_count=await count(Source, Source.topic_id),
        memory_count=await count(Memory, Memory.topic_id),
        chunk_count=await count(SourceChunk, SourceChunk.topic_id),
        project_count=await count(Project, Project.topic_id),
        memory_types={row[0]: int(row[1]) for row in type_rows},
    )


@router.post("/{topic_id}/sources", response_model=SourceOut, status_code=201)
async def register_source(
    topic_id: uuid.UUID, payload: SourceCreate, session: AsyncSession = Depends(get_session)
) -> Source:
    await _get_topic_or_404(session, topic_id)

    if payload.type not in SOURCE_TYPES:
        raise HTTPException(status_code=422, detail=f"type must be one of: {', '.join(SOURCE_TYPES)}")

    metadata = dict(payload.metadata_json)
    if payload.text is not None:
        metadata["text"] = payload.text
    if payload.type == "pasted_text" and not str(metadata.get("text", "")).strip():
        raise HTTPException(status_code=422, detail="pasted_text sources need 'text'")
    if payload.type in {"local_file", "local_folder"} and not payload.uri:
        raise HTTPException(status_code=422, detail=f"{payload.type} sources need a 'uri'")

    source = Source(
        topic_id=topic_id,
        type=payload.type,
        name=payload.name.strip(),
        uri=payload.uri,
        metadata_json=metadata,
        status="registered",
    )
    session.add(source)
    await session.commit()
    return source


@router.get("/{topic_id}/sources", response_model=list[SourceOut])
async def list_sources(topic_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> list[Source]:
    await _get_topic_or_404(session, topic_id)
    return list(
        (
            await session.scalars(
                select(Source).where(Source.topic_id == topic_id).order_by(Source.created_at.desc())
            )
        ).all()
    )


@router.get("/{topic_id}/memories", response_model=list[MemoryOut])
async def list_memories(
    topic_id: uuid.UUID,
    type: str | None = Query(default=None, description=f"Filter by memory type: {', '.join(MEMORY_TYPES)}"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[Memory]:
    await _get_topic_or_404(session, topic_id)
    stmt = select(Memory).where(Memory.topic_id == topic_id)
    if type:
        if type not in MEMORY_TYPES:
            raise HTTPException(status_code=422, detail=f"type must be one of: {', '.join(MEMORY_TYPES)}")
        stmt = stmt.where(Memory.type == type)
    stmt = stmt.order_by(Memory.importance.desc(), Memory.created_at.desc()).limit(limit).offset(offset)
    return list((await session.scalars(stmt)).all())
