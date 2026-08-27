"""Memory search."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import MemoryOut, MemorySearchHit, MemorySearchRequest, MemorySearchResponse
from app.db.models import MEMORY_TYPES
from app.db.session import get_session
from app.memory.search import explain_weights, search_memories

router = APIRouter(prefix="/memory", tags=["memory"])


@router.post("/search", response_model=MemorySearchResponse)
async def search(
    payload: MemorySearchRequest, session: AsyncSession = Depends(get_session)
) -> MemorySearchResponse:
    if payload.types:
        unknown = [t for t in payload.types if t not in MEMORY_TYPES]
        if unknown:
            raise HTTPException(
                status_code=422, detail=f"Unknown memory types: {', '.join(unknown)}"
            )

    hits = await search_memories(
        session,
        query=payload.query,
        topic_id=payload.topic_id,
        project_id=payload.project_id,
        types=payload.types,
        limit=payload.limit,
    )
    return MemorySearchResponse(
        query=payload.query,
        count=len(hits),
        weights=explain_weights(),
        results=[
            MemorySearchHit(
                memory=MemoryOut.model_validate(hit.memory),
                score=hit.score,
                similarity=hit.similarity,
                components=hit.components,
            )
            for hit in hits
        ],
    )
