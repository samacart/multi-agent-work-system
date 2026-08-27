"""Job queue serialisation.

The Redis round-trip itself is covered by the Docker smoke check; here we pin
the payload format the worker depends on.
"""

from __future__ import annotations

from app.orchestration.queue import Job


def test_job_round_trips_through_json():
    job = Job(id="abc", type="ping", payload={"n": 1, "nested": {"ok": True}})
    restored = Job.from_json(job.to_json())
    assert restored == job


def test_job_without_payload_defaults_to_empty_dict():
    restored = Job.from_json('{"id": "x", "type": "ping"}')
    assert restored.payload == {}


async def test_idle_dequeue_returns_none_not_an_error(monkeypatch):
    """An empty blocking pop must read as 'no work', not as a failed dequeue."""
    import redis.asyncio as redis_async

    from app.orchestration import queue

    class IdleRedis:
        async def blpop(self, _keys, timeout=0):  # noqa: ANN001, ANN201, ARG002
            raise redis_async.TimeoutError("Timeout reading from redis:6379")

    monkeypatch.setattr(queue, "get_redis", lambda: IdleRedis())
    assert await queue.dequeue(timeout=1) is None
