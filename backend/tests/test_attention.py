"""Ranking what needs the operator.

The ordering is a product judgement, so it is asserted directly rather than
left to emerge from whatever the collector happens to return.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.orchestration.attention import (
    KIND_WEIGHT,
    AttentionItem,
    age_seconds,
    explain_weights,
    rank,
    score_item,
)


def _item(kind: str, **kwargs) -> AttentionItem:
    return AttentionItem(kind=kind, title=kwargs.pop("title", kind), why="", **kwargs)


# --- the ordering itself ---


def test_a_degraded_dependency_outranks_everything():
    """If nothing can run at all, nothing else matters."""
    ranked = rank(
        [
            _item("approval", blast_radius=20, risk="high"),
            _item("degraded_dependency"),
            _item("failed_run"),
        ]
    )
    assert ranked[0].kind == "degraded_dependency"


def test_an_approval_outranks_a_single_blocked_task():
    """Unblocking several pieces of work is worth more attention than
    diagnosing one."""
    ranked = rank([_item("blocked_task", blast_radius=1), _item("approval", blast_radius=3)])
    assert ranked[0].kind == "approval"


def test_the_full_kind_order_holds():
    ranked = rank([_item(kind) for kind in KIND_WEIGHT])
    assert [i.kind for i in ranked] == [
        "degraded_dependency",
        "approval",
        "failed_run",
        "stale_run",
        "blocked_task",
        "open_question",
        "config_warning",
    ]


def test_blast_radius_orders_approvals_against_each_other():
    ranked = rank(
        [
            _item("approval", title="small", blast_radius=1, risk="high"),
            _item("approval", title="wide", blast_radius=9, risk="low"),
        ]
    )
    assert ranked[0].title == "wide", "blast radius should dominate risk within a kind"


def test_risk_breaks_ties_at_equal_blast_radius():
    ranked = rank(
        [
            _item("approval", title="low", blast_radius=2, risk="low"),
            _item("approval", title="high", blast_radius=2, risk="high"),
        ]
    )
    assert ranked[0].title == "high"


def test_age_never_lifts_an_item_past_a_more_urgent_kind():
    """A week-old question must not outrank a fresh failed run."""
    ranked = rank(
        [
            _item("open_question", age_seconds=86400 * 30),
            _item("failed_run", age_seconds=1),
        ]
    )
    assert ranked[0].kind == "failed_run"


def test_age_breaks_ties_within_a_kind():
    ranked = rank(
        [
            _item("open_question", title="new", age_seconds=60),
            _item("open_question", title="old", age_seconds=86400 * 5),
        ]
    )
    assert ranked[0].title == "old"


def test_every_item_explains_its_own_score():
    """The same property memory search has: a ranking you can interrogate."""
    item = score_item(_item("approval", blast_radius=3, risk="high", age_seconds=3600))
    assert set(item.components) == {"kind", "blast_radius", "risk", "age"}
    assert item.score == pytest.approx(sum(item.components.values()))
    assert set(explain_weights()) >= {"kind", "risk", "blast_weight"}


def test_an_unknown_kind_sorts_last_rather_than_crashing():
    ranked = rank([_item("something_new"), _item("open_question")])
    assert ranked[-1].kind == "something_new"


def test_age_of_a_naive_timestamp_is_treated_as_utc():
    now = datetime.now(timezone.utc)
    assert age_seconds(now.replace(tzinfo=None), now) == pytest.approx(0, abs=1)
    assert age_seconds(None) == 0.0
    assert age_seconds(now + timedelta(hours=1), now) == 0.0


# --- collecting real state ---


@pytest.fixture
def healthy_queue(monkeypatch):
    """The suite points Redis at a dead port on purpose, and an unreachable
    queue is itself something that needs the operator - so the quiet state has
    to be tested against healthy dependencies."""
    import app.api.routes.attention as module

    async def alive() -> bool:
        return True

    async def depth() -> int:
        return 0

    monkeypatch.setattr(module, "worker_alive", alive)
    monkeypatch.setattr(module, "queue_depth", depth)


async def test_nothing_outstanding_is_a_deliberate_empty_state(client, healthy_queue):
    body = (await client.get("/attention")).json()
    assert body["needs_you"] is False
    assert body["items"] == []


async def test_an_unreachable_queue_is_itself_urgent(client):
    """Redis down means async ingestion and runs cannot start at all."""
    body = (await client.get("/attention")).json()
    top = body["items"][0]
    assert top["kind"] == "degraded_dependency"
    assert top["risk"] == "high"


async def test_a_dead_worker_with_queued_jobs_is_urgent(client, monkeypatch):
    """A queued job with nothing to consume it looked exactly like progress."""
    import app.api.routes.attention as module

    async def alive() -> bool:
        return False

    async def depth() -> int:
        return 4

    monkeypatch.setattr(module, "worker_alive", alive)
    monkeypatch.setattr(module, "queue_depth", depth)

    top = (await client.get("/attention")).json()["items"][0]
    assert top["kind"] == "degraded_dependency"
    assert "Worker is not running" in top["title"]
    assert "4 job(s) queued" in top["why"]


async def test_a_pending_approval_appears_with_its_blast_radius(client, healthy_queue, session):
    from app.db.models import Project, Task
    from app.approvals.service import request_approval

    project = Project(name="p")
    session.add(project)
    await session.commit()
    session.add_all(
        [
            Task(project_id=project.id, title="a", agent_role="developer", status="ready"),
            Task(project_id=project.id, title="b", agent_role="architect", status="ready"),
            Task(project_id=project.id, title="c", agent_role="qa", status="ready"),
        ]
    )
    await session.commit()
    await request_approval(session, "deploy", "Deploy it", project_id=project.id, risk_level="high")

    body = (await client.get("/attention")).json()
    item = next(i for i in body["items"] if i["kind"] == "approval")

    assert body["needs_you"] is True
    # Two gated roles are waiting; QA is not a gated role.
    assert item["blast_radius"] == 2
    assert item["risk"] == "high"
    assert item["project_name"] == "p"
    assert item["link"] == "#queue"


async def test_a_stale_run_is_distinguished_from_one_still_working(client, healthy_queue, session, monkeypatch):
    """A run still marked running long after its timeout is almost always a
    process that died - which is exactly how a killed worker looked."""
    from app.config import get_settings
    from app.db.models import AgentProfile, AgentRun, Project

    monkeypatch.setattr(get_settings(), "stale_run_seconds", 60)
    project = Project(name="p")
    profile = AgentProfile(name="x", role="developer", system_prompt="s")
    session.add_all([project, profile])
    await session.commit()

    now = datetime.now(timezone.utc)
    session.add_all(
        [
            AgentRun(
                project_id=project.id,
                agent_profile_id=profile.id,
                status="running",
                input={"task": "old"},
                started_at=now - timedelta(hours=2),
            ),
            AgentRun(
                project_id=project.id,
                agent_profile_id=profile.id,
                status="running",
                input={"task": "fresh"},
                started_at=now,
            ),
        ]
    )
    await session.commit()

    items = (await client.get("/attention")).json()["items"]
    stale = [i for i in items if i["kind"] == "stale_run"]

    assert len(stale) == 1
    assert "old" in stale[0]["title"]


async def test_a_failed_ingestion_surfaces_as_a_config_warning(client, healthy_queue, session):
    from app.db.models import Source, Topic

    topic = Topic(name="t")
    session.add(topic)
    await session.commit()
    session.add(
        Source(
            topic_id=topic.id,
            type="local_file",
            name="notes.md",
            status="failed",
            metadata_json={"last_ingestion": {"error": "Path does not exist"}},
        )
    )
    await session.commit()

    items = (await client.get("/attention")).json()["items"]
    warning = next(i for i in items if i["kind"] == "config_warning")
    assert "notes.md" in warning["title"]
    assert "Path does not exist" in warning["why"]
