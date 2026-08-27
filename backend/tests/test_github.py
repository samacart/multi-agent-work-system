"""GitHub reference parsing, ingestion, and delivery."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.models import Artifact, Memory, Project, Source, SourceChunk, Topic
from app.db.seed import seed_agent_profiles
from app.github.client import GitHubClient, GitHubError, GitHubNotConfigured, IssueOrPr, RepoFile
from app.github.delivery import DeliveryError, branch_name, create_pull_request, generate_pr_description, slugify
from app.github.urls import InvalidGitHubReference, parse_github_ref
from app.ingestion.service import ingest_source

# --- reference parsing ---


@pytest.mark.parametrize(
    "raw,owner,repo,kind,number",
    [
        ("https://github.com/anthropics/claude-code", "anthropics", "claude-code", "repo", None),
        ("github.com/anthropics/claude-code/", "anthropics", "claude-code", "repo", None),
        ("https://github.com/anthropics/claude-code.git", "anthropics", "claude-code", "repo", None),
        ("https://github.com/o/r/issues/42", "o", "r", "issue", 42),
        ("https://github.com/o/r/pull/7", "o", "r", "pull", 7),
        ("https://api.github.com/repos/o/r/pulls/7", "o", "r", "pull", 7),
        ("o/r", "o", "r", "repo", None),
    ],
)
def test_parses_the_forms_people_actually_paste(raw, owner, repo, kind, number):
    ref = parse_github_ref(raw)
    assert (ref.owner, ref.repo, ref.kind, ref.number) == (owner, repo, kind, number)


def test_shorthand_number_takes_the_expected_kind():
    """owner/repo#12 is ambiguous - GitHub numbers issues and PRs together."""
    assert parse_github_ref("o/r#12", expected="pull").kind == "pull"
    assert parse_github_ref("o/r#12", expected="issue").kind == "issue"


def test_rejects_non_github_and_mismatched_references():
    with pytest.raises(InvalidGitHubReference):
        parse_github_ref("https://gitlab.com/o/r")
    with pytest.raises(InvalidGitHubReference):
        parse_github_ref("")
    with pytest.raises(InvalidGitHubReference, match="with a number"):
        parse_github_ref("https://github.com/o/r", expected="issue")
    with pytest.raises(InvalidGitHubReference, match="repository reference"):
        parse_github_ref("https://github.com/o/r/pull/3", expected="repo")


# --- a stub client, so no test touches the network ---


class StubGitHub(GitHubClient):
    def __init__(self) -> None:
        self.created: list[dict] = []

    async def repo_files(self, ref):  # noqa: ANN001, ANN201
        return [
            RepoFile("README.md", "We decided that invite links expire after 14 days.", 52),
            RepoFile("docs/design.md", "The invite service must not store raw tokens.", 46),
        ]

    async def issue(self, ref):  # noqa: ANN001, ANN201
        return IssueOrPr(
            number=42,
            title="Invites expire too aggressively",
            body="There is a risk that expired invites fail silently for the user.",
            state="open",
            author="sam",
            labels=["bug", "onboarding"],
            comments=["reviewer: we decided that invite links expire after 14 days."],
        )

    async def pull_request(self, ref):  # noqa: ANN001, ANN201
        return IssueOrPr(
            number=7,
            title="Add invite expiry",
            body="Implements the 14 day expiry window.",
            state="open",
            author="sam",
            comments=["reviewer: watch out for the token cache."],
            base_ref="main",
            head_ref="feature/invite-expiry",
            changed_files=["app/invites.py", "tests/test_invites.py"],
            diff="diff --git a/app/invites.py b/app/invites.py\n+EXPIRY_DAYS = 14\n",
        )

    async def create_pull_request(self, ref, title, body, head, base):  # noqa: ANN001, ANN201
        self.created.append({"ref": ref.slug, "title": title, "head": head, "base": base, "body": body})
        return {"html_url": f"https://github.com/{ref.slug}/pull/99", "number": 99}


@pytest.fixture
async def topic(session) -> Topic:
    topic = Topic(name="customer onboarding")
    session.add(topic)
    await session.commit()
    return topic


async def _ingest(session, topic, type_, uri, client):
    source = Source(topic_id=topic.id, type=type_, name=uri, uri=uri)
    session.add(source)
    await session.commit()
    return source, await ingest_source(session, source.id, github_client=client)


# --- ingestion ---


async def test_repo_ingestion_produces_chunks_and_memories(session, topic):
    _source, summary = await _ingest(session, topic, "github_repo", "https://github.com/o/r", StubGitHub())

    assert summary.status == "ingested"
    assert summary.documents == 2
    assert summary.memories_created > 0

    documents = {c.metadata_json["document"] for c in (await session.scalars(select(SourceChunk))).all()}
    assert documents == {"o/r:README.md", "o/r:docs/design.md"}
    assert {m.type for m in (await session.scalars(select(Memory))).all()} >= {"decision", "constraint"}


async def test_issue_ingestion_keeps_title_body_and_comments(session, topic):
    _source, summary = await _ingest(session, topic, "github_issue", "https://github.com/o/r/issues/42", StubGitHub())

    assert summary.status == "ingested"
    text = " ".join(c.content for c in (await session.scalars(select(SourceChunk))).all())
    assert "Invites expire too aggressively" in text
    assert "expired invites fail silently" in text
    assert "reviewer:" in text
    assert "Labels: bug, onboarding" in text


async def test_pr_ingestion_keeps_the_diff_and_changed_files(session, topic):
    _source, summary = await _ingest(session, topic, "github_pr", "https://github.com/o/r/pull/7", StubGitHub())

    assert summary.status == "ingested"
    text = " ".join(c.content for c in (await session.scalars(select(SourceChunk))).all())
    assert "app/invites.py" in text
    assert "EXPIRY_DAYS = 14" in text
    assert "Merging feature/invite-expiry into main" in text


async def test_a_huge_diff_is_truncated(session, topic):
    from app.github import ingest as ingest_module

    class HugeDiff(StubGitHub):
        async def pull_request(self, ref):  # noqa: ANN001, ANN201
            pr = await super().pull_request(ref)
            pr.diff = "x" * (ingest_module.MAX_DIFF_CHARS + 5000)
            return pr

    _source, summary = await _ingest(session, topic, "github_pr", "https://github.com/o/r/pull/7", HugeDiff())
    assert summary.status == "ingested"
    text = " ".join(c.content for c in (await session.scalars(select(SourceChunk))).all())
    assert "_diff truncated_" in text


async def test_a_bad_reference_fails_the_source_cleanly(session, topic):
    _source, summary = await _ingest(session, topic, "github_issue", "https://github.com/o/r", StubGitHub())
    assert summary.status == "failed"
    assert "with a number" in summary.error


async def test_api_errors_fail_the_source_without_leaking_details(session, topic):
    class BrokenGitHub(StubGitHub):
        async def repo_files(self, ref):  # noqa: ANN001, ANN201
            raise GitHubError("GitHub refused the request (403). Check GITHUB_TOKEN scope or rate limit.")

    _source, summary = await _ingest(session, topic, "github_repo", "https://github.com/o/r", BrokenGitHub())
    assert summary.status == "failed"
    assert "403" in summary.error


def test_the_http_client_refuses_to_start_when_unconfigured():
    from app.config import get_settings
    from app.github.client import HttpGitHubClient

    settings = get_settings()
    token, unauth = settings.github_token, settings.github_allow_unauthenticated
    settings.github_token, settings.github_allow_unauthenticated = None, False
    try:
        with pytest.raises(GitHubNotConfigured, match="GITHUB_TOKEN"):
            HttpGitHubClient()
    finally:
        settings.github_token, settings.github_allow_unauthenticated = token, unauth


# --- delivery ---


def test_branch_names_are_stable_and_namespaced():
    import uuid as uuid_module

    project = Project(id=uuid_module.UUID("12345678-1234-5678-1234-567812345678"), name="Self-Serve Onboarding!")
    assert branch_name(project) == "agents/self-serve-onboarding-12345678"
    assert branch_name(project) == branch_name(project)


def test_slugify_handles_awkward_names():
    assert slugify("A  B/C--D") == "a-b-c-d"
    assert slugify("") == "project"
    assert slugify("!!!") == "project"


@pytest.fixture
async def project(session, topic) -> Project:
    await seed_agent_profiles(session)
    project = Project(topic_id=topic.id, name="self-serve onboarding", goal="let an org sign up unaided")
    session.add(project)
    await session.commit()
    return project


async def test_pr_description_becomes_an_artifact(session, project):
    artifact, description = await generate_pr_description(session, project.id)

    assert artifact.type == "pr_description"
    assert description.title
    assert branch_name(project) in artifact.content
    assert "## Checklist" in artifact.content

    stored = (await session.scalars(select(Artifact).where(Artifact.type == "pr_description"))).all()
    assert len(stored) == 1


async def test_regenerating_replaces_rather_than_appends(session, project):
    await generate_pr_description(session, project.id)
    await generate_pr_description(session, project.id)
    assert len((await session.scalars(select(Artifact).where(Artifact.type == "pr_description"))).all()) == 1


async def test_pr_creation_is_refused_while_writes_are_disabled(session, project):
    from app.config import get_settings

    get_settings().github_allow_writes = False
    with pytest.raises(DeliveryError, match="GITHUB_ALLOW_WRITES"):
        await create_pull_request(session, project.id, "o/r", client=StubGitHub())


async def test_pr_creation_needs_an_approved_gate(session, project):
    from app.approvals.service import ApprovalRequired, respond_to_approval
    from app.config import get_settings

    settings = get_settings()
    settings.github_allow_writes = True
    try:
        stub = StubGitHub()
        with pytest.raises(ApprovalRequired) as exc:
            await create_pull_request(session, project.id, "o/r", client=stub)

        assert exc.value.approval.action_type == "create_pull_request"
        assert exc.value.approval.risk_level == "high"
        assert stub.created == []

        await respond_to_approval(session, exc.value.approval.id, "approved")
        result = await create_pull_request(session, project.id, "o/r", client=stub)

        assert result["number"] == 99
        assert result["head"] == branch_name(project)
        assert stub.created[0]["ref"] == "o/r"
        assert "## Checklist" in stub.created[0]["body"]
    finally:
        settings.github_allow_writes = False


async def test_pr_creation_rejects_a_non_repo_reference(session, project):
    from app.config import get_settings

    settings = get_settings()
    settings.github_allow_writes = True
    try:
        with pytest.raises(InvalidGitHubReference):
            await create_pull_request(session, project.id, "https://github.com/o/r/pull/3", client=StubGitHub())
    finally:
        settings.github_allow_writes = False


async def test_a_repo_with_no_ingestible_files_says_why(session, topic):
    """'produced no chunks' hides the real cause: nothing matched the allowlist."""

    class EmptyRepo(StubGitHub):
        async def repo_files(self, ref):  # noqa: ANN001, ANN201
            return []

    _source, summary = await _ingest(session, topic, "github_repo", "https://github.com/o/r", EmptyRepo())
    assert summary.status == "failed"
    assert "No ingestible files in o/r" in summary.error
    assert "INGEST_EXTENSIONS" in summary.error
