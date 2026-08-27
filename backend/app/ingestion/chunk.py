"""Chunking.

Splits on paragraph boundaries first and only falls back to sentence and hard
character splits when a block is too big, so a chunk usually stays a coherent
unit of meaning rather than an arbitrary window.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from app.config import get_settings

_PARAGRAPH_RE = re.compile(r"\n\s*\n")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Chunk:
    content: str
    index: int
    metadata: dict = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        return content_hash(self.content)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def _split_oversized(block: str, max_chars: int) -> list[str]:
    """Break a too-large block on sentences, then hard-wrap what is still long."""
    pieces: list[str] = []
    current = ""
    for sentence in _SENTENCE_RE.split(block):
        if not sentence:
            continue
        if len(current) + len(sentence) + 1 <= max_chars:
            current = f"{current} {sentence}".strip()
            continue
        if current:
            pieces.append(current)
        while len(sentence) > max_chars:
            pieces.append(sentence[:max_chars])
            sentence = sentence[max_chars:]
        current = sentence
    if current:
        pieces.append(current)
    return pieces


def chunk_text(
    text: str,
    max_chars: int | None = None,
    overlap: int | None = None,
    metadata: dict | None = None,
) -> list[Chunk]:
    settings = get_settings()
    max_chars = max_chars if max_chars is not None else settings.chunk_max_chars
    overlap = overlap if overlap is not None else settings.chunk_overlap_chars
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    overlap = max(0, min(overlap, max_chars // 2))

    text = (text or "").strip()
    if not text:
        return []

    blocks: list[str] = []
    for paragraph in _PARAGRAPH_RE.split(text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) <= max_chars:
            blocks.append(paragraph)
        else:
            blocks.extend(_split_oversized(paragraph, max_chars))

    # Pack blocks up to the size limit so small paragraphs are not each a chunk.
    packed: list[str] = []
    current = ""
    for block in blocks:
        if not current:
            current = block
        elif len(current) + len(block) + 2 <= max_chars:
            current = f"{current}\n\n{block}"
        else:
            packed.append(current)
            tail = current[-overlap:] if overlap else ""
            # Only carry overlap when it does not push the new chunk over the limit.
            current = f"{tail}\n\n{block}".strip() if tail and len(tail) + len(block) + 2 <= max_chars else block
    if current:
        packed.append(current)

    seen: set[str] = set()
    chunks: list[Chunk] = []
    for content in packed:
        digest = content_hash(content)
        if digest in seen:
            continue
        seen.add(digest)
        chunks.append(Chunk(content=content, index=len(chunks), metadata=dict(metadata or {})))
    return chunks
