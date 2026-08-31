"""Minimal Redis-backed job queue.

Deliberately small: a Redis list plus JSON payloads. Phase 2 enqueues ingestion
jobs, Phase 4 enqueues agent runs. Swapping in arq/RQ later only touches this
module and the worker loop.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

import redis.asyncio as redis

from app.config import get_settings

QUEUE_KEY = "maws:jobs"
HEARTBEAT_KEY = "maws:worker:heartbeat"


@dataclass(frozen=True)
class Job:
    id: str
    type: str
    payload: dict[str, Any]

    def to_json(self) -> str:
        return json.dumps({"id": self.id, "type": self.type, "payload": self.payload})

    @classmethod
    def from_json(cls, raw: str) -> "Job":
        data = json.loads(raw)
        return cls(id=data["id"], type=data["type"], payload=data.get("payload", {}))


_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(get_settings().redis_url, decode_responses=True)
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
    _client = None


async def enqueue(job_type: str, payload: dict[str, Any] | None = None) -> Job:
    job = Job(id=str(uuid.uuid4()), type=job_type, payload=payload or {})
    await get_redis().rpush(QUEUE_KEY, job.to_json())
    return job


async def dequeue(timeout: int = 5) -> Job | None:
    """Blocking pop. Returns None when the timeout expires with no work.

    redis-py sets the socket read deadline from the BLPOP timeout, so an idle
    poll surfaces as redis.TimeoutError rather than an empty reply. That is a
    quiet "no work", not a failure.
    """
    try:
        result = await get_redis().blpop([QUEUE_KEY], timeout=timeout)
    except redis.TimeoutError:
        return None
    if result is None:
        return None
    _key, raw = result
    return Job.from_json(raw)


async def queue_depth() -> int:
    return int(await get_redis().llen(QUEUE_KEY))


async def beat(ttl_seconds: int) -> None:
    """Record that the worker is alive.

    The key expires, so a worker that dies stops being alive rather than
    leaving a stale claim behind. A queued job with no worker to consume it is
    invisible otherwise: it looked exactly like a run in progress for an hour.
    """
    import time

    await get_redis().set(HEARTBEAT_KEY, str(time.time()), ex=ttl_seconds)


async def worker_alive() -> bool:
    return await get_redis().exists(HEARTBEAT_KEY) == 1
