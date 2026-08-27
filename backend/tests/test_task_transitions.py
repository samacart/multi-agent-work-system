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
