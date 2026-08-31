# Product roadmap

Working document for implementation planning. Companion to
[user-stories.md](user-stories.md), which holds the full inventory; this file
says what to build, in what order, and why.

Grounded in the code as of `ae0bfcf`. Where a story's label in the inventory no
longer matches the code, the correction is recorded in
[Label corrections](#label-corrections) below.

## Where the system actually is

The engine works. Topics ingest into typed memory with explainable retrieval;
projects plan through gated stages with independent reviewer briefings; the SDLC
loop runs dependency waves concurrently, promotes only on evidence, and writes
lessons back; approvals fail closed; four runtime adapters are interchangeable
behind one contract; review roles read the real diff; and role permissions are
now enforced rather than merely recorded.

What is thin is everything between that engine and the person operating it. The
system knows a great deal that it does not say. A pending approval blocking five
agents looks identical to an idle system. A run that timed out looks like a run
still working. Acceptance criteria carry verdicts and evidence in the database
and render nowhere. That is the shape of the next three months of work: not more
agent capability, but making the capability legible and steerable.

One structural gap sits underneath several stories: **the workspace is global
configuration**. `CLAUDE_CODE_CWD` is read from settings, so pointing agents at
a different repository means editing `.env` and restarting the backend, and two
projects can never target two repositories. `Project.workspace_path` exists as a
column (`4208dea`) and nothing reads it. Until that is closed, multi-project use
is not really possible, which caps the value of everything else.

## Epics

Renamed and regrouped from the inventory's eleven themes where the grouping did
not survive contact with the code. The mapping is noted per epic.

### E1 — Workspace isolation and execution safety
*Inventory themes 7 (Workspaces, Execution, Safety), part of 10.*

**Rationale.** Agents now write real code with real shell access. Everything
that makes that safe or unsafe lives here, and the global-workspace constraint
blocks routine multi-project use. This is the epic that turns a single-project
demo into a tool.

**Builds on.** `Project.workspace_path` (declared, unused);
`app/agents/permissions.py` (role capabilities, enforced by denial);
`app/orchestration/workspace.py` (`read_workspace_diff`, already read-only and
non-mutating); `claude_code_disallowed_tools` global list;
`GET /projects/{id}/branch` and `app/github/delivery.py:branch_name`.

**Stories.** 45, 46, 47, 49, 50, 51, 52, and the runtime half of 48.

### E2 — The attention model
*Inventory themes 1 (Operator Triage) and 10 (Operations, Health).*

**Rationale.** The product's stated purpose is to surface decisions only when
human judgement is needed. It currently surfaces them into a tab that looks the
same whether or not anything is waiting. Without an attention model the operator
must poll the system, which inverts the whole premise.

**Builds on.** `GET /system/summary` (per-table counts);
`GET /health/ready` (per-dependency status, queue depth);
`GET /projects/{id}` (task counts by status, `open_questions`,
`pending_approvals`); `AgentRun.status` including `failed` and stuck `running`;
`Source.status` including `failed`.

**Stories.** 1, 2, 3, 4, 5, 6, 65, 66, 68.

### E3 — The human queue as a decision surface
*Inventory theme 2.*

**Rationale.** This is the product's core interaction and the most nearly
finished. Approvals already carry the artifact, an independent reviewer briefing
with a recommendation, concerns, contradictions with earlier stages, and blast
radius. What is missing is the ability to respond with anything richer than
yes/no, and any record of how judgement accumulated.

**Builds on.** `ApprovalRequest.metadata_json.briefing` (`ApprovalBriefing`
contract: summary, recommendation, rationale, concerns,
`contradicts_earlier_stage`); `Decision.metadata_json` (options,
recommendation); `gather_context` feeding answered decisions to every later pass
as `decisions_made_by_the_human`; `respond_to_approval`; the `HumanQueue`
component, which already renders briefings and blast radius.

**Stories.** 7, 8, 9, 10, 11, 12, 13.

### E4 — Evidence-first verification
*Inventory theme 5.*

**Rationale.** The loop already refuses to promote work without evidence — the
single most trust-building behaviour in the system — and that refusal is
invisible. `Task.evidence` carries a verdict and evidence string per criterion
and the board renders neither, so "12 tasks awaiting verification evidence"
appears only in run notes.

**Builds on.** `Task.acceptance_criteria` and `Task.evidence`
(criterion/verdict/evidence, verdicts `met`/`not_met`/`unverified`);
`_attach_evidence` routing QA output back to whichever tasks own each criterion;
`_promote_verified_tasks`; `ALLOWED_TRANSITIONS` and `path_to`;
`PATCH /tasks/{id}` returning 409 with the legal moves; `Task.metadata_json`
carrying `depends_on` and `dropped_from_plan`.

**Stories.** 31, 32, 33, 34, 35, 36, 37.

### E5 — Run observability and recovery
*Inventory theme 6.*

**Rationale.** Long runs are the system's main failure surface and its least
inspectable. A 45-minute run reports nothing until it finishes; a single timeout
took out six dependent tasks in a real run; recovery means re-running everything.

**Builds on.** `AgentRun` (input with task/instruction/runtime, validated
output, error, `started_at`/`completed_at`); the retry loop in
`_run_task_isolated`; `SdlcResult.notes`; `order_waves`; the roles filter on
`POST /projects/{id}/run`; the Redis job queue.

**Stories.** 38, 39, 40, 41, 42, 43, 44, 64.

### E6 — Memory as a curated asset
*Inventory theme 3.*

**Rationale.** Retrieval quality is the ceiling on planning quality, and the
system already computes far more about a memory than it shows. Real ingestion of
a technical corpus surfaced the risk directly: a design specification's central
sentence produced no memory at all, and nothing told the operator.

**Builds on.** Eleven memory types with `confidence`/`importance`;
`metadata_json` carrying `source_quote`, `document`, and `origin`
(`sdlc_run` marks lessons the system taught itself); `POST /memory/search`
returning a score plus its six weighted components; the `_cap_evenly`
round-robin and its `notes`.

**Stories.** 14, 15, 16, 17, 18, 19, 20, 21, 22.

### E7 — Planning transparency
*Inventory theme 4.*

**Rationale.** Stage gating works, and the briefing that reviews each stage
caught real drift. What is missing is a view of the plan as a sequence: what was
approved, what changed on replan, and why.

**Builds on.** `STAGES`, `STAGE_GATES`, `STAGE_REVIEWERS` (each stage reviewed
by a role that did not write it); approved artifacts carried into resumed stages
as `approved_*`; `_sync_tasks` create/update/remove counts and notes;
`?gates=false` and `?roles=`.

**Stories.** 23, 24, 25, 26, 27, 28, 29, 30.

### E8 — Artifacts as deliverables
*Inventory theme 8.*

**Rationale.** Artifacts are the product's output and now render as markdown,
but they have no lineage and no versions, so a brief cannot be compared before
and after a replan.

**Builds on.** Nine artifact types; `upsert_artifact` (replaces in place — which
is exactly why versions are missing); `Markdown` component; `pr_description` and
`app/github/delivery.py`.

**Stories.** 53, 54, 55, 56, 57, 58.

### E9 — Agent governance
*Inventory theme 9.*

**Rationale.** Roles are now genuinely differentiated — enforced permissions and
substantive personas — which makes them worth operating rather than only
configuring.

**Builds on.** `DEFAULT_AGENT_PROFILES` seeded idempotently on boot;
`allowed_tools_json` enforced via `permissions.py`; `AgentRun.agent_profile_id`;
`available_runtimes()`.

**Stories.** 59, 60, 61, 62, 63.

### E10 — Reflective capabilities
*Inventory theme 11.*

**Rationale.** Mostly premature — but two are not, and see
[Strategic bets worth pulling forward](#strategic-bets-worth-pulling-forward).

**Stories.** 71–80.

## Sequence

Near-term order, biased toward operator trust, observability, safety and
recovery, and toward thin vertical slices.

| # | Slice | Epic | Why here | Status |
|---|---|---|---|---|
| 1 | Per-project workspace, validated | E1 | Unblocks multi-project use; every later slice is more valuable with it | **shipped** `76c48f9` |
| 2 | Attention model on the overview | E2 | The product's premise, currently unmet | **shipped** `a1133a0` |
| 3 | Evidence-first task board | E4 | Makes the system's best behaviour visible | **shipped** `b190768` |
| 4 | Run pipeline and live progress | E5 | Long runs are the main failure surface | next |
| 5 | Single-pass rerun and retry history | E5 | Recovery without re-running everything | |
| 6 | Approve-with-conditions and send-back | E3 | Richer judgement than yes/no |
| 7 | Memory provenance and curation states | E6 | Retrieval quality caps planning quality |
| 8 | Artifact lineage and versions | E8 | Enables replan diffing |
| 9 | Job records persisted beyond Redis | E2 | Worker liveness shipped in slice 2; job history has not |
| 10 | Preflight risk scan before writes | E1 | Needed before autonomy widens |

### Strategic bets worth pulling forward

Two are not "later", and treating them as such would be a mistake.

**#47, per-project branch/worktree (E1).** Already how the system is used in
practice — worktrees have been created by hand for every real run, and the
manual step is the only thing keeping agent changes off a working tree. Fold it
into slice 1.

**#51, checkpoints before each mutating pass (E1).** The system produced ~15,000
lines across two unattended runs. Reverting a single bad pass currently means
reading a 65-file diff. A commit-per-pass checkpoint is cheap now that
`vcs.commit` is a real capability, and it is the difference between recoverable
and not. Schedule immediately after slice 5.

**#48, tool-level gates at runtime**, is now partly shipped: capabilities are
enforced per role before a pass begins. The remaining half — pausing mid-pass to
ask — needs a runtime that can suspend, and should stay a bet.

---

# The first three slices

## Slice 1 — Per-project workspace, validated

### Problem
The repository agents work in is global configuration. Pointing them elsewhere
means editing `.env` and restarting the backend; two projects cannot target two
repositories. Every real run so far has needed a manual worktree and a restart.

### Stories
45 (own workspace path), 46 (validate before running), 47 (branch/worktree,
pulled forward), 52 (diff truncation visible).

### Backend
- Read `Project.workspace_path` with the global `claude_code_cwd` as fallback.
  Thread it to the two places that use a workspace: `read_workspace_diff` in
  `run_project`, and the `cwd` a `ClaudeCodeRuntime` invocation runs in. The
  runtime currently takes `cwd` at construction — move it per call, exactly as
  `tool_flags` moved in `a4e9162`.
- New `app/orchestration/workspace.py::validate_workspace(path)` returning a
  structured verdict: exists, is a git repo, current branch, dirty file count,
  whether the branch looks agent-owned (`agents/` prefix). Reuse the existing
  `_git` helper; do not add a second subprocess pattern.
- `POST /projects/{id}/workspace` to set and validate in one call;
  `GET /projects/{id}/workspace` for status.
- Refuse to start a run when the workspace is invalid, with the reason in
  `SdlcResult.notes` — the same shape as the existing "no diff to read" note.
- Extend `WorkspaceDiff` with `omitted_files: list[str]` so truncation names
  what the reviewer did not see, rather than only that it happened.

### Frontend
- Workspace field on the project create and detail views, with validation state
  inline (branch, dirty count, warning when it is not an `agents/` branch).
- Show the resolved workspace on the project detail beside the planned branch.
- Truncation notice on review artifacts listing omitted files.

### Data model
`Project.workspace_path` and migration `0005_project_workspace` **already exist
and are applied** (`4208dea`) — do not recreate them. No new migration needed
unless worktree bookkeeping is persisted, which slice 1 should avoid.

### Tests
- `validate_workspace` against a tmp git repo: clean, dirty, non-repo, missing.
- Per-project override beats the global setting; global remains the fallback.
- A run against an invalid workspace refuses with a note rather than failing.
- Two projects with different workspaces produce different diffs in one process
  — the property that proves the global constraint is gone.
- `WorkspaceDiff.omitted_files` is populated when the budget truncates.

### Acceptance criteria
- Two projects targeting two repositories run in one server process, no restart.
- A run against a missing or non-git workspace is refused with a clear reason.
- The project detail shows resolved workspace, branch and dirty state.
- Review artifacts name omitted files when the diff was truncated.

### Risks
- **Path traversal.** `workspace_path` is operator-supplied and becomes a
  process `cwd`. Decide deliberately whether to constrain it to
  `ALLOWED_SOURCE_ROOTS` (safer, but the ingestion roots are a different concept
  and worktrees live outside them) or to accept it as trusted local operator
  input. Reuse `resolve_within_roots` in `app/ingestion/extract.py` if
  constraining. **Open question below.**
- Per-call `cwd` touches the runtime constructor's contract; keep the
  constructor argument as an override, as `tool_flags` did.

### Files
`app/db/models.py` (column exists), `app/orchestration/workspace.py`,
`app/orchestration/sdlc.py`, `app/agents/runtime/claude_code.py`,
`app/api/routes/projects.py`, `app/api/schemas.py`,
`frontend/src/components/Projects.tsx`, `frontend/src/lib/api.ts`,
`tests/test_workspace.py`, `tests/test_sdlc.py`.

## Slice 2 — Attention model on the overview

### Problem
The overview is a row of counters. A pending approval blocking five agents looks
the same as an idle system, so the operator must poll every tab. The product's
stated purpose is the opposite.

### Stories
1 (most urgent thing), 2 (one ranked queue), 3 (blast radius — extend the queue
work already in `HumanQueue`), 4 (deliberate quiet state), 5 (stale-work
indicator), 6 (project cards showing next action and blocker).

### Backend
- `GET /attention` returning a ranked list across every project. Item shape:
  `kind` (`approval` | `question` | `blocked_task` | `failed_run` |
  `failed_source` | `stale_run` | `degraded_dependency`), `project_id`,
  `title`, `why`, `blast_radius` (count of tasks held), `age_seconds`,
  `severity`, and a deep link target.
- Ranking in one place, `app/orchestration/attention.py`, as a pure scored
  function over already-loaded rows so it is testable without a database.
  Suggested order: degraded dependency → blocked task with a resolvable cause →
  pending approval by blast radius → failed run → stale run → open question.
- Staleness: a run `running` with no completion for longer than
  `stale_run_seconds` (new setting, default 1800 — the Claude Code timeout).
  This is the case that produced a run stuck in `running` after a restart.
- Extend `/health/ready` with worker liveness and oldest queued job age
  (story 65). Worker liveness needs a heartbeat key in Redis written by the
  worker loop; small and self-contained.

### Frontend
- Overview becomes triage: the ranked queue first, counters demoted.
- An explicit, designed empty state — "nothing needs you" as a statement, not an
  absence (story 4).
- Project cards showing next action, current blocker, last activity.
- Reuse the existing `usePolled` hook; do not add a second polling mechanism.

### Data model
None. Everything is derivable. Add settings `stale_run_seconds` and
`worker_heartbeat_seconds`.

### Tests
- Ranking is a pure function: a blocked task with a resolvable cause outranks an
  open question; blast radius orders approvals.
- A run past the stale threshold appears; one inside it does not.
- Empty input produces the deliberate quiet state, not an error.
- Worker heartbeat absent → readiness reports the worker down.

### Acceptance criteria
- The overview answers "does anything need me?" without opening another tab.
- Every item states what it blocks and what unblocks it.
- A worker that has died is visible within one heartbeat interval.
- With nothing outstanding, the screen says so plainly.

### Risks
- Ranking is a product judgement encoded as a constant. Keep the weights in one
  named place and show why an item ranked where it did, mirroring how memory
  search exposes its score components.
- `/attention` scans several tables; keep it to counts and indexed columns, and
  cap the returned list.

### Files
`app/orchestration/attention.py` (new), `app/api/routes/system.py`,
`app/api/routes/health.py`, `app/worker/main.py` (heartbeat),
`app/config.py`, `frontend/src/components/SystemOverview.tsx`,
`frontend/src/lib/api.ts`, `tests/test_attention.py` (new).

## Slice 3 — Evidence-first task board

### Problem
The loop promotes work only on evidence, and none of that is visible. Criteria
render as a flat list with no verdict; `Task.evidence` renders nowhere; a task
sitting in `review` with three unverified criteria looks like any other card;
"blocked" names no cause.

### Stories
31 (dependency waves), 32 (blocked links to its cause), 33 (criteria as
first-class checklist), 34 (manual evidence), 35 (unmet criteria grouped
project-wide), 36 (illegal transitions prevented in the UI), 37 (dropped-but-
started tasks highlighted).

### Backend
- `GET /projects/{id}/criteria` — every criterion across the project with its
  task, verdict, evidence and source run. Enables story 35 without the frontend
  reassembling it.
- `PATCH /tasks/{id}/evidence` to attach or amend one criterion's verdict and
  evidence, attributed to `human` rather than a run. Reuse the merge logic in
  `_attach_evidence`; extract it so both callers share one path.
- `GET /tasks/{id}/blockers` returning the structured cause: pending approval
  ids, the failed run id, unsatisfied dependency titles, or unmet criteria.
  The prose already exists in `SdlcResult.notes`; this makes it addressable.
- Expose `ALLOWED_TRANSITIONS` via `GET /tasks/transitions` so the UI can
  disable illegal moves rather than discovering them through a 409.
- Surface `Task.metadata_json.dropped_from_plan` in `TaskOut` (story 37).

### Frontend
- Cards show criteria with verdict icons and evidence on expand.
- Status control offers only legal transitions, from the API.
- Blocked cards link to their cause.
- A wave indicator from `metadata_json.depends_on` — group columns by wave, or
  badge each card with its wave number.
- A project-wide "needs verification" view grouping unmet and unverified
  criteria.
- Highlight tasks tagged `dropped_from_plan`.

### Data model
None. `Task.acceptance_criteria`, `Task.evidence` and `Task.metadata_json` are
sufficient.

### Tests
- Manual evidence promotes a task exactly as agent evidence does — the existing
  `_promote_verified_tasks` path, with no second promotion rule.
- Human-attributed evidence is distinguishable from run-attributed evidence.
- `GET /tasks/{id}/blockers` returns the approval id for a gate-blocked task and
  the dependency titles for a skipped one.
- The transitions endpoint matches `ALLOWED_TRANSITIONS` exactly, so the UI
  cannot drift from the state machine.

### Acceptance criteria
- Every criterion shows verdict and evidence on the board.
- A blocked task links to what is blocking it.
- Illegal transitions are not offered.
- A human can unblock a task the automated agent could not verify, and the
  attribution says so.

### Risks
- Manual evidence is a trust boundary: a human marking `met` bypasses the
  system's best property. Attribute it explicitly and show it differently from
  agent evidence — never let the two look alike.
- Wave visualisation needs a real dependency graph; `order_waves` already
  computes it, so expose that rather than recomputing in the client.

### Files
`app/api/routes/projects.py`, `app/api/schemas.py`,
`app/orchestration/sdlc.py` (extract evidence merge, expose waves),
`app/projects/tasks.py`, `frontend/src/components/TaskBoard.tsx`,
`frontend/src/lib/api.ts`, `tests/test_api_projects.py`, `tests/test_sdlc.py`.

## Label corrections

Applied to [user-stories.md](user-stories.md). The inventory was surveyed on
2026-08-31, before `4208dea`, `a4e9162` and `ae0bfcf`.

| Story | Was | Now | Reason |
|---|---|---|---|
| 45 | Build next | Shipped foundation + Build next | `Project.workspace_path` and its migration exist and are applied; nothing reads the column |
| 48 | Strategic bet | Shipped foundation + Strategic bet | Role-level capabilities are enforced by `permissions.py`, verified against the real CLI; mid-pass gating remains a bet |
| 7 | Shipped foundation + Needs productization | Shipped | The approval panel already carries artifact, briefing, recommendation, concerns and blast radius |
| 27 | Build next | Shipped foundation + Needs productization | `ApprovalBriefing.contradicts_earlier_stage` exists and caught real drift; it is not yet shown prominently |
| 37 | Shipped foundation + Needs productization | Shipped foundation + Build next | Backend tags `dropped_from_plan` and notes it; no UI surface at all |
| 60 | Strategic bet | Strategic bet *(unchanged, note added)* | Now higher value: personas are substantive enough to be worth editing |

No story was removed, and none of the strategic bets were downgraded to make the
near-term list look tidier.

## Decisions taken

Answered by the product owner on 2026-09-01 and now implemented or scheduled.

1. **Workspace trust boundary** — constrained. A path supplied through the API
   must resolve inside `ALLOWED_WORKSPACE_ROOTS`, a new setting separate from
   the ingestion roots. The global `CLAUDE_CODE_CWD` fallback is deliberately
   exempt: it is set by whoever runs the server, and holding it to a list it
   predates would break every existing deployment. Shipped in slice 1.
2. **Manual evidence** — allowed, attributed, auditable. Human evidence goes
   through the same merge and promotion rule as agent evidence, carries
   `attributed_to`, renders differently, and `met` without evidence is refused.
   Shipped in slice 3.
3. **Checkpoint granularity** — per mutating pass. Scheduled after slice 5.
4. **Attention ranking** — approvals outrank individual blocked tasks; blast
   radius dominates within a kind. Shipped in slice 2.
5. **Multi-project concurrency** — not yet. Persisted job records and project
   locks come first; that is now slice 9.

## Open questions for the product owner

1. **Stale-run recovery.** Slice 2 surfaces a run stuck in `running` after a
   worker died, but nothing resolves it — the row stays `running` forever and
   its task stays `in_progress`. Should the worker mark its in-flight runs
   interrupted on startup, or should the operator dismiss them? This is the
   remaining half of the failure that looked like progress for an hour.
2. **Verification batching.** `GET /projects/{id}/criteria` exists and nothing
   consumes it yet — the project-wide "needs verification" view (story 35) was
   left out to keep slice 3 thin. Worth a screen of its own, or a filter on the
   board?
3. **Blast radius precision.** An approval's blast radius currently counts every
   unfinished task owned by a gated role, because gates block roles rather than
   tasks. That is accurate to the mechanism but coarse. Worth making gates
   task-specific, or is role granularity the right model?
