"""Per-project workspaces: allowed roots, validation, and the global fallback.

A workspace becomes an agent's working directory with shell access, so it is
constrained rather than trusted.
"""

from __future__ import annotations

import subprocess

import pytest

from app.config import get_settings
from app.orchestration.workspace import validate_workspace, workspace_for
from app.paths import PathNotAllowed, resolve_within


def _git(path, *args):  # noqa: ANN001, ANN202
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


@pytest.fixture
def roots(tmp_path, monkeypatch):
    root = tmp_path / "workspaces"
    root.mkdir()
    monkeypatch.setattr(get_settings(), "allowed_workspace_roots", str(root))
    return root


@pytest.fixture
def repo(roots):
    path = roots / "project-a"
    path.mkdir()
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@example.com")
    _git(path, "config", "user.name", "t")
    (path / "file.py").write_text("x = 1\n")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "base")
    return path


# --- the shared resolver ---


def test_resolution_requires_a_configured_root():
    """An unset root is a missing decision, not permission."""
    with pytest.raises(PathNotAllowed, match="No allowed workspace roots"):
        resolve_within("/anywhere", [], what="workspace")


def test_resolution_rejects_traversal(roots):
    with pytest.raises(PathNotAllowed, match="outside the allowed"):
        resolve_within(str(roots / ".." / "escape"), [str(roots)], what="workspace")


def test_resolution_rejects_a_symlink_escaping_the_root(roots, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    link = roots / "link"
    link.symlink_to(outside)
    with pytest.raises(PathNotAllowed, match="outside the allowed"):
        resolve_within(str(link), [str(roots)], what="workspace")


# --- validation ---


async def test_a_valid_repository_validates(repo):
    validation = await validate_workspace(str(repo))
    assert validation.valid is True
    assert validation.resolved_path == str(repo)
    assert validation.branch
    assert validation.dirty_files == 0


async def test_a_path_outside_the_roots_is_refused(roots, tmp_path):
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    validation = await validate_workspace(str(outside))
    assert validation.valid is False
    assert "outside the allowed workspace roots" in validation.reason


async def test_a_missing_workspace_is_refused(roots):
    validation = await validate_workspace(str(roots / "not-there"))
    assert validation.valid is False
    assert "does not exist" in validation.reason


async def test_a_non_git_directory_is_refused(roots):
    plain = roots / "plain"
    plain.mkdir()
    validation = await validate_workspace(str(plain))
    assert validation.valid is False
    assert "Not a git repository" in validation.reason


async def test_an_unconfigured_root_refuses_every_workspace(repo, monkeypatch):
    """Fails closed: with no roots configured, no project may set a workspace."""
    monkeypatch.setattr(get_settings(), "allowed_workspace_roots", "")
    validation = await validate_workspace(str(repo))
    assert validation.valid is False


async def test_a_working_tree_validates_but_warns(repo):
    """Valid is not the same as advisable - agents write here."""
    (repo / "file.py").write_text("x = 2\n")
    validation = await validate_workspace(str(repo))

    assert validation.valid is True
    assert validation.dirty_files == 1
    assert any("uncommitted" in w for w in validation.warnings)
    assert any("not an agents/ branch" in w for w in validation.warnings)


async def test_an_agent_branch_does_not_warn_about_the_branch(repo):
    _git(repo, "checkout", "-q", "-b", "agents/thing")
    validation = await validate_workspace(str(repo))
    assert validation.is_agent_branch is True
    assert not any("branch" in w for w in validation.warnings)


# --- the fallback ---


def test_a_project_workspace_wins_over_the_global_setting(monkeypatch):
    from app.db.models import Project

    monkeypatch.setattr(get_settings(), "claude_code_cwd", "/global/repo")
    project = Project(name="p", workspace_path="/project/repo")
    assert workspace_for(project) == "/project/repo"


def test_the_global_setting_is_a_fallback_not_an_override(monkeypatch):
    from app.db.models import Project

    monkeypatch.setattr(get_settings(), "claude_code_cwd", "/global/repo")
    assert workspace_for(Project(name="p")) == "/global/repo"


def test_no_workspace_anywhere_resolves_to_nothing(monkeypatch):
    from app.db.models import Project

    monkeypatch.setattr(get_settings(), "claude_code_cwd", "")
    assert workspace_for(Project(name="p")) is None


# --- the point of the slice: two projects, two repositories, one process ---


@pytest.fixture
def two_repos(roots):
    made = {}
    for name, content in (("alpha", "ALPHA_MARKER = 1\n"), ("beta", "BETA_MARKER = 2\n")):
        path = roots / name
        path.mkdir()
        _git(path, "init", "-q")
        _git(path, "config", "user.email", "t@example.com")
        _git(path, "config", "user.name", "t")
        (path / "base.py").write_text("base\n")
        _git(path, "add", "-A")
        _git(path, "commit", "-q", "-m", "base")
        (path / "changed.py").write_text(content)
        made[name] = path
    return made


async def test_two_projects_read_their_own_repositories(session, two_repos, monkeypatch):
    """The whole reason for the slice: the workspace was global configuration,
    so pointing agents elsewhere meant editing .env and restarting the server."""
    from app.db.models import Project
    from app.orchestration.workspace import read_workspace_diff

    monkeypatch.setattr(get_settings(), "claude_code_cwd", "")
    alpha = Project(name="alpha", workspace_path=str(two_repos["alpha"]))
    beta = Project(name="beta", workspace_path=str(two_repos["beta"]))
    session.add_all([alpha, beta])
    await session.commit()

    alpha_diff = await read_workspace_diff(workspace_for(alpha))
    beta_diff = await read_workspace_diff(workspace_for(beta))

    assert "ALPHA_MARKER" in alpha_diff.patch
    assert "BETA_MARKER" not in alpha_diff.patch
    assert "BETA_MARKER" in beta_diff.patch
    assert "ALPHA_MARKER" not in beta_diff.patch


async def test_a_project_without_a_workspace_falls_back_to_the_global_one(
    session, two_repos, monkeypatch
):
    from app.db.models import Project
    from app.orchestration.workspace import read_workspace_diff

    monkeypatch.setattr(get_settings(), "claude_code_cwd", str(two_repos["alpha"]))
    project = Project(name="unset")
    session.add(project)
    await session.commit()

    diff = await read_workspace_diff(workspace_for(project))
    assert "ALPHA_MARKER" in diff.patch


async def test_truncation_names_the_files_a_reviewer_did_not_see(roots):
    """"Truncated" alone tells a reviewer something was hidden but not what."""
    from app.orchestration.workspace import read_workspace_diff

    path = roots / "big"
    path.mkdir()
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@example.com")
    _git(path, "config", "user.name", "t")
    (path / "base.py").write_text("base\n")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "base")
    for n in range(4):
        (path / f"new{n}.py").write_text("# padding\n" * 400)

    diff = await read_workspace_diff(str(path), max_chars=600)

    assert diff.truncated is True
    assert diff.omitted_files
    assert "files_not_shown" in diff.as_context()


async def test_the_global_fallback_is_not_held_to_the_allowed_roots(repo, monkeypatch):
    """CLAUDE_CODE_CWD is set by whoever runs the server, in the same file as
    the database credentials. Holding it to a list it predates would break every
    existing deployment; it still has to exist and be a git repository."""
    monkeypatch.setattr(get_settings(), "allowed_workspace_roots", "")

    assert (await validate_workspace(str(repo), enforce_roots=True)).valid is False
    assert (await validate_workspace(str(repo), enforce_roots=False)).valid is True


async def test_the_fallback_still_has_to_be_a_real_repository(roots, monkeypatch):
    plain = roots / "plain"
    plain.mkdir()
    validation = await validate_workspace(str(plain), enforce_roots=False)
    assert validation.valid is False
    assert "Not a git repository" in validation.reason
