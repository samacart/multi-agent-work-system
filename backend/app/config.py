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

    # Which AgentRuntime implementation to use:
    #   mock         deterministic, offline, no provider (default)
    #   llm          Anthropic or OpenAI, chosen by DEFAULT_AGENT_MODEL
    #   langgraph    the llm runtime wrapped in a retrieve/generate/validate/repair graph
    #   claude_code  shells out to the Claude Code CLI on the host
    agent_runtime: str = "mock"

    # Claude Code host adapter. The CLI is not expected to exist inside the
    # API container; run the backend on the host to use it.
    claude_code_binary: str = "claude"
    claude_code_cwd: str = ""
    # Deep analytical passes over a large repository run long; 600s timed out
    # mid-run on a real project and cascaded to six skipped dependents.
    claude_code_timeout_seconds: int = 1800
    # Claude Code has real filesystem and shell access, and in headless `-p`
    # mode it edits without prompting. What each role may reach for comes from
    # its own profile now (app/agents/permissions.py); this list is applied on
    # top of every profile and is for what no role may ever do. It must not name
    # Edit, Write or bare Bash, or it would silently override the grants that
    # let the developer and QA roles work at all.
    claude_code_disallowed_tools: str = (
        "Bash(rm:*),Bash(sudo:*),Bash(curl:*),Bash(wget:*),Bash(ssh:*),Bash(git push:*)"
    )
    # Independent tasks in the same dependency wave run concurrently. Each pass
    # is a whole agent invocation, so this is the difference between a run
    # taking ten minutes and taking fifty.
    sdlc_max_parallel_tasks: int = 3
    # Retry a failed pass before blocking it. A timeout is usually transient,
    # and blocking on the first one takes every dependent task down with it.
    sdlc_task_retries: int = 1
    # How much of the workspace diff review passes are shown. A review that
    # cannot see the code is an opinion about the plan, not about the work.
    review_diff_max_chars: int = 60000
    # Reuse Claude Code sessions across passes so the repository is not
    # re-explored from cold each time. Off by default: the benefit is real but
    # unmeasured, and a reused session carries prior context into a later pass.
    claude_code_reuse_sessions: bool = False
    claude_code_allowed_tools: str = ""

    # Ingestion is restricted to paths under these roots.
    allowed_source_roots: str = "/data/sources"

    # Repositories a project may point its agents at. Deliberately separate from
    # the ingestion roots: those are read-only corpora, these are working trees
    # an agent executes in. Empty means no project may set a workspace, which
    # fails closed - an unset root is a missing decision, not permission.
    allowed_workspace_roots: str = ""

    # Embedding provider adapter:
    #   hash    deterministic, offline, lexical only, no dependencies
    #   ollama  real semantic embeddings from a local model, no credentials
    #   openai  hosted, requires OPENAI_API_KEY
    embedding_provider: str = "hash"
    ollama_base_url: str = "http://localhost:11434"

    # Memory extraction adapter. "heuristic" is deterministic and offline.
    memory_extractor: str = "heuristic"

    # Ingestion limits. A single oversized file should not stall the worker.
    max_source_file_bytes: int = 2_000_000
    max_folder_files: int = 500
    ingest_extensions: str = ".md,.txt,.rst,.py,.ts,.tsx,.js,.jsx,.json,.yaml,.yml,.toml,.sql,.sh,.html,.css,.java,.go,.rb,.rs"

    # A safety valve against runaway extraction, not a curation budget:
    # a 39-file corpus at 200 kept only five memories per document.
    max_memories_per_source: int = 1000

    # GitHub. Disabled unless a token is set; writes need a second opt-in.
    github_api_url: str = "https://api.github.com"
    github_allow_unauthenticated: bool = False
    github_allow_writes: bool = False
    github_max_files: int = 200

    chunk_max_chars: int = 1200
    chunk_overlap_chars: int = 150

    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_source_root_list(self) -> list[str]:
        return [p.strip() for p in self.allowed_source_roots.split(",") if p.strip()]

    @property
    def github_enabled(self) -> bool:
        """External integrations stay off unless explicitly configured."""
        return bool(self.github_token) or self.github_allow_unauthenticated

    @property
    def allowed_workspace_root_list(self) -> list[str]:
        return [p.strip() for p in self.allowed_workspace_roots.split(",") if p.strip()]

    @property
    def ingest_extension_set(self) -> set[str]:
        return {e.strip().lower() for e in self.ingest_extensions.split(",") if e.strip()}

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
