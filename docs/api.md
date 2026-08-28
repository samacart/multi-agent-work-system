# API reference

Generated from the live OpenAPI spec. The running stack serves the interactive
version at <http://localhost:8000/docs> and the raw schema at `/openapi.json` -
both are authoritative if this file drifts.

The typed client in `frontend/src/lib/api.ts` mirrors every response model here.

## Health and system

| Method | Path | What it does |
|---|---|---|
| `GET` | `/config` | Redacted runtime configuration. Never returns secret values. |
| `GET` | `/health` | Liveness. Always cheap, never touches dependencies. |
| `GET` | `/health/ready` | Readiness. Reports per-dependency status; 503 if anything is down. |
| `GET` | `/system/summary` | Summary |

## Topics, sources, memory

| Method | Path | What it does |
|---|---|---|
| `POST` | `/memory/search` | Search |
| `GET` | `/sources/{source_id}` | Get Source |
| `POST` | `/sources/{source_id}/ingest` | Start Ingestion |
| `GET` | `/topics` | List Topics |
| `POST` | `/topics` | Create Topic |
| `GET` | `/topics/{topic_id}` | Get Topic |
| `GET` | `/topics/{topic_id}/memories` | List Memories |
| `POST` | `/topics/{topic_id}/sources` | Register Source |
| `GET` | `/topics/{topic_id}/sources` | List Sources |

## Projects and planning

| Method | Path | What it does |
|---|---|---|
| `GET` | `/projects` | List Projects |
| `POST` | `/projects` | Create Project |
| `GET` | `/projects/{project_id}` | Get Project |
| `POST` | `/projects/{project_id}/plan` | Run Planning |
| `POST` | `/projects/{project_id}/run` | Run the SDLC loop over the project's planned tasks. |

## Tasks

| Method | Path | What it does |
|---|---|---|
| `GET` | `/projects/{project_id}/tasks` | List Tasks |
| `POST` | `/projects/{project_id}/tasks` | Create Task |
| `PATCH` | `/tasks/{task_id}` | Update Task |

## Runs, artifacts, human queue

| Method | Path | What it does |
|---|---|---|
| `POST` | `/approvals/{approval_id}/respond` | Respond Approval |
| `POST` | `/decisions/{decision_id}/answer` | Answer Decision |
| `GET` | `/projects/{project_id}/approvals` | List Approvals |
| `GET` | `/projects/{project_id}/artifacts` | List Artifacts |
| `GET` | `/projects/{project_id}/decisions` | List Decisions |
| `POST` | `/projects/{project_id}/decisions` | Create Decision |
| `GET` | `/projects/{project_id}/runs` | List Runs |

## GitHub

| Method | Path | What it does |
|---|---|---|
| `GET` | `/github/status` | Whether the integration is usable, without revealing the token. |
| `GET` | `/projects/{project_id}/branch` | Planned Branch |
| `POST` | `/projects/{project_id}/pr-description` | Pr Description |
| `POST` | `/projects/{project_id}/pull-request` | Open Pull Request |

## Agents

| Method | Path | What it does |
|---|---|---|
| `GET` | `/agent-profiles` | List Agent Profiles |
| `GET` | `/agent-profiles/{profile_id}` | Get Agent Profile |

## Notes for consumers

- `GET /health/ready` answers **503** with a useful body when a dependency is
  down. Treat that as data, not as a failed request.
- `POST /sources/{id}/ingest` and `POST /projects/{id}/run` accept
  `?mode=async` to hand the work to the background worker; the response is
  **202** and the source/project status flips to `ingesting`/`running` for
  polling. Default is synchronous.
- `POST /projects/{id}/plan` answers **422** with the full result body when
  planning fails - the failure is recorded on the project and its runs.
- `PATCH /tasks/{id}` rejects an illegal status move with **409** and a message
  naming what is allowed from the current status.
- `POST /projects/{id}/pull-request` answers **409** with an `approval_id` when
  the gate has not been approved. That is the expected path, not an error.
- `GET /config` and `GET /github/status` never return secret values.
