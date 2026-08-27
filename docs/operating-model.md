# Operating model

## SDLC stages

A project moves through: **Discovery → Planning → Architecture → Implementation
→ Verification → Review → Delivery → Learning**.

`projects.status` tracks where it is: `draft`, `planning`, `ready`, `running`,
`blocked`, `review`, `delivered`, `archived`.

Tasks move through: `backlog`, `ready`, `in_progress`, `blocked`, `review`,
`verified`, `done`.

At Delivery the system should have produced: project summary, task completion
report, implementation notes, test report, review report, security review,
release notes, and durable lessons learned — each an `artifacts` row.

## Human-in-the-loop

The default posture is: act autonomously on reversible, scoped work; stop for
anything irreversible or outside the registered blast radius.

**Never gated** (`auto_approved`):

- reading registered sources
- summarizing content
- creating plans
- extracting memories
- semantic search
- creating draft artifacts
- running tests in a local or containerized environment
- making scoped edits in a feature branch

**Always gated** (`requires_approval`):

- deleting files
- changing production configuration
- changing database schema
- modifying auth, billing, permissions, security, or data retention behaviour
- adding dependencies
- pushing to protected branches
- merging PRs
- deploying
- using external paid APIs not already configured
- accessing sources not registered by the user

Both lists live in `backend/app/agents/profiles.py` and are stamped onto every
seeded profile as `approval_rules_json`.

## Questions vs approvals

Two different queues, both surfaced in the dashboard's **Human queue**:

- **`decisions`** — an open question that needs judgement (`question`, `answer`,
  `rationale`, `decided_by`). Agents should only raise ones that materially
  affect scope, user behaviour, security, cost, or irreversibility. Prefer a
  stated assumption over a question.
- **`approval_requests`** — a specific action an agent wants to take
  (`action_type`, `action_summary`, `risk_level`, `status`). Blocks until
  answered `approved` or `rejected`.

## Enforcement status

Phase 1 stores and displays these rules; nothing enforces them yet because no
agent takes real actions. Enforcement lands with the orchestration loop in
Phase 4, at the point where a runtime is allowed to call a tool.
