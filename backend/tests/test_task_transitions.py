"""Task status transition rules."""

from __future__ import annotations

import pytest

from app.projects.tasks import ALLOWED_TRANSITIONS, InvalidTransition, check_transition


def test_the_happy_path_is_allowed():
    path = ["backlog", "ready", "in_progress", "review", "verified", "done"]
    for current, requested in zip(path, path[1:]):
        check_transition(current, requested)


def test_a_no_op_transition_is_allowed():
    for status in ALLOWED_TRANSITIONS:
        check_transition(status, status)


def test_work_cannot_skip_verification():
    with pytest.raises(InvalidTransition):
        check_transition("in_progress", "done")
    with pytest.raises(InvalidTransition):
        check_transition("backlog", "done")


def test_done_is_terminal():
    for status in ("in_progress", "review", "verified", "backlog"):
        with pytest.raises(InvalidTransition):
            check_transition("done", status)


def test_anything_can_be_blocked_and_recovered():
    for status in ("backlog", "ready", "in_progress", "review"):
        check_transition(status, "blocked")
    check_transition("blocked", "in_progress")


def test_review_can_send_work_back():
    check_transition("review", "in_progress")
    check_transition("verified", "in_progress")


def test_the_error_names_what_is_allowed():
    with pytest.raises(InvalidTransition, match="Allowed from 'ready'"):
        check_transition("ready", "done")


def test_every_status_has_a_rule():
    from app.db.models import TASK_STATUSES

    assert set(ALLOWED_TRANSITIONS) == set(TASK_STATUSES)


def test_path_to_finds_the_shortest_legal_route():
    from app.projects.tasks import path_to

    assert path_to("backlog", "in_progress") == ["ready", "in_progress"]
    assert path_to("review", "in_progress") == ["in_progress"]
    assert path_to("review", "done") == ["verified", "done"]
    assert path_to("done", "done") == []


def test_path_to_refuses_an_impossible_route():
    from app.projects.tasks import InvalidTransition, path_to

    with pytest.raises(InvalidTransition):
        path_to("done", "ready")
    with pytest.raises(InvalidTransition):
        path_to("ready", "nonsense")


def test_every_path_it_returns_is_legal_step_by_step():
    from app.projects.tasks import InvalidTransition, path_to

    for start in ALLOWED_TRANSITIONS:
        for target in ALLOWED_TRANSITIONS:
            try:
                path = path_to(start, target)
            except InvalidTransition:
                continue
            current = start
            for step in path:
                check_transition(current, step)
                current = step
            assert current == target


def test_blocked_is_a_destination_not_a_waypoint():
    """Routing healthy work through 'blocked' would mark it blocked in passing."""
    from app.projects.tasks import path_to

    assert "blocked" not in path_to("backlog", "done")
    assert "blocked" not in path_to("ready", "verified")
    assert path_to("ready", "blocked") == ["blocked"]
