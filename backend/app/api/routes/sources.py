"""Source ingestion."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import SourceOut
from app.db.models import Source
from app.db.session import get_session
from app.ingestion.service import ingest_source
from app.orchestration.queue import enqueue

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("/{source_id}", response_model=SourceOut)
async def get_source(source_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> Source:
    source = await session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


@router.post("/{source_id}/ingest")
async def start_ingestion(
    source_id: uuid.UUID,
    response: Response,
    mode: str = Query(default="async", pattern="^(async|sync)$", description="'sync' runs inline; useful for debugging"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    source = await session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")

    if mode == "sync":
        summary = await ingest_source(session, source_id)
        if summary.status == "failed":
            # The failure is recorded on the source; report it rather than 500.
            response.status_code = 422
        return {"mode": "sync", "summary": summary.as_dict()}

    try:
        job = await enqueue("ingest_source", {"source_id": str(source_id)})
    except Exception as exc:  # noqa: BLE001 - Redis down is an operational state, not a bug
        raise HTTPException(
            status_code=503,
            detail=f"Job queue unavailable ({type(exc).__name__}). Retry, or use ?mode=sync.",
        ) from exc

    source.status = "ingesting"
    await session.commit()
    response.status_code = 202
    return {"mode": "async", "job_id": job.id, "source_id": str(source_id), "status": "ingesting"}
