"""GitHub delivery: branch naming, PR descriptions, and PR creation.

PR creation is deliberately hard to reach by accident. It needs the integration
configured, writes explicitly enabled, an approved `create_pull_request` gate,
and a head branch that already exists on the remote. Nothing here pushes code -
that needs a runtime that can execute work.
"""

from __future__ import annotations

import logging
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.contracts import PrDescription
from app.agents.runtime.base import AgentContext
from app.approvals.service import ApprovalRequired, check_gate
from app.artifacts.service import bullets, upsert_artifact
from app.config import get_settings
from app.db.models import Artifact, Project, Task
from app.github.client import GitHubClient, GitHubError, get_github_client
from app.github.urls import parse_github_ref
from app.orchestration.runs import AgentRunFailed, execute_run
from app.projects.planning import gather_context

log = logging.getLogger(__name__)

BRANCH_PREFIX = "agents"
PR_APPROVAL_ACTION = "create_pull_request"


class DeliveryError(Exception):
    pass


def slugify(text: str, max_length: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug[:max_length].strip("-") or "project"


def branch_name(project: Project) -> str:
    """Stable per project, so re-running does not scatter branches.

    Namespaced under `agents/` so a human can tell at a glance what created it,
    and so branch protection rules can target it.
    """
    return f"{BRANCH_PREFIX}/{slugify(project.name)}-{str(project.id)[:8]}"


def _pr_markdown(description: PrDescription, branch: str, base: str) -> str:
    return f"""# {description.title}

{description.summary}

Branch: `{branch}` -> `{base}`

## Changes
{bullets(description.changes)}

## Testing
{bullets(description.testing)}

## Risks
{bullets(description.risks, "_none identified_")}

## Checklist
{bullets([f"[ ] {item}" for item in description.checklist])}
"""


async def generate_pr_description(
    session: AsyncSession, project_id: uuid.UUID, base: str = "main"
) -> tuple[Artifact, PrDescription]:
    project = await session.get(Project, project_id)
    if project is None:
        raise DeliveryError(f"Project {project_id} not found")

    tasks = list((await session.scalars(select(Task).where(Task.project_id == project_id))).all())
    context, _memories = await gather_context(session, project)
    context.extra["completed_tasks"] = [t.title for t in tasks if t.status == "done"]
    context.extra["outstanding_tasks"] = [t.title for t in tasks if t.status != "done"]

    try:
        outcome = await execute_run(
            session,
            role="release_manager",
            task="pr_description",
            instruction="Draft the pull request description a reviewer will read.",
            context=AgentContext(
                project_id=str(project.id), memories=context.memories, extra=context.extra
            ),
            project_id=project.id,
        )
    except AgentRunFailed as exc:
        raise DeliveryError(str(exc)) from exc

    description: PrDescription = outcome.output  # type: ignore[assignment]
    artifact = await upsert_artifact(
        session,
        project.id,
        "pr_description",
        f"PR description - {project.name}",
        _pr_markdown(description, branch_name(project), base),
    )
    return artifact, description


async def create_pull_request(
    session: AsyncSession,
    project_id: uuid.UUID,
    repo_uri: str,
    base: str = "main",
    head: str | None = None,
    client: GitHubClient | None = None,
) -> dict:
    """Open a pull request. Gated, and off by default.

    Raises ApprovalRequired when no approved `create_pull_request` gate exists;
    the caller surfaces that to the human queue.
    """
    project = await session.get(Project, project_id)
    if project is None:
        raise DeliveryError(f"Project {project_id} not found")

    settings = get_settings()
    if not settings.github_allow_writes:
        raise DeliveryError(
            "GitHub writes are disabled. Set GITHUB_ALLOW_WRITES=true to allow creating pull requests."
        )

    ref = parse_github_ref(repo_uri, expected="repo")
    head = head or branch_name(project)

    # Raises ApprovalRequired, creating the gate if it does not exist yet.
    await check_gate(
        session,
        PR_APPROVAL_ACTION,
        f"Open a pull request on {ref.slug} from {head} into {base}",
        project_id=project.id,
        risk_level="high",
    )

    artifact = (
        await session.scalars(
            select(Artifact).where(Artifact.project_id == project_id, Artifact.type == "pr_description")
        )
    ).first()
    if artifact is None:
        artifact, description = await generate_pr_description(session, project_id, base)
        title = description.title
    else:
        title = artifact.content.splitlines()[0].lstrip("# ").strip() or project.name

    client = client or get_github_client()
    try:
        pr = await client.create_pull_request(ref, title=title, body=artifact.content, head=head, base=base)
    except GitHubError as exc:
        raise DeliveryError(str(exc)) from exc

    log.info("opened pull request %s for project %s", pr.get("html_url"), project.name)
    return {"url": pr.get("html_url"), "number": pr.get("number"), "head": head, "base": base}


__all__ = [
    "ApprovalRequired",
    "DeliveryError",
    "branch_name",
    "create_pull_request",
    "generate_pr_description",
    "slugify",
]
