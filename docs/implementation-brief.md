# Multi-Agent Work System: Claude Code Implementation Brief

## Copy/Paste Prompt For Claude Code

You are implementing a local-first, Docker-deployable multi-agent work system.

The goal is to build a platform where I can:

1. Ingest all information related to a topic from work and other sources.
2. Create a project or task tied to that topic.
3. Have the system own the project through the SDLC.
4. Break the work into multiple tasks.
5. Assign tasks to specialist agents such as PM, Architect, Developer, QA, Reviewer, Security, and Domain Expert.
6. Surface decisions and questions only when human judgment is needed.
7. Produce final deliverables such as specs, implementation plans, PRs, test reports, release notes, and project summaries.

Build this in phases. Start with Phase 1 and do not skip verification. Prefer a working vertical slice over an overbuilt framework.

Use the implementation brief below as the source of truth.

## Product Summary

Build a self-hosted "mission control" system for AI-assisted software and knowledge work.

The system should combine:

- topic knowledge ingestion
- long-term project memory
- multi-agent orchestration
- task planning
- SDLC workflow management
- GitHub-aware delivery
- human-in-the-loop approval gates
- dashboard visibility

The platform should be local-first and run through Docker Compose.

## Preferred Stack

Use:

- Python 3.11+
- FastAPI for the backend API
- LangGraph / LangChain for orchestration
- Deep Agents if practical for planning, subagents, memory, filesystem workflows, and human-in-the-loop controls
- Postgres with pgvector for persistent storage and semantic search
- Redis for background jobs and queues
- React, Next.js, or Vite React for the dashboard
- Docker Compose for local deployment
- GitHub API or GitHub CLI integration
- Claude Code as the primary coding-agent runtime

Optional later:

- Graphiti / Neo4j for temporal entity memory
- Mem0 integration for externalized long-term memory
- OpenHands Agent Canvas or ACP support as an alternate control surface
- local models through Ollama, LM Studio, vLLM, or LiteLLM

## Core User Flows

### Flow 1: Ingest Topic Knowledge

User says:

> Ingest everything related to customer onboarding from this repo, these docs, and these GitHub issues.

System should:

1. Create or select a topic.
2. Register sources.
3. Extract text and metadata.
4. Chunk source content.
5. Generate embeddings.
6. Store source chunks.
7. Extract durable memories:
   - facts
   - decisions
   - constraints
   - risks
   - architecture notes
   - terms and definitions
   - people, teams, and systems
   - previous attempts
   - gotchas
8. Associate memories with topic, source, and optional project.
9. Produce an ingestion summary.

### Flow 2: Create Project From Topic

User says:

> Own the self-serve onboarding project. Use the customer onboarding topic memory.

System should:

1. Create a project.
2. Retrieve relevant topic memory.
3. Inspect registered project sources.
4. Generate a project brief.
5. Identify assumptions, unknowns, risks, and non-goals.
6. Create milestones and tasks.
7. Define acceptance criteria.
8. Create a question queue for human decisions.
9. Assign work to specialist agents.

### Flow 3: Run SDLC Workflow

System should move a project through:

1. Discovery
2. Planning
3. Architecture
4. Implementation
5. Verification
6. Review
7. Delivery
8. Learning

At the end, the system should produce:

- project summary
- task completion report
- implementation notes
- test report
- review report
- security review
- release notes
- durable lessons learned

### Flow 4: GitHub PR Review And Delivery

System should support:

- ingesting GitHub repos
- ingesting GitHub issues
- ingesting GitHub pull requests
- creating implementation branches
- drafting PR descriptions
- running code review agents
- running security review agents
- posting summaries or comments later if configured

For v1, GitHub integration may be read-only plus artifact generation. PR creation can be Phase 4.

## Architecture

Use this shape:

```text
Dashboard
  |
FastAPI Backend
  |
  |-- Topic ingestion service
  |-- Memory service
  |-- Project planning service
  |-- Agent orchestration service
  |-- Approval/question service
  |-- GitHub service
  |-- Artifact service
  |
Postgres + pgvector
Redis
Worker process
```

## Docker Deployment

Provide a `docker-compose.yml` with:

- `api`: FastAPI backend
- `worker`: background worker for ingestion and agent runs
- `postgres`: Postgres with pgvector
- `redis`: queue/cache
- `frontend`: dashboard

Persist Postgres and Redis data in named Docker volumes.

Add `.env.example` with:

```text
DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/agent_work
REDIS_URL=redis://redis:6379/0
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GITHUB_TOKEN=
EMBEDDING_MODEL=text-embedding-3-small
DEFAULT_AGENT_MODEL=claude-sonnet
APP_ENV=local
```

If Claude Code cannot be run directly from inside Docker, design the backend with an adapter interface so the first implementation can mock agent execution and later call Claude Code on the host.

## Repository Structure

Create this structure:

```text
.
├── docker-compose.yml
├── .env.example
├── README.md
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   ├── agents/
│   │   ├── db/
│   │   ├── github/
│   │   ├── ingestion/
│   │   ├── memory/
│   │   ├── orchestration/
│   │   ├── projects/
│   │   ├── approvals/
│   │   └── artifacts/
│   └── tests/
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   ├── lib/
│   │   └── styles/
└── docs/
    ├── architecture.md
    ├── agent-roles.md
    ├── operating-model.md
    └── memory-model.md
```

## Data Model

Implement database models for:

### Topic

Fields:

- id
- name
- description
- created_at
- updated_at

### Source

Fields:

- id
- topic_id
- type
- name
- uri
- metadata_json
- status
- created_at
- updated_at

Source types:

- local_folder
- local_file
- github_repo
- github_issue
- github_pr
- pasted_text
- url

### SourceChunk

Fields:

- id
- source_id
- topic_id
- content
- content_hash
- metadata_json
- embedding
- created_at

Use pgvector for `embedding`.

### Memory

Fields:

- id
- topic_id
- project_id nullable
- source_id nullable
- type
- content
- confidence
- importance
- metadata_json
- embedding
- created_at
- updated_at

Memory types:

- fact
- decision
- constraint
- risk
- architecture
- definition
- person
- system
- open_question
- lesson
- gotcha

### Project

Fields:

- id
- topic_id nullable
- name
- goal
- status
- brief
- created_at
- updated_at

Project statuses:

- draft
- planning
- ready
- running
- blocked
- review
- delivered
- archived

### Task

Fields:

- id
- project_id
- parent_task_id nullable
- title
- description
- agent_role
- status
- acceptance_criteria
- evidence
- created_at
- updated_at

Task statuses:

- backlog
- ready
- in_progress
- blocked
- review
- verified
- done

### AgentProfile

Fields:

- id
- name
- role
- system_prompt
- allowed_tools_json
- approval_rules_json
- created_at
- updated_at

### AgentRun

Fields:

- id
- project_id nullable
- task_id nullable
- agent_profile_id
- status
- input
- output
- error
- started_at
- completed_at

### Decision

Fields:

- id
- project_id
- question
- answer
- rationale
- decided_by
- created_at

### ApprovalRequest

Fields:

- id
- project_id nullable
- task_id nullable
- action_type
- action_summary
- risk_level
- status
- requested_by_agent_id
- response
- created_at
- updated_at

Statuses:

- pending
- approved
- rejected
- cancelled

### Artifact

Fields:

- id
- project_id
- task_id nullable
- type
- title
- content
- path nullable
- created_at

Artifact types:

- project_brief
- architecture_plan
- task_breakdown
- test_report
- review_report
- security_report
- pr_description
- release_notes
- final_summary

## Agent Roles

Create default agent profiles.

### Lead PM

Purpose:

- Owns project coordination.
- Converts vague requests into scoped plans.
- Creates tasks and milestones.
- Asks only blocking questions.
- Synthesizes agent outputs.

Prompt:

```text
You are the Lead PM agent. Your job is to turn vague goals into executable project plans. You coordinate other agents, maintain project state, and surface only decisions that materially affect scope, user behavior, security, cost, or irreversible changes. Prefer clear assumptions over excessive questioning. Always produce acceptance criteria and a next action.
```

### Architect

Purpose:

- Designs technical approach.
- Identifies systems touched.
- Flags tradeoffs, risks, and migration concerns.

Prompt:

```text
You are the Architect agent. Your job is to understand existing systems, propose implementation designs, identify integration points, and call out risks. Prefer existing project patterns. Avoid unnecessary new abstractions. Produce a concise architecture plan with impacted files, data changes, APIs, rollout notes, and risks.
```

### Software Developer

Purpose:

- Implements scoped tasks.
- Follows repo conventions.
- Produces implementation notes.

Prompt:

```text
You are the Software Developer agent. Your job is to implement scoped tasks according to the plan and project conventions. Keep changes focused. Prefer existing patterns. Add or update tests when behavior changes. Record what changed and any follow-up risks.
```

### QA/Test

Purpose:

- Defines verification strategy.
- Runs or recommends tests.
- Checks acceptance criteria.

Prompt:

```text
You are the QA/Test agent. Your job is to verify that project tasks meet acceptance criteria. Identify relevant tests, missing coverage, edge cases, and manual verification steps. Produce evidence for each acceptance criterion.
```

### Code Reviewer

Purpose:

- Reviews diffs and implementation artifacts.
- Finds bugs, regressions, missing tests, maintainability issues.

Prompt:

```text
You are the Code Reviewer agent. Your job is to review implementation work for correctness, regressions, maintainability, and missing tests. Prioritize real behavioral issues over style. Findings must include severity, evidence, and suggested fix.
```

### Security Reviewer

Purpose:

- Reviews auth, permissions, data handling, secrets, destructive actions, supply chain, and privacy risk.

Prompt:

```text
You are the Security Reviewer agent. Your job is to identify security and privacy risks. Focus on authentication, authorization, data leakage, secrets, injection, unsafe file operations, dependency risk, and irreversible actions. Be precise and evidence-based.
```

### Domain Expert

Purpose:

- Retrieves and applies topic-specific memory.
- Explains relevant terminology, constraints, history, and known failures.

Prompt:

```text
You are the Domain Expert agent. Your job is to apply durable topic memory to the current project. Retrieve relevant facts, decisions, constraints, prior attempts, risks, and gotchas. Explain what matters for this project and cite memory/source ids where possible.
```

### Release Manager

Purpose:

- Creates release notes, rollout plan, migration notes, final summary.

Prompt:

```text
You are the Release Manager agent. Your job is to prepare delivery artifacts: release notes, rollout checklist, migration notes, operational risks, monitoring suggestions, and final project summary.
```

## Human-In-The-Loop Rules

Do not ask approval for:

- reading registered sources
- summarizing content
- creating plans
- extracting memories
- semantic search
- creating draft artifacts
- running tests in a local or containerized environment
- making scoped edits in a feature branch

Ask approval before:

- deleting files
- changing production configuration
- changing database schema
- modifying auth, billing, permissions, security, or data retention behavior
- adding dependencies
- pushing to protected branches
- merging PRs
- deploying
- using external paid APIs not already configured
- accessing sources not registered by the user

## Memory Design

Use layered memory:

```text
Global memory:
  user preferences, operating rules, default approval rules

Organization memory:
  company-wide terms, systems, teams, policies

Topic memory:
  facts, decisions, risks, architecture notes, history for a domain

Project memory:
  project-specific scope, decisions, tasks, assumptions, status

Agent memory:
  role-specific lessons and successful patterns
```

For v1, implement topic and project memory first.

Memory retrieval should combine:

- semantic similarity
- recency
- importance
- source reliability
- project/topic match

Memory extraction should avoid storing every chunk as memory. Store durable, reusable knowledge.

## API Endpoints

Implement:

```text
GET  /health

POST /topics
GET  /topics
GET  /topics/{topic_id}

POST /topics/{topic_id}/sources
GET  /topics/{topic_id}/sources
POST /sources/{source_id}/ingest

GET  /topics/{topic_id}/memories
POST /memory/search

POST /projects
GET  /projects
GET  /projects/{project_id}
POST /projects/{project_id}/plan
POST /projects/{project_id}/run

GET  /projects/{project_id}/tasks
POST /projects/{project_id}/tasks
PATCH /tasks/{task_id}

GET  /projects/{project_id}/runs
GET  /projects/{project_id}/artifacts

GET  /projects/{project_id}/approvals
POST /approvals/{approval_id}/respond

GET  /projects/{project_id}/decisions
POST /projects/{project_id}/decisions
```

## Dashboard Requirements

Build a clean operational dashboard.

Views:

1. Topics
   - list topics
   - create topic
   - view topic sources
   - view memories
   - search memory

2. Topic Detail
   - sources
   - ingestion status
   - extracted memories
   - related projects

3. Projects
   - list projects
   - create project from topic
   - see status and progress

4. Project Detail
   - project brief
   - assumptions
   - task board
   - agent runs
   - decisions
   - approvals
   - artifacts

5. Task Board
   - backlog
   - ready
   - in progress
   - blocked
   - review
   - verified
   - done

6. Agent Runs
   - role
   - input
   - output
   - status
   - timestamps

7. Human Queue
   - questions
   - approval requests
   - risks needing user decision

Design should be utilitarian, dense, and easy to scan.

## Implementation Phases

### Phase 1: Working Skeleton

Build:

- Docker Compose
- FastAPI backend
- Postgres + pgvector
- Redis
- frontend shell
- health endpoint
- database migrations
- core models
- seed default agent profiles

Acceptance criteria:

- `docker compose up` starts the stack.
- Dashboard loads.
- API health endpoint works.
- Database persists across restarts.
- Default agent profiles exist.

### Phase 2: Topic Ingestion And Memory Search

Build:

- create topic
- register local folder/local file/pasted text source
- ingestion worker
- text extraction
- chunking
- embeddings
- source chunk storage
- memory extraction
- memory search
- topic memory dashboard

Acceptance criteria:

- User can create a topic.
- User can add a local file or pasted text source.
- User can run ingestion.
- System extracts chunks and memories.
- User can search topic memory.

### Phase 3: Project Planning

Build:

- create project from topic
- retrieve relevant memories
- Lead PM planning run
- Domain Expert context run
- Architect planning run
- task generation
- approval/question generation
- artifacts for project brief and task breakdown

Acceptance criteria:

- User can create a project tied to a topic.
- System creates a project brief.
- System creates tasks with acceptance criteria.
- System identifies assumptions and risks.
- Dashboard shows tasks, runs, and artifacts.

### Phase 4: SDLC Agent Loop

Build:

- agent run orchestration
- task status transitions
- QA pass
- reviewer pass
- security pass
- release manager final summary
- project learning memory extraction

Acceptance criteria:

- System can run PM, Architect, QA, Reviewer, Security, and Release passes.
- Each pass creates an AgentRun record.
- Review outputs become artifacts.
- Lessons learned are stored as memory.

### Phase 5: GitHub Integration

Build:

- GitHub repo ingestion
- issue ingestion
- PR ingestion
- branch/worktree planning
- PR description artifact
- optional PR creation

Acceptance criteria:

- User can add a GitHub repo/issue/PR as a source.
- System ingests GitHub content.
- System can generate PR review or PR description artifacts.

### Phase 6: Real Agent Runtime Adapter

Build adapter interface:

```text
AgentRuntime
  run(agent_profile, input, context) -> AgentRunResult
```

Implement:

- mock runtime for tests
- LangGraph/Deep Agents runtime
- optional Claude Code host adapter

Acceptance criteria:

- Agent orchestration is not hard-coded to one provider.
- Runtime can be swapped by config.
- Tests can run without external model calls.

## Agent Runtime Guidance

Start with a mock/runtime abstraction so development is deterministic.

Then implement a LangGraph/Deep Agents runtime that:

- accepts an agent role
- accepts project context
- retrieves relevant memory
- produces structured outputs
- records run state
- respects approval gates

Use Claude or GPT models through environment variables. Local model support can come later.

## Structured Outputs

Where possible, use structured outputs for:

- memory extraction
- project brief
- task breakdown
- risks
- approval requests
- review findings
- test evidence
- final summary

Example memory extraction schema:

```json
{
  "memories": [
    {
      "type": "decision",
      "content": "Invite links expire after 14 days.",
      "confidence": 0.91,
      "importance": 0.77,
      "metadata": {
        "source_quote": "Links should expire after two weeks",
        "system": "onboarding"
      }
    }
  ]
}
```

Example task schema:

```json
{
  "tasks": [
    {
      "title": "Design invite link data model",
      "description": "Define how invite tokens are stored, expired, and associated with organizations.",
      "agent_role": "Architect",
      "acceptance_criteria": [
        "Token expiry behavior is defined",
        "Security risks are identified",
        "Existing auth patterns are considered"
      ]
    }
  ]
}
```

## Testing Requirements

Add tests for:

- topic creation
- source registration
- text chunking
- memory extraction with mock model
- memory search
- project creation
- project planning with mock runtime
- approval gating
- task status transitions

Do not require live LLM API keys for the default test suite.

## Security Requirements

- Do not expose API keys in logs.
- Do not ingest files outside registered paths.
- Do not allow path traversal.
- Do not run shell commands from the dashboard in v1.
- Require explicit approval for destructive actions.
- Keep external integrations disabled unless configured.
- Store secrets in environment variables, not the database.

## README Requirements

Write a README with:

- what the system does
- quickstart
- environment setup
- Docker Compose commands
- how to create a topic
- how to ingest a source
- how to create a project
- how to run planning
- how memory works
- how agents work
- current limitations

## Definition Of Done For V1

The v1 is done when:

- The stack starts with Docker Compose.
- The dashboard loads.
- A topic can be created.
- A local file or pasted text can be ingested.
- Memories are extracted and searchable.
- A project can be created from a topic.
- The system generates a project brief.
- The system generates a task breakdown.
- Agent runs are recorded.
- Approval requests can be created and answered.
- Artifacts are persisted and visible.
- Tests pass without external model calls.

## Important Implementation Notes

- Keep the first version boring and reliable.
- Use adapters for model/runtime/provider-specific behavior.
- Avoid making every action autonomous at first.
- Focus on visibility, memory, planning, and approval gates.
- Do not overbuild the UI.
- Do not assume Claude Code can safely run inside Docker; abstract it.
- Prefer deterministic tests with mocked model outputs.
- Add clear extension points for GitHub, Slack, Google Drive, Linear, and local model support.

## Suggested First Command To Run In Claude Code

After opening a new empty repo, paste this:

```text
Implement Phase 1 of the Multi-Agent Work System brief in docs/implementation-brief.md.

Start by creating the repository structure, Docker Compose stack, FastAPI backend, Postgres/pgvector setup, Redis setup, database models/migrations, default agent profile seeding, frontend shell, health endpoint, and README quickstart.

Do not implement live LLM calls yet. Add mock runtime boundaries where needed. Add tests for the backend skeleton and model creation. Verify the stack can start locally.
```

