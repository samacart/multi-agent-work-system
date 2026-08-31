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

## Enforcement

`check_gate()` in `backend/app/approvals/service.py` fails closed: anything not
on the auto-approved list is gated, including action types nobody classified -
a novel action is likelier to be risky than routine.

The SDLC loop (`backend/app/orchestration/sdlc.py`) applies this at role
granularity: while a project has a pending approval, the developer, architect,
and release roles do not run. Their tasks are marked `blocked` and anything
depending on them is skipped, with the reason recorded in the run notes and the
final summary. Answering the gate and re-running picks up where it stopped.

Below that, each role is constrained to the capabilities its profile grants
(`backend/app/agents/permissions.py`). Enforcement is by denial rather than by
allowance: `--allowedTools` means "pre-approved without prompting", not "only
these", so a role's permissions are expressed as the complement of what it was
granted, with a global deny list folded in last. A profile grants; it never
overrides.

What does not exist yet is a gate at the moment of a specific tool call - the
runtime cannot pause mid-pass and ask. Permissions are decided before the pass
starts and hold for its duration.

## Verification

Work is promoted by evidence, not by a pass completing:

- A successful agent pass moves a task to `review`.
- QA attaches evidence per acceptance criterion, routed back to whichever tasks
  own that criterion.
- A task reaches `verified` only when every one of its criteria has evidence
  with the verdict `met`, and no blocking review or security finding is open.
- Only then does it reach `done`, and only when every task is done does the
  project reach `delivered`.

With the mock runtime nothing can actually be executed, so evidence comes back
`unverified` and work stalls at `review`. That is the correct outcome, and the
run reports it rather than pretending otherwise.
