"""What needs the operator, ranked.

The product's stated purpose is to surface decisions only when human judgement
is needed. Until this existed it surfaced them into a tab that looked the same
whether or not anything was waiting, so the operator had to poll the system -
which inverts the premise.

Ranking is a product judgement, so it lives in one named place and every item
carries the reason it scored where it did, the same way memory search exposes
its score components rather than asserting a ranking.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

# Kind ordering, highest first. An approval blocking several tasks outranks a
# single blocked task: unblocking many pieces of work is worth more of the
# operator's attention than diagnosing one.
KIND_WEIGHT: dict[str, int] = {
    "degraded_dependency": 700,  # nothing can run at all
    "approval": 600,  # blocking N tasks, weighted below by risk and count
    "failed_run": 500,  # blocking whatever depended on it
    "stale_run": 400,  # running long enough to be suspect
    "blocked_task": 300,  # blocked with no obvious recovery
    "open_question": 200,  # wanted, but nothing is waiting on it
    "config_warning": 100,  # informational
}

RISK_BONUS = {"high": 30, "medium": 15, "low": 0}

# Within a kind, blast radius dominates: a gate holding eight tasks should sort
# above one holding a single task even if the single one is higher risk.
BLAST_WEIGHT = 6
MAX_BLAST_BONUS = 60
# Age breaks remaining ties so nothing sits unnoticed forever, but it never
# lifts an item past a more urgent kind.
MAX_AGE_BONUS = 9


@dataclass
class AttentionItem:
    kind: str
    title: str
    why: str
    project_id: str | None = None
    project_name: str | None = None
    blast_radius: int = 0
    risk: str = "low"
    age_seconds: float = 0.0
    link: str = ""
    action_id: str | None = None
    score: float = 0.0
    components: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "title": self.title,
            "why": self.why,
            "project_id": self.project_id,
            "project_name": self.project_name,
            "blast_radius": self.blast_radius,
            "risk": self.risk,
            "age_seconds": round(self.age_seconds),
            "link": self.link,
            "action_id": self.action_id,
            "score": round(self.score, 2),
            "components": {k: round(v, 2) for k, v in self.components.items()},
        }


def age_seconds(since: datetime | None, now: datetime | None = None) -> float:
    if since is None:
        return 0.0
    now = now or datetime.now(timezone.utc)
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    return max(0.0, (now - since).total_seconds())


def score_item(item: AttentionItem) -> AttentionItem:
    """Score one item and record why it scored that way."""
    kind = KIND_WEIGHT.get(item.kind, 0)
    blast = min(MAX_BLAST_BONUS, item.blast_radius * BLAST_WEIGHT)
    risk = RISK_BONUS.get(item.risk, 0)
    # Logarithmic in hours so a week-old item does not outrank an urgent one.
    hours = item.age_seconds / 3600.0
    age = min(MAX_AGE_BONUS, hours ** 0.5)

    item.components = {"kind": kind, "blast_radius": blast, "risk": risk, "age": age}
    item.score = kind + blast + risk + age
    return item


def rank(items: list[AttentionItem]) -> list[AttentionItem]:
    """Highest need first. Pure, so the ordering is testable without a database."""
    scored = [score_item(item) for item in items]
    scored.sort(key=lambda i: (i.score, i.age_seconds), reverse=True)
    return scored


def explain_weights() -> dict[str, object]:
    """Exposed so the dashboard can say why something ranked where it did."""
    return {
        "kind": KIND_WEIGHT,
        "risk": RISK_BONUS,
        "blast_weight": BLAST_WEIGHT,
        "max_blast_bonus": MAX_BLAST_BONUS,
        "max_age_bonus": MAX_AGE_BONUS,
    }


async def collect(session, now: datetime | None = None) -> list[AttentionItem]:  # noqa: ANN001
    """Everything currently wanting the operator, across every project."""
    from sqlalchemy import select

    from app.config import get_settings
    from app.db.models import AgentRun, ApprovalRequest, Decision, Project, Source, Task

    now = now or datetime.now(timezone.utc)
    settings = get_settings()
    items: list[AttentionItem] = []

    projects = {p.id: p for p in (await session.scalars(select(Project))).all()}

    def name_of(project_id) -> str | None:  # noqa: ANN001
        project = projects.get(project_id)
        return project.name if project else None

    # How much work each project has waiting on any gate. Gates block roles, not
    # individual tasks, so the blast radius of one pending approval is every
    # unfinished task in the project a gated role owns.
    from app.orchestration.sdlc import GATED_ROLES

    gated_pending: dict[uuid.UUID, int] = {}
    for task in (await session.scalars(select(Task))).all():
        if task.agent_role in GATED_ROLES and task.status != "done":
            gated_pending[task.project_id] = gated_pending.get(task.project_id, 0) + 1

    for approval in (
        await session.scalars(select(ApprovalRequest).where(ApprovalRequest.status == "pending"))
    ).all():
        blast = gated_pending.get(approval.project_id, 0)
        items.append(
            AttentionItem(
                kind="approval",
                title=approval.action_type.replace("_", " "),
                why=approval.action_summary,
                project_id=str(approval.project_id) if approval.project_id else None,
                project_name=name_of(approval.project_id),
                blast_radius=blast,
                risk=approval.risk_level,
                age_seconds=age_seconds(approval.created_at, now),
                link="#queue",
                action_id=str(approval.id),
            )
        )

    for run in (
        await session.scalars(select(AgentRun).where(AgentRun.status.in_(("failed", "running"))))
    ).all():
        age = age_seconds(run.started_at or run.created_at, now)
        if run.status == "failed":
            items.append(
                AttentionItem(
                    kind="failed_run",
                    title=f"{run.input.get('task', 'pass')} failed",
                    why=(run.error or "no error recorded")[:200],
                    project_id=str(run.project_id) if run.project_id else None,
                    project_name=name_of(run.project_id),
                    age_seconds=age,
                    risk="medium",
                    link="#runs",
                    action_id=str(run.id),
                )
            )
        elif age > settings.stale_run_seconds:
            # A run still marked running long after its timeout is almost always
            # a process that died, not work in progress. That is exactly how a
            # killed worker looks, and it looked like progress for an hour.
            items.append(
                AttentionItem(
                    kind="stale_run",
                    title=f"{run.input.get('task', 'pass')} has not finished",
                    why=f"Running for {age / 60:.0f} minutes with no completion recorded",
                    project_id=str(run.project_id) if run.project_id else None,
                    project_name=name_of(run.project_id),
                    age_seconds=age,
                    risk="medium",
                    link="#runs",
                    action_id=str(run.id),
                )
            )

    for task in (await session.scalars(select(Task).where(Task.status == "blocked"))).all():
        items.append(
            AttentionItem(
                kind="blocked_task",
                title=task.title,
                why=str((task.metadata_json or {}).get("blocked_reason") or "Blocked; cause not recorded"),
                project_id=str(task.project_id),
                project_name=name_of(task.project_id),
                blast_radius=1,
                age_seconds=age_seconds(task.updated_at, now),
                link="#board",
                action_id=str(task.id),
            )
        )

    for decision in (
        await session.scalars(select(Decision).where(Decision.answer.is_(None)))
    ).all():
        items.append(
            AttentionItem(
                kind="open_question",
                title=decision.question[:120],
                why=decision.rationale or "",
                project_id=str(decision.project_id),
                project_name=name_of(decision.project_id),
                age_seconds=age_seconds(decision.created_at, now),
                link="#queue",
                action_id=str(decision.id),
            )
        )

    for source in (await session.scalars(select(Source).where(Source.status == "failed"))).all():
        last = (source.metadata_json or {}).get("last_ingestion") or {}
        items.append(
            AttentionItem(
                kind="config_warning",
                title=f"Ingestion failed: {source.name}",
                why=str(last.get("error") or "no reason recorded")[:200],
                age_seconds=age_seconds(source.updated_at, now),
                link="#topics",
                action_id=str(source.id),
            )
        )

    return items
