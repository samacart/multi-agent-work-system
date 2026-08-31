# Agent roles

Eight default profiles are seeded into `agent_profiles` on every API start.
They are defined in `backend/app/agents/profiles.py`; `name` is the natural key,
so editing a prompt there updates the row on the next boot rather than creating
a duplicate.

| Profile | `role` | Owns |
|---|---|---|
| Lead PM | `lead_pm` | Coordination, scoping, task creation, blocking questions, synthesis |
| Architect | `architect` | Technical approach, systems touched, tradeoffs and migration risk |
| Software Developer | `developer` | Implementing scoped tasks, repo conventions, implementation notes |
| QA/Test | `qa` | Verification strategy, coverage gaps, evidence per acceptance criterion |
| Code Reviewer | `code_reviewer` | Correctness, regressions, maintainability, missing tests |
| Security Reviewer | `security_reviewer` | Authn/authz, data handling, secrets, injection, irreversible actions |
| Domain Expert | `domain_expert` | Applying durable topic memory; terminology, history, known failures |
| Release Manager | `release_manager` | Release notes, rollout, migration notes, final summary |

Each profile carries:

- `system_prompt` — how the role works, what it refuses, how it behaves when it
  disagrees with another role, and what done means in its own terms.
- `allowed_tools_json` — what the role may actually do. **Enforced**, not
  documentation: `backend/app/agents/permissions.py` turns these capabilities
  into the tool flags the role's runtime is invoked with. Only `developer` and
  `qa` can edit a repository; only `developer` and `release_manager` can commit.
- `approval_rules_json` — `auto_approved` and `requires_approval` action lists,
  see [operating-model.md](operating-model.md).

Browse them at `GET /agent-profiles`, or in the dashboard's **Agents** tab.

## Adding a role

1. Append a `DefaultAgentProfile` to `DEFAULT_AGENT_PROFILES`.
2. Add the role slug to `AGENT_ROLES` in `app/db/models.py`.
3. Generate a migration (the slug lives in a CHECK constraint):
   `alembic revision --autogenerate -m "add <role> role"`.


## What each role produces

Every pass asks its runtime for one named structured output, defined in
`backend/app/agents/contracts.py`:

| Role | Output contract | Becomes |
|---|---|---|
| Domain Expert | `DomainContext` | the brief's domain section |
| Lead PM | `ProjectBrief`, `TaskBreakdown`, `QuestionSet`, `ApprovalSet` | the brief and task breakdown artifacts, the human queue |
| Architect | `ArchitecturePlan` | the architecture plan artifact |
| Developer, PM, Domain Expert (task passes) | `TaskOutcome` | the agent run record |
| QA/Test | `TestReport` | the test report artifact, plus evidence on each task |
| Code Reviewer | `ReviewReport` | the review report artifact |
| Security Reviewer | `ReviewReport` | the security report artifact |
| Release Manager | `ReleaseSummary`, `PrDescription` | release notes, final summary, PR description |

A reply that fails its contract produces a failed run carrying the validation
error - it never reaches the database half-shaped.
