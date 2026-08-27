"""Source text extraction and its path safety boundary."""

from __future__ import annotations

import pytest

from app.ingestion.extract import (
    SourceAccessError,
    UnsupportedSourceType,
    extract_documents,
    resolve_within_roots,
)


@pytest.fixture
def sources_root(tmp_path):
    root = tmp_path / "sources"
    root.mkdir()
    (root / "notes.md").write_text("# Onboarding\n\nInvite links expire after 14 days.")
    (root / "ignored.bin").write_bytes(b"\x00\x01\x02")
    nested = root / "nested"
    nested.mkdir()
    (nested / "design.txt").write_text("The invite service owns token issuance.")
    return root


async def test_pasted_text_is_extracted_from_metadata():
    docs = await extract_documents("pasted_text", None, {"text": "hello world", "title": "kickoff"})
    assert len(docs) == 1
    assert docs[0].name == "kickoff"
    assert docs[0].text == "hello world"


async def test_pasted_text_without_text_is_rejected():
    with pytest.raises(SourceAccessError, match="no 'text'"):
        await extract_documents("pasted_text", None, {})


async def test_local_file_inside_root_is_read(sources_root):
    docs = await extract_documents("local_file", str(sources_root / "notes.md"), roots=[str(sources_root)])
    assert len(docs) == 1
    assert "expire after 14 days" in docs[0].text


async def test_local_folder_walks_supported_extensions(sources_root):
    docs = await extract_documents("local_folder", str(sources_root), roots=[str(sources_root)])
    names = {d.name for d in docs}
    assert "notes.md" in names
    assert "nested/design.txt" in names
    assert "ignored.bin" not in names


async def test_path_outside_allowed_roots_is_refused(sources_root, tmp_path):
    outside = tmp_path / "secret.md"
    outside.write_text("do not read me")
    with pytest.raises(SourceAccessError, match="outside the allowed source roots"):
        await extract_documents("local_file", str(outside), roots=[str(sources_root)])


def test_path_traversal_is_refused(sources_root):
    traversal = str(sources_root / ".." / "escape.md")
    with pytest.raises(SourceAccessError):
        resolve_within_roots(traversal, [str(sources_root)])


async def test_symlink_escaping_the_root_is_refused(sources_root, tmp_path):
    secret = tmp_path / "secret.md"
    secret.write_text("do not read me")
    link = sources_root / "link.md"
    link.symlink_to(secret)
    # The link lives inside the root, but resolves outside it.
    with pytest.raises(SourceAccessError, match="outside the allowed source roots"):
        await extract_documents("local_file", str(link), roots=[str(sources_root)])


async def test_missing_path_reports_clearly(sources_root):
    with pytest.raises(SourceAccessError, match="does not exist"):
        await extract_documents("local_file", str(sources_root / "nope.md"), roots=[str(sources_root)])


async def test_empty_folder_reports_clearly(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    with pytest.raises(SourceAccessError, match="No ingestible files"):
        await extract_documents("local_folder", str(root), roots=[str(root)])


async def test_url_sources_are_not_supported():
    with pytest.raises(UnsupportedSourceType, match="pasted_text"):
        await extract_documents("url", "https://example.com/page")


async def test_oversized_file_is_refused(sources_root, monkeypatch):
    from app.config import get_settings

    big = sources_root / "big.md"
    big.write_text("x" * 5000)
    settings = get_settings()
    monkeypatch.setattr(settings, "max_source_file_bytes", 100)
    with pytest.raises(SourceAccessError, match="larger than"):
        await extract_documents("local_file", str(big), roots=[str(sources_root)])
