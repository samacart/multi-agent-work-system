"""Health and readiness."""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.config import get_settings
from app.db.session import get_sessionmaker
from app.orchestration.queue import get_redis, queue_depth

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
        checks["redis"] = {"status": "ok", "queue_depth": await queue_depth()}
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = {"status": "error", "detail": type(exc).__name__}

    ready = all(c.get("status") == "ok" for c in checks.values())  # type: ignore[union-attr]
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if ready else "degraded", "checks": checks}


@router.get("/config")
async def config() -> dict[str, object]:
    """Redacted runtime configuration. Never returns secret values."""
    return get_settings().safe_dump()
