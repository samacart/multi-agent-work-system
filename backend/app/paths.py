"""Proving a path sits inside a root it is allowed to be in.

Shared by ingestion (which roots reading in ALLOWED_SOURCE_ROOTS) and workspaces
(which root agent execution in ALLOWED_WORKSPACE_ROOTS). Security-critical
resolution duplicated in two places is resolution that drifts, so it lives once,
here.

Resolution is done on the fully resolved path, so `..` segments and symlinks
pointing outside a root are both rejected - a symlink inside an allowed root
that resolves outside it is exactly the case a naive prefix check misses.
"""

from __future__ import annotations

from pathlib import Path


class PathNotAllowed(Exception):
    """The path cannot be resolved, does not exist, or is outside every root."""


def resolve_within(raw_path: str, roots: list[str], what: str = "path") -> Path:
    """Resolve `raw_path` and prove it sits inside one of `roots`.

    `what` names the kind of root in the error, so a caller's message reads in
    its own terms rather than in this module's.
    """
    if not roots:
        raise PathNotAllowed(f"No allowed {what} roots are configured")

    candidate = Path(raw_path or "").expanduser()
    if not str(candidate).strip():
        raise PathNotAllowed(f"No {what} given")

    try:
        # strict=False so a clear "does not exist" beats an OSError.
        resolved = candidate.resolve(strict=False)
    except OSError as exc:
        raise PathNotAllowed(f"Cannot resolve path: {exc}") from exc

    for root in roots:
        root_resolved = Path(root).expanduser().resolve(strict=False)
        if resolved == root_resolved or root_resolved in resolved.parents:
            if not resolved.exists():
                raise PathNotAllowed(f"Path does not exist: {raw_path}")
            return resolved

    raise PathNotAllowed(
        f"Path is outside the allowed {what} roots ({', '.join(roots)}): {raw_path}"
    )
