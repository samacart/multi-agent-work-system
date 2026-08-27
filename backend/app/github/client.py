"""GitHub API adapter.

Same shape as the other adapters: one interface, a real HTTP implementation,
and a stub for tests. Nothing above this line makes a network call or knows
what a GitHub JSON payload looks like.

The integration is off unless configured, and writes need a second opt-in.
"""

from __future__ import annotations

import base64
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.config import get_settings
from app.github.urls import GitHubRef

log = logging.getLogger(__name__)


class GitHubError(Exception):
    pass


class GitHubNotConfigured(GitHubError):
    pass


class GitHubWritesDisabled(GitHubError):
    pass


@dataclass
class RepoFile:
    path: str
    text: str
    size: int


@dataclass
class IssueOrPr:
    number: int
    title: str
    body: str
    state: str
    author: str
    labels: list[str] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)
    # Pull requests only.
    base_ref: str | None = None
    head_ref: str | None = None
    changed_files: list[str] = field(default_factory=list)
    diff: str = ""


class GitHubClient(ABC):
    @abstractmethod
    async def repo_files(self, ref: GitHubRef) -> list[RepoFile]: ...

    @abstractmethod
    async def issue(self, ref: GitHubRef) -> IssueOrPr: ...

    @abstractmethod
    async def pull_request(self, ref: GitHubRef) -> IssueOrPr: ...

    @abstractmethod
    async def create_pull_request(
        self, ref: GitHubRef, title: str, body: str, head: str, base: str
    ) -> dict[str, Any]: ...


class HttpGitHubClient(GitHubClient):
    """Real GitHub REST client."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.github_enabled:
            raise GitHubNotConfigured(
                "GitHub integration is disabled. Set GITHUB_TOKEN, or GITHUB_ALLOW_UNAUTHENTICATED=true "
                "for public repositories at a much lower rate limit."
            )
        self._settings = settings
        self._base = settings.github_api_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._settings.github_token:
            headers["Authorization"] = f"Bearer {self._settings.github_token}"
        return headers

    async def _get(self, path: str, params: dict[str, Any] | None = None, accept: str | None = None) -> Any:
        import httpx

        headers = self._headers()
        if accept:
            headers["Accept"] = accept

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{self._base}{path}", headers=headers, params=params)

        if response.status_code == 404:
            raise GitHubError(f"Not found on GitHub: {path}")
        if response.status_code in (401, 403):
            # Never echo the response body; it can carry token hints.
            raise GitHubError(
                f"GitHub refused the request ({response.status_code}). Check GITHUB_TOKEN scope or rate limit."
            )
        if response.status_code >= 400:
            raise GitHubError(f"GitHub returned {response.status_code} for {path}")

        return response.text if accept == "application/vnd.github.diff" else response.json()

    async def repo_files(self, ref: GitHubRef) -> list[RepoFile]:
        settings = self._settings
        repo = await self._get(f"/repos/{ref.owner}/{ref.repo}")
        branch = repo.get("default_branch", "main")
        tree = await self._get(f"/repos/{ref.owner}/{ref.repo}/git/trees/{branch}", {"recursive": "1"})

        if tree.get("truncated"):
            log.warning("tree for %s was truncated by GitHub; ingesting what was returned", ref.slug)

        extensions = settings.ingest_extension_set
        wanted = [
            entry
            for entry in tree.get("tree", [])
            if entry.get("type") == "blob"
            and int(entry.get("size") or 0) <= settings.max_source_file_bytes
            and any(str(entry["path"]).lower().endswith(ext) for ext in extensions)
        ][: settings.github_max_files]

        files: list[RepoFile] = []
        for entry in wanted:
            blob = await self._get(f"/repos/{ref.owner}/{ref.repo}/git/blobs/{entry['sha']}")
            if blob.get("encoding") != "base64":
                continue
            try:
                text = base64.b64decode(blob["content"]).decode("utf-8", errors="replace")
            except (ValueError, KeyError):
                continue
            files.append(RepoFile(path=entry["path"], text=text, size=int(entry.get("size") or 0)))
        return files

    async def _comments(self, ref: GitHubRef) -> list[str]:
        comments = await self._get(
            f"/repos/{ref.owner}/{ref.repo}/issues/{ref.number}/comments", {"per_page": 100}
        )
        return [f"{c['user']['login']}: {c.get('body') or ''}".strip() for c in comments]

    async def issue(self, ref: GitHubRef) -> IssueOrPr:
        data = await self._get(f"/repos/{ref.owner}/{ref.repo}/issues/{ref.number}")
        return IssueOrPr(
            number=data["number"],
            title=data.get("title") or "",
            body=data.get("body") or "",
            state=data.get("state") or "unknown",
            author=(data.get("user") or {}).get("login", "unknown"),
            labels=[label["name"] for label in data.get("labels", [])],
            comments=await self._comments(ref),
        )

    async def pull_request(self, ref: GitHubRef) -> IssueOrPr:
        data = await self._get(f"/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}")
        files = await self._get(f"/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}/files", {"per_page": 100})
        diff = await self._get(
            f"/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}", accept="application/vnd.github.diff"
        )
        return IssueOrPr(
            number=data["number"],
            title=data.get("title") or "",
            body=data.get("body") or "",
            state=data.get("state") or "unknown",
            author=(data.get("user") or {}).get("login", "unknown"),
            labels=[label["name"] for label in data.get("labels", [])],
            comments=await self._comments(ref),
            base_ref=(data.get("base") or {}).get("ref"),
            head_ref=(data.get("head") or {}).get("ref"),
            changed_files=[f["filename"] for f in files],
            diff=diff if isinstance(diff, str) else "",
        )

    async def create_pull_request(
        self, ref: GitHubRef, title: str, body: str, head: str, base: str
    ) -> dict[str, Any]:
        import httpx

        if not self._settings.github_allow_writes:
            raise GitHubWritesDisabled(
                "GitHub writes are disabled. Set GITHUB_ALLOW_WRITES=true to allow creating pull requests."
            )
        if not self._settings.github_token:
            raise GitHubNotConfigured("Creating a pull request requires GITHUB_TOKEN.")

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self._base}/repos/{ref.owner}/{ref.repo}/pulls",
                headers=self._headers(),
                json={"title": title, "body": body, "head": head, "base": base},
            )
        if response.status_code >= 400:
            detail = ""
            try:
                detail = "; ".join(e.get("message", "") for e in response.json().get("errors", []))
            except Exception:  # noqa: BLE001 - error bodies vary; the status is the signal
                detail = ""
            raise GitHubError(f"GitHub refused to create the pull request ({response.status_code}). {detail}".strip())
        return response.json()


def get_github_client() -> GitHubClient:
    return HttpGitHubClient()
