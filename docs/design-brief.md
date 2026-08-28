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
