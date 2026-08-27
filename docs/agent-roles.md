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

- `system_prompt` — the role instruction, verbatim from the brief.
- `allowed_tools_json` — intended blast radius. Advisory in Phase 1; no runtime
  enforces it yet.
- `approval_rules_json` — `auto_approved` and `requires_approval` action lists,
  see [operating-model.md](operating-model.md).

Browse them at `GET /agent-profiles`, or in the dashboard's **Agents** tab.

## Adding a role

1. Append a `DefaultAgentProfile` to `DEFAULT_AGENT_PROFILES`.
2. Add the role slug to `AGENT_ROLES` in `app/db/models.py`.
3. Generate a migration (the slug lives in a CHECK constraint):
   `alembic revision --autogenerate -m "add <role> role"`.
