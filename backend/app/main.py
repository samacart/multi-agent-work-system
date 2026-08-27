"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import get_settings
from app.db.seed import seed_agent_profiles
from app.db.session import dispose_engine, get_sessionmaker
from app.orchestration.queue import close_redis

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    log.info("starting %s (env=%s)", settings.app_name, settings.app_env)
    log.info("config: %s", settings.safe_dump())

    # Migrations run in the container entrypoint before the app boots; seeding is
    # idempotent so it is safe on every start.
    try:
        async with get_sessionmaker()() as session:
            await seed_agent_profiles(session)
    except Exception:  # noqa: BLE001 - a seed failure must not make the API unbootable
        log.exception("agent profile seeding failed; continuing (check /health/ready)")

    yield

    await close_redis()
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Local-first multi-agent work system. Phase 1: working skeleton.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)
    return app


app = create_app()
