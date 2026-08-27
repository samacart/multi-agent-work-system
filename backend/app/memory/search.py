"""Memory retrieval.

Scoring blends semantic similarity with the signals the brief calls for:
recency, importance, source reliability, and topic/project match. Similarity
alone surfaces things that merely sound relevant; the other terms are what make
an old low-confidence aside lose to a recent explicit decision.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import Select, select, text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Memory, Source
from app.memory.embeddings import cosine_similarity, get_embedding_provider

# Weights sum to 1.0. Similarity dominates; the rest break ties sensibly.
WEIGHTS = {
    "similarity": 0.55,
    "importance": 0.15,
    "confidence": 0.10,
    "recency": 0.10,
    "reliability": 0.05,
    "scope": 0.05,
}

RECENCY_HALF_LIFE_DAYS = 45.0

# How many nearest neighbours to pull before re-ranking with the other signals.
CANDIDATE_MULTIPLIER = 5
MIN_CANDIDATES = 50


@dataclass
class ScoredMemory:
    memory: Memory
    score: float
    similarity: float
    components: dict[str, float]


def recency_score(created_at: datetime | None, now: datetime | None = None) -> float:
    """Exponential decay - a memory keeps half its recency credit every 45 days."""
    if created_at is None:
        return 0.0
    now = now or datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (now - created_at).total_seconds() / 86400.0)
    return 0.5 ** (age_days / RECENCY_HALF_LIFE_DAYS)


def _reliability(source: Source | None) -> float:
    """Source reliability, from the source's own metadata.

    Registered-by-a-human sources beat scraped ones; an explicit override in
    `metadata_json["reliability"]` wins over both.
    """
    if source is None:
        return 0.5
    override = source.metadata_json.get("reliability") if isinstance(source.metadata_json, dict) else None
    if isinstance(override, (int, float)):
        return max(0.0, min(1.0, float(override)))
    return {
        "pasted_text": 0.8,
        "local_file": 0.75,
        "local_folder": 0.7,
        "github_pr": 0.7,
        "github_issue": 0.65,
        "github_repo": 0.7,
        "url": 0.5,
    }.get(source.type, 0.5)


def _scope_score(memory: Memory, topic_id: uuid.UUID | None, project_id: uuid.UUID | None) -> float:
    """Reward memories scoped to what the caller is actually working on."""
    score = 0.0
    if topic_id is not None and memory.topic_id == topic_id:
        score += 0.5
    if project_id is not None and memory.project_id == project_id:
        score += 0.5
    elif project_id is not None and memory.project_id is None:
        # Topic-level memory is still relevant to a project, just less specific.
        score += 0.25
    if topic_id is None and project_id is None:
        score = 0.5
    return min(1.0, score)


def _base_query(
    topic_id: uuid.UUID | None,
    project_id: uuid.UUID | None,
    types: list[str] | None,
) -> Select:
    stmt = select(Memory)
    if topic_id is not None:
        stmt = stmt.where(Memory.topic_id == topic_id)
    if project_id is not None:
        stmt = stmt.where(Memory.project_id == project_id)
    if types:
        stmt = stmt.where(Memory.type.in_(types))
    return stmt


async def _postgres_candidates(
    session: AsyncSession,
    query_vector: list[float],
    topic_id: uuid.UUID | None,
    project_id: uuid.UUID | None,
    types: list[str] | None,
    limit: int,
) -> list[Memory]:
    """Nearest neighbours via pgvector, so the whole table is never loaded."""
    conditions = ["embedding IS NOT NULL"]
    params: dict[str, object] = {"q": "[" + ",".join(f"{v:.6f}" for v in query_vector) + "]", "k": limit}
    if topic_id is not None:
        conditions.append("topic_id = :topic_id")
        params["topic_id"] = topic_id
    if project_id is not None:
        conditions.append("project_id = :project_id")
        params["project_id"] = project_id
    if types:
        conditions.append("type = ANY(:types)")
        params["types"] = types

    stmt = sql_text(
        f"SELECT id FROM memories WHERE {' AND '.join(conditions)} "  # noqa: S608 - conditions are literals, values are bound
        "ORDER BY embedding <=> CAST(:q AS vector) LIMIT :k"
    )
    ids = [row[0] for row in (await session.execute(stmt, params)).all()]
    if not ids:
        return []
    rows = (await session.scalars(select(Memory).where(Memory.id.in_(ids)))).all()
    order = {mid: i for i, mid in enumerate(ids)}
    return sorted(rows, key=lambda m: order[m.id])


async def search_memories(
    session: AsyncSession,
    query: str,
    topic_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    types: list[str] | None = None,
    limit: int = 10,
    min_score: float = 0.0,
) -> list[ScoredMemory]:
    provider = get_embedding_provider()
    query_vector = await provider.embed_one(query)

    candidate_limit = max(MIN_CANDIDATES, limit * CANDIDATE_MULTIPLIER)
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        candidates = await _postgres_candidates(
            session, query_vector, topic_id, project_id, types, candidate_limit
        )
    else:
        candidates = list((await session.scalars(_base_query(topic_id, project_id, types))).all())

    if not candidates:
        return []

    source_ids = {m.source_id for m in candidates if m.source_id}
    sources: dict[uuid.UUID, Source] = {}
    if source_ids:
        sources = {
            s.id: s for s in (await session.scalars(select(Source).where(Source.id.in_(source_ids)))).all()
        }

    now = datetime.now(timezone.utc)
    scored: list[ScoredMemory] = []
    for memory in candidates:
        similarity = cosine_similarity(query_vector, memory.embedding or [])
        components = {
            # Cosine runs -1..1; map to 0..1 so one negative term cannot dominate.
            "similarity": (similarity + 1.0) / 2.0,
            "importance": float(memory.importance),
            "confidence": float(memory.confidence),
            "recency": recency_score(memory.created_at, now),
            "reliability": _reliability(sources.get(memory.source_id) if memory.source_id else None),
            "scope": _scope_score(memory, topic_id, project_id),
        }
        score = sum(WEIGHTS[k] * v for k, v in components.items())
        if score >= min_score:
            scored.append(
                ScoredMemory(
                    memory=memory,
                    score=round(score, 4),
                    similarity=round(similarity, 4),
                    components={k: round(v, 4) for k, v in components.items()},
                )
            )

    scored.sort(key=lambda s: (s.score, s.similarity), reverse=True)
    return scored[:limit]


def explain_weights() -> dict[str, float]:
    """Exposed so the dashboard can show why a result ranked where it did."""
    return dict(WEIGHTS)


assert math.isclose(sum(WEIGHTS.values()), 1.0), "retrieval weights must sum to 1.0"
