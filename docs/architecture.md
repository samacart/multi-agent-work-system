# Architecture

## Shape

```text
Dashboard (Vite + React, :5173)
  |
  v
FastAPI backend (:8000)
  |-- Topic ingestion service      app/ingestion      (done)
  |-- Memory service               app/memory         (done)
  |-- Project planning service     app/projects       (done)
  |-- Approval/question service    app/approvals      (done)
  |-- Artifact service             app/artifacts       (done)
  |-- Agent orchestration service  app/orchestration  (done)
  |-- GitHub service               app/github         (done)
  |
  +-- Postgres 17 + pgvector   (durable state, semantic search)
  +-- Redis                    (job queue)
  +-- Worker process           (app/worker, consumes the queue)
```

Every service package existed from Phase 1 with the tables it would need, so
later phases added behaviour rather than schema churn.

## Key boundaries

**Agent runtime adapter** (`app/agents/runtime/base.py`). Nothing above this line
knows which provider executes an agent:

```python
class AgentRuntime(ABC):
    async def run(self, agent_profile, input, context) -> AgentRunResult: ...
```

Four implementations, selected by `AGENT_RUNTIME`:

| Runtime | What it is | Needs |
|---|---|---|
| `mock` | Deterministic rule-based scaffolding. Composes valid outputs from the project goal and retrieved memory. No network. | nothing |
| `llm` | Anthropic or OpenAI over HTTP, forced into the contract's JSON schema, with one repair retry. | an API key |
| `langgraph` | The `llm` runtime inside a `prepare → generate → validate → repair` state graph with a bounded attempt count. | the `[langgraph]` extra |
| `claude_code` | Shells out to the Claude Code CLI - the only runtime that can read a repository, edit files, and run tests. | the CLI on PATH |

Claude Code is deliberately **not** assumed to run inside the container. Run the
backend on the host to use it, or point `CLAUDE_CODE_BINARY` at a wrapper.

**Structured output contracts** (`app/agents/contracts.py`). Every planning and
review step asks a runtime for one named output and validates the reply against
a Pydantic model. A runtime that answers in the wrong shape produces a failed
run with the validation error attached - never a half-shaped object reaching the
database. This is what actually makes the runtimes interchangeable.

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
