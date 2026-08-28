"""Reading the workspace diff that review passes judge."""

from __future__ import annotations

import subprocess

import pytest

from app.orchestration.workspace import read_workspace_diff


def _git(path, *args):  # noqa: ANN001, ANN202
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "workspace"
    path.mkdir()
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "test")
    (path / "existing.py").write_text("def original():\n    return 1\n")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "base")
    return path


async def test_a_clean_workspace_reports_no_changes(repo):
    diff = await read_workspace_diff(str(repo))
    assert diff.available is True
    assert diff.is_empty is True
    assert "No changes" in diff.as_context()["diff_status"]


async def test_modified_files_appear_in_the_patch(repo):
    (repo / "existing.py").write_text("def original():\n    return 2\n")

    diff = await read_workspace_diff(str(repo))

    assert diff.changed_files == ["existing.py"]
    assert "return 2" in diff.patch
    assert "1 file changed" in diff.stat


async def test_new_files_are_included_without_staging_them(repo):
    """Most new code lives in untracked files, and `git diff` cannot see them.
    Staging them would mutate the workspace a review is only meant to read."""
    (repo / "added.py").write_text("def brand_new():\n    return 'hello'\n")

    diff = await read_workspace_diff(str(repo))

    assert diff.new_files == ["added.py"]
    assert "brand_new" in diff.patch
    assert "new file: added.py" in diff.patch

    # The index is untouched: the file is still untracked afterwards.
    staged = subprocess.run(
        ["git", "-C", str(repo), "diff", "--cached", "--name-only"], capture_output=True, text=True
    )
    assert staged.stdout.strip() == ""


async def test_the_patch_is_capped(repo):
    (repo / "huge.py").write_text("# padding\n" * 5000)

    diff = await read_workspace_diff(str(repo), max_chars=500)

    assert diff.truncated is True
    assert len(diff.patch) <= 600
    assert "truncated" in diff.as_context()["diff_status"]


async def test_a_missing_workspace_says_so_rather_than_failing():
    diff = await read_workspace_diff("/nope/does/not/exist")
    assert diff.available is False
    assert "does not exist" in diff.reason
    assert "No workspace diff available" in diff.as_context()["diff_status"]


async def test_a_non_repository_says_so(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    diff = await read_workspace_diff(str(plain))
    assert diff.available is False
    assert "not a git repository" in diff.reason


async def test_no_workspace_configured_is_reported_not_crashed():
    diff = await read_workspace_diff(None)
    assert diff.available is False
    assert "CLAUDE_CODE_CWD" in diff.reason
