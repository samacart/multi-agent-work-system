"""Background worker.

Consumes jobs from Redis and dispatches on job type. Handlers register into
HANDLERS; one bad job is logged and dropped rather than killing the loop.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import text

from app.config import get_settings
from app.db.session import dispose_engine, get_sessionmaker
from app.orchestration.queue import Job, beat, close_redis, dequeue

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("worker")

Handler = Callable[[Job], Awaitable[dict[str, Any]]]


async def handle_ping(job: Job) -> dict[str, Any]:
    """Health job: touches the database so a queued job proves the full path."""
    async with get_sessionmaker()() as session:
        value = (await session.execute(text("SELECT 1"))).scalar_one()
    return {"pong": True, "db": value, "echo": job.payload}


async def handle_ingest_source(job: Job) -> dict[str, Any]:
    """Run the ingestion pipeline for one registered source."""
    from app.ingestion.service import ingest_source

    source_id = uuid.UUID(str(job.payload["source_id"]))
    async with get_sessionmaker()() as session:
        summary = await ingest_source(session, source_id)
    return summary.as_dict()


async def handle_run_project(job: Job) -> dict[str, Any]:
    """Run the SDLC loop for one project."""
    from app.orchestration.sdlc import run_project

    project_id = uuid.UUID(str(job.payload["project_id"]))
    roles = job.payload.get("roles")
    async with get_sessionmaker()() as session:
        result = await run_project(session, project_id, roles=set(roles) if roles else None)
    return result.as_dict()


HANDLERS: dict[str, Handler] = {
    "ping": handle_ping,
    "ingest_source": handle_ingest_source,
    "run_project": handle_run_project,
}


class Worker:
    def __init__(self) -> None:
        self._stopping = asyncio.Event()

    def request_stop(self, *_: object) -> None:
        log.info("stop requested, draining")
        self._stopping.set()

    async def run(self) -> None:
        settings = get_settings()
        log.info("worker starting (env=%s, runtime=%s)", settings.app_env, settings.agent_runtime)
        heartbeat_ttl = settings.worker_heartbeat_seconds * 3
        while not self._stopping.is_set():
            try:
                # Before dequeuing, so a worker blocked on an empty queue still
                # reports alive.
                await beat(heartbeat_ttl)
                job = await dequeue(timeout=5)
            except Exception:  # noqa: BLE001 - keep the loop alive on transient Redis errors
                log.exception("dequeue failed; retrying in 2s")
                await asyncio.sleep(2)
                continue

            if job is None:
                continue

            handler = HANDLERS.get(job.type)
            if handler is None:
                log.warning("no handler for job type %r (id=%s)", job.type, job.id)
                continue

            try:
                result = await handler(job)
                log.info("job %s (%s) ok: %s", job.id, job.type, result)
            except Exception:  # noqa: BLE001 - one bad job must not kill the worker
                log.exception("job %s (%s) failed", job.id, job.type)

        await close_redis()
        await dispose_engine()
        log.info("worker stopped")


def main() -> None:
    worker = Worker()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, worker.request_stop)
    loop.run_until_complete(worker.run())


if __name__ == "__main__":
    main()
