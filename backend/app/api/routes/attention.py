"""What needs the operator, ranked.

Its own route rather than a field on the system summary: the answer to "does
anything need me?" should be one request, and the same answer whichever screen
asks it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.orchestration.attention import AttentionItem, collect, explain_weights, rank
from app.orchestration.queue import queue_depth, worker_alive

router = APIRouter(tags=["attention"])
@router.get("/attention")
async def attention(
    limit: int = 20, session: AsyncSession = Depends(get_session)
) -> dict:
    """What needs the operator, ranked, across every project.

    A separate endpoint rather than a field on the summary: the answer to "does
    anything need me?" should be one request, and it should be the same answer
    whichever screen asks.
    """
    items: list[AttentionItem] = []

    # Nothing can run at all if the queue has work and no worker, so this
    # outranks anything project-specific.
    try:
        if not await worker_alive() and await queue_depth() > 0:
            items.append(
                AttentionItem(
                    kind="degraded_dependency",
                    title="Worker is not running",
                    why=f"{await queue_depth()} job(s) queued with nothing to consume them",
                    risk="high",
                    link="#overview",
                )
            )
    except Exception:  # noqa: BLE001 - Redis being down is itself the finding
        items.append(
            AttentionItem(
                kind="degraded_dependency",
                title="Job queue unreachable",
                why="Redis is not answering; async ingestion and runs cannot start",
                risk="high",
                link="#overview",
            )
        )

    items.extend(await collect(session))
    ranked = rank(items)

    return {
        "count": len(ranked),
        "needs_you": bool(ranked),
        "weights": explain_weights(),
        "items": [item.as_dict() for item in ranked[:limit]],
    }
