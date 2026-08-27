"""Test fixtures.

The default suite runs entirely offline: SQLite for the database, a fake Redis
for the queue, and the mock agent runtime. No API keys, no Docker, no network.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

# Forced, not setdefault: the suite must be hermetic even when it runs inside a
# container whose DATABASE_URL/REDIS_URL point at real services.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://127.0.0.1:6399/15"  # deliberately nothing listening
os.environ["APP_ENV"] = "test"

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db import models  # noqa: E402,F401 - registers tables
from app.db.session import get_session  # noqa: E402


@pytest_asyncio.fixture
async def engine():
    # StaticPool keeps a single in-memory database across connections.
    from sqlalchemy.pool import StaticPool

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session


@pytest_asyncio.fixture
async def client(engine) -> AsyncIterator[AsyncClient]:
    """API client wired to the test database, with lifespan startup skipped."""
    from app.main import create_app

    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with maker() as s:
            yield s

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
