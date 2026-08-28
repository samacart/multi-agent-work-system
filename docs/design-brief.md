# Design brief — Mission Control dashboard

Paste this to Claude Design (or any design agent) together with repo access.

---

## What this system is

A local-first "mission control" for AI-assisted software work. You ingest
everything known about a **topic**, create a **project** from it, and specialist
agents (PM, Architect, Developer, QA, Reviewer, Security, Domain Expert, Release
Manager) carry it through the SDLC — surfacing decisions to a human **only when
judgement is actually needed**, and producing real deliverables.

The dashboard is how a single operator watches and steers that. One person,
local, often with several projects mid-flight.

## Your job

Redesign the frontend (`frontend/`). The backend, API, and data model are done
and should not change — design against what the API actually returns.

The existing UI is deliberately plain: React + Vite, no UI framework, no icons,
no charts, ~160 lines of hand-written CSS, dark-only, one flat page per tab. It
is a working skeleton that proves the data flows. It is not a designed product.

## The five things that are actually wrong

Fix these before making anything prettier.

1. **You cannot tell what needs you.** The whole premise is "surface decisions
   only when human judgment is needed" — but a pending approval blocking three
   agents looks identical to an idle system. Nothing pulls the eye. The human
   queue is buried behind a tab like any other view.

2. **The deliverables read like debug output.** Project briefs, architecture
   plans, test reports, release notes, PR descriptions are the *product* — and
   they are dumped as raw markdown inside a `<pre>` block. These are documents a
   person reads carefully and shares.

3. **The pipeline is invisible.** A planning run fires six agent passes in
   sequence; an SDLC run fires nine more. The UI shows a JSON blob per row.
   There is no sense of shape: which pass, in what order, feeding what, producing
   which artifact, and where it stalled.

4. **Blocked work does not explain itself.** When a run blocks, the reasons exist
   as a list of prose strings, shown as a bullet list. The task board just shows
   a `blocked` column with no causal link back to the gate that caused it.

5. **A new user is stranded.** Empty states say "No topics yet." Nothing conveys
   the path: ingest a topic → create a project → plan → run → answer the queue →
   deliver. Long operations (ingestion, planning, a full SDLC run) show only a
   text label changing to "running…".

## The mental model to design around

```
Topic ──ingest──> memories ──retrieve──> Project ──plan──> tasks + questions + gates
                     ▲                                              │
                     └────────── lessons written back ──── SDLC run ┘
```

Two things are worth making legible that the current UI hides entirely:

- **Memory has provenance.** Every memory is typed (`decision`, `risk`,
  `constraint`, `gotcha`, `lesson`, `open_question`, …), carries `confidence` and
  `importance` 0–1, and keeps the `source_quote` it came from. Search returns a
  per-result score *and its six weighted components* (similarity, importance,
  confidence, recency, source reliability, scope) — so a ranking can be
  explained, not guessed at. Right now that breakdown is a `title` tooltip.
- **The loop closes.** An SDLC run writes `lesson` and `gotcha` memories back to
  the topic. That is the thing that makes the second project cheaper than the
  first, and it is currently invisible.

## Views (current tabs — restructure freely)

| View | Shows | Weakness |
|---|---|---|
| Overview | phase, runtime/provider config, row counts | a wall of undifferentiated numbers |
| Agents | 8 seeded profiles, prompts, gated actions | static; never relates to live work |
| Topics | topics, sources + ingest status, memories, search | the densest, most useful screen; search results bury their scoring |
| Projects | brief, artifacts, plan/run/draft-PR buttons | artifacts are `<pre>` dumps |
| Task board | 7 status columns | cramped cards, dependencies as raw text |
| Agent runs | role, task, status, duration, JSON output | no pipeline shape |
| Human queue | pending approvals, open questions | the most important screen, styled like the least |

## Hard constraints

- **React 18 + TypeScript + Vite.** Currently zero runtime dependencies beyond
  `react`/`react-dom`. Adding a router, or a headless component/animation
  library, is fine — say what and why. Avoid anything needing a build step Vite
  doesn't already do.
- **API base URL** comes from `VITE_API_BASE_URL` (default `http://localhost:8000`).
  All calls go through `src/lib/api.ts`, which has typed models for every
  response — read it first; it is the contract.
- **Do not invent data.** Every endpoint is listed in `docs/api.md` and served at
  `/openapi.json` on a running stack. If a design needs a field the API does not
  return, flag it as a backend change rather than faking it.
- Runs in Docker: the `frontend` service bind-mounts `frontend/` and runs the
  Vite dev server on 5173. `npm run build` must stay clean (`tsc -b && vite build`).
- Long operations are synchronous HTTP by default and can take seconds; async
  mode exists for ingestion and SDLC runs (`?mode=async`), which flips a status
  to `ingesting`/`running` for polling.

## Where to push back on the original brief

The source brief (`docs/implementation-brief.md`) says *"Design should be
utilitarian, dense, and easy to scan"* and *"Do not overbuild the UI."* That was
right for a skeleton and it is still the right instinct for the operational
screens — this is a tool, not a marketing site.

But "utilitarian" is not the same as "undesigned", and two places earn more than
the rest: **the human queue** (the product's whole reason to exist) and **the
artifacts** (its actual output). Argue for spending the design budget there.

## Running it

```bash
cp .env.example .env && docker compose up --build
# dashboard  http://localhost:5173
# api docs   http://localhost:8000/docs
```

Everything runs offline on defaults — no API keys needed. To get realistic data
on screen, follow the "Ingesting a topic" and "Planning a project" sections of
the README; one file produces 8 typed memories, a project plans into 9 tasks
with acceptance criteria, 2 open questions, and 1 approval gate.

## What to hand back

1. The redesigned frontend, building and running against the live API.
2. A short rationale: what you changed about **information hierarchy** and why —
   specifically how a user now knows, within a second of loading, whether the
   system is waiting on them.
3. Anything you needed that the API does not expose, listed as a backend ask.

---

# Part two — what each view is for

The section above says what is wrong. This one says what each surface is
*meant to do*, what data it actually has, and where there is room to go further
than a restyle.

## Overview

**Meant to be:** the "is anything waiting on me?" screen. Right now it is the
opposite — a row of undifferentiated counters.

**Has:** `/system/summary` (configured runtime, embedding provider, memory
extractor, GitHub on/off, and row counts across all nine tables) and
`/health/ready` (per-dependency status, queue depth).

The counters are the least interesting thing on it. What matters is which
projects are blocked, on what, and for how long.

**Further:** make this a *triage* surface rather than a status page — the
system's own attention model. If nothing needs a human it should say so plainly
and get out of the way. Consider whether Overview and Human queue are really two
screens.

## Topics

**Meant to be:** the knowledge side. A topic holds sources (`pasted_text`,
`local_file`, `local_folder`, `github_repo`, `github_issue`, `github_pr`) that
ingest into chunks and typed memories.

**Has:** eleven memory types — `fact`, `decision`, `constraint`, `risk`,
`architecture`, `definition`, `person`, `system`, `open_question`, `lesson`,
`gotcha`. Every memory carries `confidence` and `importance` (0-1) and
`metadata_json.source_quote`, the exact sentence it came from. Search returns a
score **plus its six weighted components**: similarity 0.55, importance 0.15,
confidence 0.10, recency 0.10, source reliability 0.05, scope 0.05.

This is the densest, most genuinely useful screen and the closest to working.
Two things it wastes: the type taxonomy renders as a plain text column when it
is really the structure of what the system knows, and the score breakdown — the
answer to "why did this rank first?", a rare thing for a retrieval system to
expose at all — lives in a `title` tooltip.

**Further:** let someone *interrogate* the ranking, or tune the weights and
watch results reorder. Also surface that memories written back by a project run
are marked `metadata_json.origin === "sdlc_run"` — the system learning from its
own work, currently indistinguishable from ingested memory.

## Projects

**Meant to be:** where the deliverables live.

**Has:** `GET /projects/{id}` returns status, brief, topic, task counts by
status, run count, artifact count, open questions, pending approvals.
`GET /projects/{id}/artifacts` returns up to nine markdown documents:
`project_brief`, `architecture_plan`, `task_breakdown`, `test_report`,
`review_report`, `security_report`, `pr_description`, `release_notes`,
`final_summary`.

All of them currently dumped into `<pre>`. These are what a person reads
carefully, quotes from, and sends to someone else. Treat them as documents: real
typography, navigable structure, and something better than "select all, copy".

**Further:** artifacts have *lineage*. Each was produced by a specific agent run,
from a specific set of retrieved memories, at a specific point in the project. A
brief that can show which memory a given risk came from is a different product
from a brief that is a wall of text.

## Task board

**Meant to be:** the state of the work.

**Has:** seven columns — `backlog`, `ready`, `in_progress`, `blocked`, `review`,
`verified`, `done`. Cards carry `acceptance_criteria[]`, `evidence[]` (criterion
+ verdict of `met`/`not_met`/`unverified` + evidence text), and
`metadata_json.depends_on[]`. Moves are validated server-side; an illegal
transition returns 409 naming what is allowed from here.

Two structural facts the current board throws away: dependencies form a graph,
and `verified` is *earned by evidence*, not by clicking. A card sitting in
`review` with three `unverified` criteria is saying something specific, and right
now it looks like every other card.

**Further:** the board is one projection of a dependency graph — there may be a
better one. And the criterion/evidence pair is arguably the real unit of work,
not the task.

## Agent runs

**Meant to be:** the record of every agent invocation, successful or not.

**Has:** which role, which structured task, the runtime that executed it,
start/end timestamps, the validated output, and the error if it failed. A
planning run is six passes in fixed order (domain context -> brief ->
architecture -> task breakdown -> questions -> approval gates). An SDLC run is
one pass per task in dependency order, plus a release pass.

Currently a flat table of JSON blobs. This is a *pipeline* with a shape: passes
feed each other, produce artifacts, and stop somewhere specific.

**Further:** this is the closest thing to a debugger for the system's reasoning.
Failed runs carry the exact contract-validation error — a genuinely useful
diagnostic currently rendered as a stack of braces.

## Human queue

**Meant to be:** the product's entire reason to exist. Currently styled like the
least important tab.

**Has:** two distinct things, and conflating them is part of the problem.
**Approvals** are specific actions an agent wants to take
(`change_database_schema`, `modify_auth_billing_permissions_security_retention`,
`deploy`, `merge_pr`, `create_pull_request`, ...) carrying a `risk_level`; they
*block execution* until answered. **Questions** are open decisions needing
judgement; they do not block, they just stay unanswered.

An approval with three agents stalled behind it is urgent in a way a question is
not, and nothing conveys that.

**Further:** an approval should show its blast radius — which tasks are blocked,
what happens on approve versus reject. The *reason* already exists as a prose
string in the SDLC run notes ("Blocked 'Design the technical approach': architect
work needs the pending approval gate(s) answered first") but is never connected
back to the task it names. Linking those structurally is a **backend ask** —
flag it if you want it.

## Agents

**Meant to be:** who is doing the work and under what constraints.

**Has:** the eight seeded profiles with system prompts, allowed tools, and gated
actions. Currently a static reference page that never touches live work.

**Further:** it could be where you understand who did what and why they were
allowed to — profiles connected to their runs, their outputs, and the gates that
constrain them.

## Cross-cutting

- **Progress.** Ingestion, planning, and SDLC runs take seconds and currently
  show a label changing to "running...". Both ingestion and SDLC runs accept
  `?mode=async`, returning 202 and flipping status to `ingesting`/`running` for
  polling — real progress is available if you want it.
- **Failure states are informative and under-used.** Sources record why ingestion
  failed, planning returns 422 with the full result body, runs carry validation
  errors, and SDLC runs return a `notes[]` array explaining every block and skip.
- **Dark-only today.** Light mode and responsive behaviour are open questions.
  This is a single-operator local tool, so decide deliberately rather than by
  default.

## Two constraints on the ambitious ideas

1. **Do not invent data.** If a design needs something the API does not return,
   that is fine — list it as a backend ask rather than faking it.
2. **Restraint is a real design decision here.** Several of the ideas above would
   make the tool worse if applied everywhere. Two views that are genuinely
   excellent and five that are clean and honest beats seven that are all trying
   hard.
