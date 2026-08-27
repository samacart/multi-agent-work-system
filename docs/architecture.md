# Architecture

## Shape

```text
Dashboard (Vite + React, :5173)
  |
  v
FastAPI backend (:8000)
  |-- Topic ingestion service      app/ingestion      (done)
  |-- Memory service               app/memory         (done)
  |-- Project planning service     app/projects       (Phase 3)
  |-- Approval/question service    app/approvals      (Phase 3)
  |-- Artifact service             app/artifacts      (Phase 3)
  |-- Agent orchestration service  app/orchestration  (Phase 4)
  |-- GitHub service               app/github         (Phase 5)
  |
  +-- Postgres 17 + pgvector   (durable state, semantic search)
  +-- Redis                    (job queue)
  +-- Worker process           (app/worker, consumes the queue)
```

Every service package exists from Phase 1 with the tables it will need, so later
phases add behaviour rather than schema churn.

## Key boundaries

**Agent runtime adapter** (`app/agents/runtime/base.py`). Nothing above this line
knows which provider executes an agent:

```python
class AgentRuntime(ABC):
    async def run(self, agent_profile, input, context) -> AgentRunResult: ...
```

Phase 1 ships `MockAgentRuntime` only — deterministic, offline, no API keys. The
runtime is selected by the `AGENT_RUNTIME` environment variable, so a
LangGraph/Deep Agents runtime or a Claude Code host adapter drops in without
touching orchestration code. Claude Code is deliberately *not* assumed to run
inside the container: a host adapter will reach out of the container instead.

**Job queue** (`app/orchestration/queue.py`). A Redis list plus JSON payloads.
Small on purpose — moving to arq/RQ later touches this module and the worker loop
and nothing else.

**Portable column types** (`app/db/types.py`). `Embedding` renders as pgvector
`VECTOR(1536)` on Postgres and as JSON elsewhere, which is what lets the default
test suite run on SQLite with no services.

## Request path

1. Compose starts Postgres and Redis and waits for their healthchecks.
2. The `api` container entrypoint runs `alembic upgrade head`, then serves.
3. On startup the app seeds default agent profiles (idempotent — safe every boot).
4. The `worker` container waits for the API to be healthy (so the schema exists)
   and then blocks on the queue.

## Data model

Eleven tables: `topics`, `sources`, `source_chunks`, `memories`, `projects`,
`tasks`, `agent_profiles`, `agent_runs`, `decisions`, `approval_requests`,
`artifacts`. See `backend/app/db/models.py`; the value sets for every status and
type field are module-level tuples in the same file.

Status and type columns are `VARCHAR` + `CHECK` constraint (`native_enum=False`),
not Postgres enums — adding a status later is a cheap migration, and a typo still
fails loudly at write time.

## Ingestion pipeline

```text
source -> documents -> chunks -> embeddings -> source_chunks
                                            -> memories -> embeddings -> memories
```

Re-ingesting is safe and cheap: chunks dedupe per source by content hash (there
is a unique constraint backing it), and memories dedupe across the whole topic,
so the same decision written in two places is stored once.

Failures are recorded, not raised: the source moves to `failed` and the reason
lands in `sources.metadata_json["last_ingestion"]`, visible in the dashboard.

Path safety is enforced in `app/ingestion/extract.py`: local paths are fully
resolved and must sit inside `ALLOWED_SOURCE_ROOTS`, which rejects absolute
paths outside the root, `..` traversal, and symlinks that point out of it.

## Deliberate omissions

- No live model calls anywhere.
- No authentication on the API. It binds to localhost via Compose; do not expose
  it to a network without adding auth first.
- No ingestion, planning, or orchestration logic — only the tables and packages
  they will live in.
