# Multi-Agent Work System

A local-first, Docker-deployable "mission control" for AI-assisted software and
knowledge work. Ingest everything about a topic, create a project from it, and
let specialist agents (PM, Architect, Developer, QA, Reviewer, Security, Domain
Expert, Release Manager) own it through the SDLC — surfacing decisions only when
human judgement is actually needed, and producing real deliverables: specs,
plans, PRs, test reports, release notes, project summaries.

**Status: Phase 4 complete.** Topics can be ingested, their memory is searchable, and
a project created from a topic gets planned into a brief, an architecture plan,
tasks with acceptance criteria, queued questions, and approval gates - then run
through the SDLC loop, producing test, review, security, and delivery reports
and writing what it learned back to topic memory. Everything runs offline by
default - no API keys needed.
See [Current limitations](#current-limitations).

## Quickstart

Requires Docker (with Compose v2) and about 1.5 GB of disk for images.

```bash
cp .env.example .env
docker compose up --build
```

Then:

- Dashboard — <http://localhost:5173>
- API docs — <http://localhost:8000/docs>
- Health — <http://localhost:8000/health>

No API keys are needed for Phase 1 — leave the key fields in `.env` empty.

```bash
docker compose ps                 # service status
docker compose logs -f api        # follow the API
docker compose down               # stop, keep data
docker compose down -v            # stop and destroy the volumes
```

Data lives in the named volumes `postgres_data` and `redis_data`, so it survives
`docker compose down` and restarts.

## Environment

Everything is configured through `.env` (see `.env.example`). Secrets are read
from the environment only — they are never written to the database, and
`GET /config` redacts them.

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@postgres:5432/agent_work` | Must match the `POSTGRES_*` vars |
| `REDIS_URL` | `redis://redis:6379/0` | Job queue |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GITHUB_TOKEN` | empty | Unused in Phase 1 |
| `EMBEDDING_MODEL` / `EMBEDDING_DIM` | `text-embedding-3-small` / `1536` | The dimension is pinned in migration `0001` |
| `EMBEDDING_PROVIDER` | `hash` | `hash` is offline and deterministic; `openai` needs `OPENAI_API_KEY` |
| `MEMORY_EXTRACTOR` | `heuristic` | Offline rule-based extraction |
| `CHUNK_MAX_CHARS` / `CHUNK_OVERLAP_CHARS` | `1200` / `150` | Chunking |
| `DEFAULT_AGENT_MODEL` | `claude-sonnet` | Used from Phase 6 |
| `AGENT_RUNTIME` | `mock` | Selects the runtime adapter; `mock` is the only one shipped |
| `SOURCES_DIR` / `ALLOWED_SOURCE_ROOTS` | `./data/sources` / `/data/sources` | Host dir mounted read-only; ingestion may not read outside it |
| `API_PORT` / `FRONTEND_PORT` | `8000` / `5173` | Host ports |

## Backend development

```bash
cd backend
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/python -m pytest -q
```

The default suite runs fully offline — SQLite instead of Postgres, no Redis, no
model calls, no API keys — so it needs nothing running. `Embedding` columns fall
back to JSON on SQLite (`backend/app/db/types.py`), which is what makes that
possible. Inside Docker: `docker compose run --rm api ./entrypoint.sh test`.

Migrations run automatically in the `api` container entrypoint. Manually:

```bash
docker compose run --rm api ./entrypoint.sh migrate
# new migration, against the running postgres:
cd backend && DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/agent_work" \
  .venv/bin/alembic revision --autogenerate -m "your change"
```

## Frontend development

```bash
cd frontend && npm install && npm run dev
```

Utilitarian and dense on purpose: React + Vite, no UI framework, no router.
`VITE_API_BASE_URL` points it at the API.

## Endpoints today

```text
GET /health              liveness
GET /health/ready        readiness: per-dependency status, 503 when degraded
GET /config              redacted runtime configuration
GET /agent-profiles      the eight seeded specialist agents
GET /agent-profiles/{id}
GET /system/summary      phase, runtime, row counts per table
```

The full endpoint surface from the brief (`/topics`, `/projects`, `/memory/search`,
`/approvals/...`) lands in Phases 2–4.

## How the pieces work

**Topics and memory.** A topic collects sources (local file/folder, pasted text,
URL, GitHub repo/issue/PR). Ingestion chunks them into `source_chunks` with
embeddings, then extracts durable `memories` — facts, decisions, constraints,
risks, architecture notes, definitions, people, systems, open questions, lessons,
gotchas — each carrying confidence, importance, and the source quote it came
from. Retrieval blends semantic similarity with recency, importance, source
reliability, and topic/project match. See [docs/memory-model.md](docs/memory-model.md).

**Projects and agents.** A project is created from a topic, planned by the Lead
PM with Domain Expert and Architect input, and broken into tasks with acceptance
criteria. Each task is assigned an agent role. Every execution is an `agent_runs`
row with its input, output, and status; every deliverable is an `artifacts` row.
See [docs/agent-roles.md](docs/agent-roles.md).

**Agent runtime.** Everything goes through one adapter —
`run(agent_profile, input, context) -> AgentRunResult` — selected by
`AGENT_RUNTIME`. Phase 1 ships the deterministic mock. Claude Code is
deliberately not assumed to run inside the container; a host adapter will call
out to it. See [docs/architecture.md](docs/architecture.md).

**Human-in-the-loop.** Reversible, scoped work (reading registered sources,
planning, extracting memory, searching, drafting artifacts, running tests,
scoped edits on a feature branch) never asks. Irreversible or out-of-scope work
(deleting files, schema changes, dependency additions, touching auth/billing/
permissions, pushing to protected branches, merging, deploying, paid APIs,
unregistered sources) always asks. Questions go to `decisions`, specific actions
go to `approval_requests`. See [docs/operating-model.md](docs/operating-model.md).

## Roadmap

| Phase | Scope | Status |
|---|---|---|
| 1 | Working skeleton: Compose, FastAPI, Postgres+pgvector, Redis, dashboard shell, migrations, core models, seeded agent profiles | **Done** |
| 2 | Topic ingestion and memory search | **Done** |
| 3 | Project planning: brief, tasks, assumptions, approvals, artifacts | **Done** |
| 4 | SDLC agent loop: QA, review, security, release passes, lessons learned | **Done** |
| 5 | GitHub integration: repo/issue/PR ingestion, PR descriptions | Next |
| 6 | Real agent runtime adapter: LangGraph/Deep Agents, Claude Code host adapter | |

The full source-of-truth spec is [docs/implementation-brief.md](docs/implementation-brief.md).

## Current limitations

- **No agent does real work yet.** The only runtime is the mock; it makes no
  network calls and returns a canned structured result.
- **No ingestion, planning, or orchestration.** The tables, packages, and queue
  exist; the logic arrives in Phases 2–4.
- **No authentication on the API.** Compose binds it to localhost. Do not expose
  it to a network without adding auth.
- **Approval gates block roles, not individual tool calls.** While a gate is
  pending the SDLC loop refuses to run developer, architect, or release work.
  Per-action gating at the point a runtime calls a tool arrives with a real
  runtime in Phase 6.
- **Postgres-only in production.** The SQLite fallback exists for the test suite;
  pgvector search requires Postgres.
- **`EMBEDDING_DIM` is pinned to 1536** in migration `0001`. Changing it requires
  a new migration that alters both embedding columns.
- **Single-user, local-first.** No multi-tenancy, no RBAC.
