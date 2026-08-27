"""Task status transitions.

The board is only meaningful if the moves are constrained: an unverified task
must not jump straight to done, and finished work should not silently reopen.
"""

from __future__ import annotations

# Forward moves plus the two backward moves that real work needs: anything can
# get blocked, and review or verification can send work back.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "backlog": {"ready", "blocked"},
    "ready": {"in_progress", "blocked", "backlog"},
    "in_progress": {"review", "blocked", "ready"},
    "blocked": {"backlog", "ready", "in_progress", "review"},
    "review": {"verified", "in_progress", "blocked"},
    "verified": {"done", "in_progress"},
    "done": set(),
}


class InvalidTransition(Exception):
    def __init__(self, current: str, requested: str) -> None:
        allowed = ", ".join(sorted(ALLOWED_TRANSITIONS.get(current, set()))) or "nothing (terminal)"
        super().__init__(f"Cannot move a task from {current!r} to {requested!r}. Allowed from {current!r}: {allowed}")
        self.current = current
        self.requested = requested


def check_transition(current: str, requested: str) -> None:
    if current == requested:
        return
    if requested not in ALLOWED_TRANSITIONS.get(current, set()):
        raise InvalidTransition(current, requested)
