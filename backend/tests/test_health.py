"""Health endpoints."""

from __future__ import annotations


async def test_health_is_ok(client):
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"


async def test_readiness_reports_each_dependency(client):
    """Redis is not running in the default suite, so readiness must report
    degraded rather than crash."""
    response = await client.get("/health/ready")
    assert response.status_code in (200, 503)
    checks = response.json()["checks"]
    assert set(checks) == {"database", "redis", "worker"}
    assert checks["database"]["status"] == "ok"


async def test_config_endpoint_redacts_secrets(client, monkeypatch):
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-super-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:hunter2@postgres:5432/agent_work")
    try:
        response = await client.get("/config")
        assert response.status_code == 200
        body = response.json()
        raw = response.text
        assert body["anthropic_api_key"] == "set"
        assert "sk-ant-super-secret" not in raw
        assert "hunter2" not in raw
        assert body["database_url"] == "postgresql+asyncpg://***@postgres:5432/agent_work"
    finally:
        get_settings.cache_clear()


async def test_readiness_reports_a_dead_worker(client, monkeypatch):
    """A queued job with no worker to consume it is otherwise invisible: the
    request succeeds, the job never runs, and it reads as progress."""
    import app.api.routes.health as health

    class LiveRedis:
        async def ping(self):  # noqa: ANN201
            return True

    monkeypatch.setattr(health, "get_redis", lambda: LiveRedis())
    monkeypatch.setattr(health, "queue_depth", lambda: _async(3))
    monkeypatch.setattr(health, "worker_alive", lambda: _async(False))

    body = (await client.get("/health/ready")).json()

    assert body["checks"]["worker"]["status"] == "error"
    assert "queued jobs will not run" in body["checks"]["worker"]["detail"]
    assert body["checks"]["worker"]["queue_depth"] == 3
    assert body["status"] == "degraded"


async def test_readiness_is_ready_when_the_worker_is_beating(client, monkeypatch):
    import app.api.routes.health as health

    class LiveRedis:
        async def ping(self):  # noqa: ANN201
            return True

    monkeypatch.setattr(health, "get_redis", lambda: LiveRedis())
    monkeypatch.setattr(health, "queue_depth", lambda: _async(0))
    monkeypatch.setattr(health, "worker_alive", lambda: _async(True))

    body = (await client.get("/health/ready")).json()
    assert body["checks"]["worker"]["status"] == "ok"


async def _async(value):  # noqa: ANN001, ANN202
    return value
