"""Health and readiness."""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.config import get_settings
from app.db.session import get_sessionmaker
from app.orchestration.queue import get_redis, queue_depth, worker_alive

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, object]:
    """Liveness. Always cheap, never touches dependencies."""
    settings = get_settings()
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env, "version": "0.1.0"}


@router.get("/health/ready")
async def readiness(response: Response) -> dict[str, object]:
    """Readiness. Reports per-dependency status; 503 if anything is down."""
    checks: dict[str, object] = {}

    try:
        async with get_sessionmaker()() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok"}
    except Exception as exc:  # noqa: BLE001 - report, do not leak internals to logs as errors
        checks["database"] = {"status": "error", "detail": type(exc).__name__}

    try:
        await get_redis().ping()
        depth = await queue_depth()
        checks["redis"] = {"status": "ok", "queue_depth": depth}
        # A queued job with no worker to consume it is invisible otherwise:
        # the request succeeds, the job never runs, and it reads as progress.
        alive = await worker_alive()
        checks["worker"] = {
            "status": "ok" if alive else "error",
            "detail": None if alive else "no heartbeat; queued jobs will not run",
            "queue_depth": depth,
        }
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = {"status": "error", "detail": type(exc).__name__}
        checks["worker"] = {"status": "error", "detail": "redis unavailable"}

    ready = all(c.get("status") == "ok" for c in checks.values())  # type: ignore[union-attr]
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if ready else "degraded", "checks": checks}


@router.get("/config")
async def config() -> dict[str, object]:
    """Redacted runtime configuration. Never returns secret values."""
    return get_settings().safe_dump()
