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


# Tie-break order when several routes are the same length. Healthy work should
# never be routed through `blocked` just to reach the next state.
_ROUTE_PREFERENCE = ["ready", "in_progress", "review", "verified", "done", "backlog", "blocked"]


def _preferred(statuses: set[str]) -> list[str]:
    return sorted(statuses, key=lambda s: _ROUTE_PREFERENCE.index(s) if s in _ROUTE_PREFERENCE else 99)


def path_to(current: str, target: str) -> list[str]:
    """Shortest legal sequence of statuses from `current` to `target`.

    Callers that move work several steps at once - the SDLC loop picking a task
    up again after a previous run left it in review - should not have to know
    which intermediate states the board requires.
    """
    if current == target:
        return []
    if target not in ALLOWED_TRANSITIONS:
        raise InvalidTransition(current, target)

    queue: list[tuple[str, list[str]]] = [(current, [])]
    seen = {current}
    while queue:
        status, path = queue.pop(0)
        for nxt in _preferred(ALLOWED_TRANSITIONS.get(status, set())):
            if nxt in seen:
                continue
            # `blocked` is a destination, never a waypoint: routing healthy work
            # through it would mark it blocked on the way past.
            if nxt == "blocked" and nxt != target:
                continue
            if nxt == target:
                return [*path, nxt]
            seen.add(nxt)
            queue.append((nxt, [*path, nxt]))
    raise InvalidTransition(current, target)
