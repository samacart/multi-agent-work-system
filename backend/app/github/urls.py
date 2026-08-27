"""GitHub URL and reference parsing.

Accepts what a person would actually paste: a browser URL, an API URL, or the
shorthand forms (`owner/repo`, `owner/repo#12`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_BROWSER_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/(?P<owner>[^/\s]+)/(?P<repo>[^/\s#]+?)(?:\.git)?"
    r"(?:/(?P<kind>issues|pull)/(?P<number>\d+))?/?$",
    re.IGNORECASE,
)
_API_RE = re.compile(
    r"^(?:https?://)?api\.github\.com/repos/(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+)"
    r"(?:/(?P<kind>issues|pulls)/(?P<number>\d+))?/?$",
    re.IGNORECASE,
)
_SHORTHAND_RE = re.compile(
    r"^(?P<owner>[A-Za-z0-9][\w.-]*)/(?P<repo>[\w.-]+?)(?:\.git)?(?:#(?P<number>\d+))?$"
)


class InvalidGitHubReference(Exception):
    pass


@dataclass(frozen=True)
class GitHubRef:
    owner: str
    repo: str
    kind: str  # repo | issue | pull
    number: int | None = None

    @property
    def slug(self) -> str:
        base = f"{self.owner}/{self.repo}"
        if self.number is None:
            return base
        return f"{base}#{self.number}"


def parse_github_ref(raw: str, expected: str | None = None) -> GitHubRef:
    """Parse `raw` into a reference, optionally asserting what kind it must be."""
    text = (raw or "").strip()
    if not text:
        raise InvalidGitHubReference("No GitHub reference given")

    for pattern in (_BROWSER_RE, _API_RE):
        match = pattern.match(text)
        if match:
            kind = {"issues": "issue", "pull": "pull", "pulls": "pull"}.get(match.group("kind") or "", "repo")
            number = int(match.group("number")) if match.group("number") else None
            return _validated(GitHubRef(match.group("owner"), match.group("repo"), kind, number), expected)

    match = _SHORTHAND_RE.match(text)
    if match:
        number = int(match.group("number")) if match.group("number") else None
        # `owner/repo#12` is ambiguous between an issue and a PR; GitHub numbers
        # them in one sequence, so the caller's expectation decides.
        kind = "repo" if number is None else (expected or "issue")
        return _validated(GitHubRef(match.group("owner"), match.group("repo"), kind, number), expected)

    raise InvalidGitHubReference(f"Not a GitHub reference: {raw!r}")


def _validated(ref: GitHubRef, expected: str | None) -> GitHubRef:
    if expected is None:
        return ref
    if expected in {"issue", "pull"} and ref.number is None:
        raise InvalidGitHubReference(f"Expected a {expected} reference with a number, got {ref.slug!r}")
    if expected == "repo" and ref.number is not None:
        raise InvalidGitHubReference(f"Expected a repository reference, got {ref.slug!r}")
    if expected in {"issue", "pull"} and ref.kind != expected:
        # A shorthand `owner/repo#12` is coerced; a full URL that disagrees is not.
        return GitHubRef(ref.owner, ref.repo, expected, ref.number)
    return ref


SOURCE_TYPE_TO_KIND = {"github_repo": "repo", "github_issue": "issue", "github_pr": "pull"}
