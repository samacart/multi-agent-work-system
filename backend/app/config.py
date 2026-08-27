"""Application settings.

Secrets live in environment variables only, never in the database.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

SECRET_FIELDS = {"openai_api_key", "anthropic_api_key", "github_token"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    app_name: str = "Multi-Agent Work System"

    database_url: str = "postgresql+asyncpg://postgres:postgres@postgres:5432/agent_work"
    redis_url: str = "redis://redis:6379/0"

    # Model/provider configuration. Phase 1 makes no live model calls.
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    github_token: str | None = None
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    default_agent_model: str = "claude-sonnet"

    # Which AgentRuntime implementation to use. Phase 1 ships "mock" only.
    agent_runtime: str = "mock"

    # Ingestion (Phase 2) is restricted to paths under these roots.
    allowed_source_roots: str = "/data/sources"

    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_source_root_list(self) -> list[str]:
        return [p.strip() for p in self.allowed_source_roots.split(",") if p.strip()]

    def safe_dump(self) -> dict[str, object]:
        """Settings snapshot with every secret redacted. Safe for logs and API."""
        out: dict[str, object] = {}
        for name in type(self).model_fields:
            value = getattr(self, name)
            if name in SECRET_FIELDS:
                out[name] = "set" if value else "unset"
            elif name in {"database_url", "redis_url"}:
                out[name] = redact_url(str(value))
            else:
                out[name] = value
        return out


def redact_url(url: str) -> str:
    """Strip credentials out of a connection URL before it is shown or logged."""
    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" not in rest:
        return url
    _creds, host = rest.rsplit("@", 1)
    return f"{scheme}://***@{host}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
