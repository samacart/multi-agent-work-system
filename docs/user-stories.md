# Multi-Agent Work System User Stories

Generated after a codebase survey on 2026-08-31. Labels re-audited against the
code on 2026-08-31 after commits `4208dea`, `a4e9162` and `ae0bfcf`; the six
corrections are listed in [product-roadmap.md](product-roadmap.md#label-corrections).
Sequencing and slice definitions live there — this file stays the inventory.

## What The System Is Today

The system is a local-first mission control app for AI-assisted software and
knowledge work. It can ingest topic sources into typed memories, create projects
from those memories, plan projects through gated stages, run specialist agent
passes through an SDLC loop, store artifacts, route decisions and approvals to a
human queue, read workspace diffs for review roles, draft PR descriptions, and
write lessons back into topic memory.

The strongest current foundations are:

- Typed, provenance-aware memory with explainable retrieval scoring.
- Structured agent output contracts with persisted failed runs.
- Stage-gated planning with independent reviewer briefings.
- Idempotent replanning that updates tasks, questions, approvals, and artifacts.
- Approval gates that fail closed and block risky roles.
- Evidence-based task promotion rather than "agent said it is done".
- Concurrent dependency waves for independent SDLC tasks.
- Workspace diff reading for QA, code review, security review, and release.
- Local/offline defaults with optional LLM, LangGraph, Claude Code, OpenAI embeddings, Ollama embeddings, and GitHub integration.

The main product gaps are not "add agents" or "add a dashboard" anymore. They
are: explain what is happening, make the system steerable, isolate workspaces per
project, make evidence and provenance first-class, and turn the human queue into
the operator's control tower.

## Operating Principles For The Next Backlog

- The operator should know within one second whether the system needs them.
- Every blocked state should answer: what is blocked, why, by whom, and what
  unblocks it.
- Every recommendation should show the evidence and the confidence behind it.
- Every long run should be inspectable while it is running, not only after it
  finishes.
- Real coding agents need workspace isolation, tool-level permissions, and
  recoverable checkpoints before they need more autonomy.
- The memory system should become a living project asset, not a hidden retrieval
  cache.

## User Stories

Label guide:

- **Shipped**: works end to end today.
- **Needs productization**: the capability or data exists, but needs better UX,
  visibility, controls, or polish.
- **Build next**: clear implementation gap with strong near-term value.
- **Strategic bet**: larger capability that may define the system and deserves
  design or architecture thought.
- **Research spike**: promising direction where the right implementation shape
  needs investigation.

Combined labels are intentional. For example, **Shipped foundation + Needs
productization** means the important backend behavior exists, but the operator
experience still needs work.

### 1. Operator Triage And Attention

1. **Needs productization**. As a solo operator, I want the overview to show the most urgent thing waiting
   for me, so that I can open the app and immediately know whether to act.

2. **Build next**. As a solo operator, I want approvals, open questions, blocked tasks, failed
   runs, stale ingestion jobs, and degraded dependencies ranked in one attention
   queue, so that I do not have to inspect every tab.

3. **Needs productization**. As a solo operator, I want each queue item to show its blast radius, so that I
   know whether a low-risk approval is blocking one task or the whole project.

4. **Needs productization**. As a solo operator, I want "nothing needs you" to be a deliberate state, so
   that a quiet dashboard feels trustworthy rather than empty.

5. **Build next**. As a solo operator, I want a stale-work indicator for runs or ingestions that
   have not changed for a configurable period, so that background failures do
   not hide behind "running".

6. **Needs productization**. As a solo operator, I want project cards to show next action, blocker, and
   last activity, so that switching projects feels like triage rather than
   archaeology.

### 2. Human Queue As A Decision Product

7. **Shipped**. As an approver, I want every approval to include the artifact, reviewer
   briefing, recommendation, concerns, and blocked tasks in one panel, so that I
   can decide without hunting for context.

8. **Build next**. As an approver, I want to approve with conditions, so that the system records
   "approved if X" as context for later agents instead of reducing nuanced
   judgement to yes/no.

9. **Build next**. As an approver, I want a "send back for revision" response that creates a
   targeted planning or task follow-up, so that rejection is constructive.

10. **Build next**. As an approver, I want the system to explain what will happen next after I
    approve or reject, so that I understand the operational consequence of the
    decision.

11. **Shipped foundation + Needs productization**. As an approver, I want decisions to support offered options, tradeoffs, and
    a recommended default, so that answering a question is easier than doing the
    agent's thinking myself.

12. **Shipped foundation + Needs productization**. As an approver, I want answered decisions to be visible inside future
    planning context, so that the system proves it acted on my judgement.

13. **Build next**. As an approver, I want a decision history timeline, so that I can see how
    scope changed over time and why.

### 3. Memory And Knowledge Work

14. **Shipped foundation + Needs productization**. As a project owner, I want memory search results to show their score
    breakdown visually, so that I can understand why a memory ranked highly.

15. **Shipped foundation + Needs productization**. As a project owner, I want to filter memory by origin, such as ingested
    source versus SDLC learning, so that I can separate external knowledge from
    lessons generated by the system.

16. **Shipped foundation + Needs productization**. As a project owner, I want each memory to show its source quote and source
    document, so that I can audit claims before trusting them in a plan.

17. **Build next**. As a project owner, I want to mark a memory as stale, disputed, promoted, or
    canonical, so that bad or outdated knowledge does not keep shaping plans.

18. **Build next**. As a project owner, I want memory diffs after re-ingestion, so that I can see
    what the system learned, forgot, or deduplicated.

19. **Research spike**. As a project owner, I want to tune retrieval weights per search or topic, so
    that recent decisions, high-confidence facts, or project-specific lessons
    can dominate when appropriate.

20. **Build next**. As a project owner, I want memory coverage analysis for a project goal, so
    that the system can say "you have architecture context but no security
    history" before planning.

21. **Strategic bet**. As a project owner, I want the system to propose missing sources, so that a
    thin topic can be improved before agents build on it.

22. **Needs productization**. As a project owner, I want topic memory to cluster into decisions, risks,
    systems, people, gotchas, and open questions, so that a topic becomes a
    readable knowledge map rather than a table.

### 4. Planning And Replanning

23. **Shipped foundation + Needs productization**. As a project owner, I want planning to show the current gated stage, prior
    approved stages, and the next stage to run, so that staged planning feels
    like an intentional workflow.

24. **Build next**. As a project owner, I want to compare the old and new brief, architecture,
    and task breakdown after replanning, so that I can review scope drift before
    approving it.

25. **Research spike**. As a project owner, I want the system to classify replan changes as human
    answer, memory change, agent refinement, or manual task edit, so that I know
    why the plan moved.

26. **Research spike**. As a project owner, I want a plan confidence score with supporting reasons,
    so that I know whether to trust the current task breakdown.

27. **Shipped foundation + Needs productization**. As a project owner, I want the planner to call out contradictions between
    approved stages, human answers, and topic memory, so that drift is caught
    before implementation.

28. **Strategic bet**. As a project owner, I want to lock approved scope elements, so that later
    replanning can sharpen wording without silently changing commitments.

29. **Shipped foundation + Needs productization**. As a project owner, I want a "plan only", "review only", and "full gated
    planning" mode, so that I can choose the amount of process for the risk of
    the project.

30. **Research spike**. As a project owner, I want planning to propose tasks at different grains, so
    that I can choose between a small solo-agent change and a multi-agent SDLC
    run.

### 5. Task Board, Dependencies, And Evidence

31. **Build next**. As an operator, I want the task board to visualize dependency waves, so that
    I understand what can run in parallel and what is waiting.

32. **Build next**. As an operator, I want blocked tasks to link back to their specific approval,
    failed run, dependency, or missing evidence, so that "blocked" is actionable.

33. **Shipped foundation + Needs productization**. As an operator, I want acceptance criteria to be tracked as first-class
    checklist items with evidence and verdicts, so that verification is visible
    at the level that actually controls promotion.

34. **Build next**. As a QA reviewer, I want to attach manual evidence to a criterion, so that I
    can unblock a task when the automated agent cannot verify it.

35. **Build next**. As a QA reviewer, I want unmet and unverified criteria grouped across the
    whole project, so that verification work can be batched intelligently.

36. **Shipped foundation + Needs productization**. As an operator, I want illegal status transitions to be prevented in the UI,
    so that I do not learn the state machine only after a 409 response.

37. **Shipped foundation + Build next**. As an operator, I want started tasks dropped by replanning to be highlighted,
    so that abandoned work does not quietly linger.

### 6. Agent Runs And Runtime Observability

38. **Shipped foundation + Needs productization**. As an operator, I want agent runs shown as a pipeline rather than a flat
    table, so that I can see which pass produced which artifact and where the
    workflow stopped.

39. **Shipped foundation + Needs productization**. As an operator, I want each run to show input context summaries, cited memory
    ids, runtime, duration, retries, output contract, and validation errors, so
    that failures are diagnosable.

40. **Build next**. As an operator, I want live progress for async jobs, so that a long SDLC run
    does not disappear into Redis with only polling side effects.

41. **Build next**. As an operator, I want retry history to be explicit, so that transient
    provider failures are distinguishable from persistent task failures.

42. **Build next**. As an operator, I want to rerun a single failed pass with the same context,
    so that recovery does not require restarting an entire SDLC loop.

43. **Shipped foundation + Needs productization**. As an operator, I want to rerun only review roles against the current diff,
    so that I can recheck code without allowing more implementation changes.

44. **Build next**. As an operator, I want model-backed run costs, token counts, and latency
    summaries, so that I can tune runtime choice by project risk and budget.

### 7. Workspaces, Execution, And Safety

45. **Shipped foundation + Build next**. As a project owner, I want each project to have its own workspace path, so
    that multiple projects can target different repositories without server
    restarts.

46. **Build next**. As a project owner, I want the system to validate that a workspace exists, is
    a git repo, and has a clean or intentionally dirty state before agents run,
    so that execution starts from a known baseline.

47. **Strategic bet**. As a project owner, I want the system to create or select a per-project
    branch/worktree, so that agent changes are isolated from my active working
    tree.

48. **Shipped foundation + Strategic bet**. As a security-minded operator, I want tool-level approval gates at runtime,
    so that a coding agent can read broadly but must ask before writing,
    installing dependencies, deleting files, or touching protected surfaces.

49. **Build next**. As a security-minded operator, I want a preflight risk scan before enabling
    Claude Code writes, so that the system confirms branch, diff, gates, and
    rollback before mutation.

50. **Build next**. As an operator, I want repository-specific command allowlists, so that test
    and build commands can run safely without giving every project the same
    shell power.

51. **Strategic bet**. As an operator, I want checkpoints before each mutating pass, so that a bad
    agent change can be inspected and reverted without losing the project state.

52. **Build next**. As an operator, I want workspace diff truncation to be visible with a list of
    omitted files, so that reviewers know when they did not see the whole change.

### 8. Artifacts And Delivery

53. **Shipped foundation + Needs productization**. As a stakeholder, I want artifacts to render as shareable documents with
    headings, tables of contents, status, authoring run, and generated time, so
    that they feel like deliverables rather than debug output.

54. **Build next**. As a stakeholder, I want artifact lineage, so that every brief, report, or
    PR description links to the run, memories, tasks, and decisions that shaped
    it.

55. **Build next**. As a stakeholder, I want artifact versions, so that I can compare the brief
    before and after replanning.

56. **Shipped foundation + Needs productization**. As a release owner, I want final summaries to distinguish completed work,
    blocked work, unverified work, accepted risk, and follow-ups, so that
    partial delivery is honest.

57. **Shipped foundation + Build next**. As a release owner, I want PR creation to explain which gate, branch, base,
    repo, and artifact will be used, so that opening a PR is deliberate.

58. **Build next**. As a release owner, I want GitHub issue and PR sources to stay linked to the
    project delivery artifacts, so that reviewers can trace the work back to its
    origin.

### 9. Agent Governance And System Design

59. **Build next**. As an operator, I want agent profiles to show live usage, recent failures,
    average duration, and artifacts produced, so that profiles are operational
    actors rather than static prompts.

60. **Strategic bet**. As an operator, I want to edit or version agent prompts through the UI, so
    that improving a role does not require code changes.

61. **Strategic bet**. As an operator, I want project-specific agent overrides, so that a risky
    project can use stricter reviewer prompts without changing global defaults.

62. **Research spike**. As an operator, I want the system to recommend the runtime per task, so that
    mock, LLM, LangGraph, and Claude Code are used where they make sense.

63. **Shipped foundation + Needs productization**. As an operator, I want a simulation mode that runs the whole plan with mock
    agents first, so that gates, task graph, and artifact structure can be
    inspected before spending model time or allowing writes.

64. **Build next**. As an operator, I want failed contract outputs saved with sanitized raw
    snippets, so that prompt/schema issues can be improved without leaking
    sensitive provider payloads.

### 10. Operations, Health, And Administration

65. **Build next**. As an operator, I want the readiness screen to include worker liveness, queue
    depth, oldest job age, and last job error, so that async mode is observable.

66. **Build next**. As an operator, I want job records persisted beyond the Redis list, so that
    completed, failed, and abandoned jobs can be audited.

67. **Shipped foundation + Needs productization**. As an operator, I want a setup checklist for GitHub, embeddings, model keys,
    Claude Code, and allowed source roots, so that local-first defaults can be
    upgraded deliberately.

68. **Build next**. As an operator, I want config drift warnings when docs say one thing and
    runtime says another, so that stale docs do not become product confusion.

69. **Build next**. As an operator, I want backup and restore guidance for Postgres and Redis
    volumes, so that topic memory and project history are not fragile local
    state.

70. **Build next**. As an operator, I want basic auth or a local auth gate before binding beyond
    localhost, so that a convenient dashboard does not become an exposed control
    surface.

### 11. Outside-The-Box Bets

71. **Strategic bet**. As a project owner, I want a "why this plan" explainer that lets me ask why a
    task exists, why it depends on another task, and which memories caused it, so
    that agent planning becomes inspectable.

72. **Strategic bet**. As a project owner, I want a "counterfactual plan" option, so that I can ask
    what would change if we accepted a risk, rejected a dependency, or delayed a
    migration.

73. **Strategic bet**. As a project owner, I want the system to detect repeated patterns across
    projects, so that recurring blockers become suggested playbooks or repo
    refactors.

74. **Research spike**. As a project owner, I want "unknown unknowns" prompts generated from thin or
    contradictory memory areas, so that the system asks better questions before
    implementation.

75. **Strategic bet**. As an operator, I want a project replay mode, so that I can scrub through
    memory retrieval, planning, approvals, agent runs, verification, and
    delivery as a timeline.

76. **Strategic bet**. As an operator, I want an incident-style postmortem for failed projects, so
    that blocked or abandoned work improves the system rather than disappearing.

77. **Strategic bet**. As an operator, I want a personal operating-memory layer, so that the system
    learns my default approval preferences, wording style, risk tolerance, and
    favorite delivery format.

78. **Strategic bet**. As an operator, I want a "board of agents" review where each role gets one
    concise dissent before approval, so that important disagreements surface
    early.

79. **Strategic bet**. As a maintainer, I want the system to generate its own next backlog from run
    history, so that the product continuously proposes improvements grounded in
    actual friction.

80. **Strategic bet**. As a maintainer, I want a health score for each topic, project, role, and
    runtime, so that investment goes where the system is weakest.

## Suggested First Slices

1. Project workspace support end to end: API schema, create/edit UI, diff reader
   using `project.workspace_path`, validation, and tests.
2. Attention-first overview: unified queue of pending approvals, open questions,
   blocked tasks, failed runs, and dependency health.
3. Evidence-first task board: criterion verdicts, manual evidence entry, blocker
   explanations, and legal transition controls.
4. Agent run pipeline view: stages, run lineage, retries, validation errors, and
   artifacts produced.
5. Memory provenance view: source quote, origin, score breakdown, and memory
   curation states.
