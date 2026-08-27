"""Chunking."""

from __future__ import annotations

from app.ingestion.chunk import chunk_text, content_hash


def test_short_text_is_a_single_chunk():
    chunks = chunk_text("A short note about onboarding.")
    assert len(chunks) == 1
    assert chunks[0].index == 0
    assert chunks[0].content == "A short note about onboarding."


def test_empty_text_produces_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_paragraphs_are_packed_up_to_the_limit():
    text = "\n\n".join(f"Paragraph number {i} with some filler text." for i in range(10))
    chunks = chunk_text(text, max_chars=120, overlap=0)
    assert len(chunks) > 1
    assert all(len(c.content) <= 120 for c in chunks)
    # Packing, not one chunk per paragraph.
    assert len(chunks) < 10


def test_oversized_paragraph_is_split_on_sentences():
    text = " ".join(
        f"Sentence number {i} is deliberately long enough that the paragraph must be split." for i in range(20)
    )
    chunks = chunk_text(text, max_chars=200, overlap=0)
    assert len(chunks) > 1
    assert all(len(c.content) <= 200 for c in chunks)
    # Splitting must not lose content.
    assert "Sentence number 19" in " ".join(c.content for c in chunks)


def test_a_single_unbroken_run_is_hard_wrapped():
    text = "".join(f"{i:04d}" for i in range(250))  # 1000 chars, no repeating window
    chunks = chunk_text(text, max_chars=100, overlap=0)
    assert len(chunks) == 10
    assert all(len(c.content) == 100 for c in chunks)
    assert "".join(c.content for c in chunks) == text


def test_chunks_are_contiguous_and_indexed():
    text = "\n\n".join(f"Block {i} of the document." for i in range(6))
    chunks = chunk_text(text, max_chars=60, overlap=0)
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_identical_blocks_are_deduplicated():
    """Byte-identical chunks collapse to one.

    This is not just tidiness: source_chunks has a unique (source_id,
    content_hash) constraint, so emitting duplicates would fail the insert.
    """
    text = "\n\n".join(["The same paragraph repeated verbatim every time."] * 5)
    chunks = chunk_text(text, max_chars=60, overlap=0)
    assert len(chunks) == 1


def test_content_hash_ignores_surrounding_whitespace():
    assert content_hash("  hello  ") == content_hash("hello")
    assert content_hash("hello") != content_hash("goodbye")


def test_overlap_carries_context_between_chunks():
    text = "\n\n".join(f"Distinct paragraph {i} carrying its own words." for i in range(6))
    with_overlap = chunk_text(text, max_chars=120, overlap=40)
    assert all(len(c.content) <= 120 for c in with_overlap)
    assert len(with_overlap) > 1
