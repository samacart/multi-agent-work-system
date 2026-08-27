"""Turn GitHub references into ingestible documents."""

from __future__ import annotations

from app.github.client import GitHubClient, GitHubError, IssueOrPr, get_github_client
from app.github.urls import SOURCE_TYPE_TO_KIND, parse_github_ref
from app.ingestion.extract import ExtractedDocument

# A diff can be enormous and is mostly noise for memory extraction; keep enough
# to see what the change touches.
MAX_DIFF_CHARS = 40_000


async def fetch_documents(
    source_type: str, uri: str | None, client: GitHubClient | None = None
) -> list[ExtractedDocument]:
    kind = SOURCE_TYPE_TO_KIND[source_type]
    ref = parse_github_ref(uri or "", expected=kind)
    client = client or get_github_client()

    if kind == "repo":
        files = await client.repo_files(ref)
        if not files:
            from app.config import get_settings

            raise GitHubError(
                f"No ingestible files in {ref.slug}. Files must match INGEST_EXTENSIONS "
                f"({', '.join(sorted(get_settings().ingest_extension_set))}) and be under "
                f"MAX_SOURCE_FILE_BYTES."
            )
        return [
            ExtractedDocument(
                name=f"{ref.slug}:{file.path}",
                text=file.text,
                metadata={"github": ref.slug, "path": file.path, "bytes": file.size},
            )
            for file in files
        ]

    item = await (client.issue(ref) if kind == "issue" else client.pull_request(ref))
    return [ExtractedDocument(name=f"{ref.slug}", text=_render(kind, item), metadata=_metadata(ref, kind, item))]


def _render(kind: str, item: IssueOrPr) -> str:
    parts = [f"# {item.title}", "", f"State: {item.state}. Opened by {item.author}."]
    if item.labels:
        parts.append(f"Labels: {', '.join(item.labels)}.")
    if kind == "pull" and item.head_ref:
        parts.append(f"Merging {item.head_ref} into {item.base_ref}.")
    parts += ["", item.body or "_no description_"]

    if item.comments:
        parts += ["", "## Comments", ""]
        parts.extend(item.comments)

    if kind == "pull":
        if item.changed_files:
            parts += ["", "## Changed files", ""]
            parts.extend(f"- {path}" for path in item.changed_files)
        if item.diff:
            diff = item.diff[:MAX_DIFF_CHARS]
            truncated = "\n\n_diff truncated_" if len(item.diff) > MAX_DIFF_CHARS else ""
            parts += ["", "## Diff", "", "```diff", diff, "```", truncated]

    return "\n".join(parts)


def _metadata(ref, kind: str, item: IssueOrPr) -> dict:  # noqa: ANN001
    metadata = {
        "github": ref.slug,
        "kind": kind,
        "number": item.number,
        "state": item.state,
        "author": item.author,
        "labels": item.labels,
    }
    if kind == "pull":
        metadata.update(
            {"base_ref": item.base_ref, "head_ref": item.head_ref, "changed_files": item.changed_files}
        )
    return metadata
