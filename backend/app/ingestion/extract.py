"""Text extraction from registered sources.

Security boundary: local paths must resolve inside ALLOWED_SOURCE_ROOTS. The
check runs on the fully resolved path, so `..` segments and symlinks that point
outside the roots are both rejected.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from app.config import get_settings


class SourceAccessError(Exception):
    """The source cannot be read, or is not permitted to be read."""


class UnsupportedSourceType(Exception):
    """This source type has no extractor yet."""


@dataclass
class ExtractedDocument:
    name: str
    text: str
    metadata: dict = field(default_factory=dict)


def resolve_within_roots(raw_path: str, roots: list[str] | None = None) -> Path:
    """Resolve `raw_path` and prove it sits inside an allowed root."""
    allowed = roots if roots is not None else get_settings().allowed_source_root_list
    if not allowed:
        raise SourceAccessError("No allowed source roots are configured")

    candidate = Path(raw_path).expanduser()
    try:
        # strict=False so a clear "does not exist" beats an OSError.
        resolved = candidate.resolve(strict=False)
    except OSError as exc:
        raise SourceAccessError(f"Cannot resolve path: {exc}") from exc

    for root in allowed:
        root_resolved = Path(root).expanduser().resolve(strict=False)
        if resolved == root_resolved or root_resolved in resolved.parents:
            if not resolved.exists():
                raise SourceAccessError(f"Path does not exist: {raw_path}")
            return resolved

    raise SourceAccessError(
        f"Path is outside the allowed source roots ({', '.join(allowed)}): {raw_path}"
    )


def _read_text_file(path: Path, max_bytes: int) -> str:
    size = path.stat().st_size
    if size > max_bytes:
        raise SourceAccessError(f"File is larger than the {max_bytes} byte limit: {path} ({size} bytes)")
    # Ingested content is often source code with odd bytes; never fail on those.
    return path.read_text(encoding="utf-8", errors="replace")


async def extract_documents(
    source_type: str,
    uri: str | None,
    metadata: dict | None = None,
    roots: list[str] | None = None,
    github_client=None,  # noqa: ANN001 - injected in tests
) -> list[ExtractedDocument]:
    """Turn a registered source into one or more plain-text documents.

    Async because remote sources are fetched over the network; local extraction
    stays synchronous underneath.
    """
    settings = get_settings()
    metadata = metadata or {}

    if source_type == "pasted_text":
        text = metadata.get("text", "")
        if not str(text).strip():
            raise SourceAccessError("pasted_text source has no 'text' in its metadata")
        return [ExtractedDocument(name=metadata.get("title", "pasted text"), text=str(text))]

    if source_type == "local_file":
        if not uri:
            raise SourceAccessError("local_file source needs a uri")
        path = resolve_within_roots(uri, roots)
        if not path.is_file():
            raise SourceAccessError(f"Not a file: {uri}")
        return [
            ExtractedDocument(
                name=path.name,
                text=_read_text_file(path, settings.max_source_file_bytes),
                metadata={"path": str(path)},
            )
        ]

    if source_type == "local_folder":
        if not uri:
            raise SourceAccessError("local_folder source needs a uri")
        root = resolve_within_roots(uri, roots)
        if not root.is_dir():
            raise SourceAccessError(f"Not a folder: {uri}")
        return _extract_folder(root, settings)

    if source_type in {"github_repo", "github_issue", "github_pr"}:
        from app.github.client import GitHubError
        from app.github.ingest import fetch_documents
        from app.github.urls import InvalidGitHubReference

        try:
            return await fetch_documents(source_type, uri, github_client)
        except (GitHubError, InvalidGitHubReference) as exc:
            raise SourceAccessError(str(exc)) from exc

    if source_type == "url":
        raise UnsupportedSourceType(
            "Source type 'url' is not supported. Paste the content as a pasted_text source instead."
        )

    raise UnsupportedSourceType(f"Unknown source type {source_type!r}")


_SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next", ".pytest_cache"}


def _extract_folder(root: Path, settings) -> list[ExtractedDocument]:  # noqa: ANN001
    extensions = settings.ingest_extension_set
    documents: list[ExtractedDocument] = []
    skipped: list[str] = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS and not d.startswith("."))
        for filename in sorted(filenames):
            if len(documents) >= settings.max_folder_files:
                skipped.append("folder file limit reached")
                break
            path = Path(dirpath) / filename
            if path.suffix.lower() not in extensions:
                continue
            if path.is_symlink():
                # A symlink inside an allowed root can still point outside it.
                try:
                    resolve_within_roots(str(path))
                except SourceAccessError:
                    skipped.append(f"{path}: symlink escapes allowed roots")
                    continue
            try:
                text = _read_text_file(path, settings.max_source_file_bytes)
            except (SourceAccessError, OSError) as exc:
                skipped.append(f"{path}: {exc}")
                continue
            documents.append(
                ExtractedDocument(
                    name=str(path.relative_to(root)),
                    text=text,
                    metadata={"path": str(path)},
                )
            )

    if not documents:
        raise SourceAccessError(
            f"No ingestible files under {root} (extensions: {', '.join(sorted(extensions))})"
        )
    if skipped:
        documents[0].metadata["skipped"] = skipped[:20]
    return documents
