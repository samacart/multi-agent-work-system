"""Heuristic memory extraction."""

from __future__ import annotations

import pytest

from app.memory.extraction import HeuristicMemoryExtractor, get_memory_extractor

NOTES = """
# Onboarding kickoff

We decided that invite links expire after 14 days.
Invites must not be reusable once accepted.
There is a risk that expired invites silently fail and users see a blank page.
Watch out: the invite service caches tokens for 5 minutes.
An invite token is defined as a signed opaque string tied to one organisation.
Who owns the reminder email copy?
The invite service talks to the billing API on signup.
We learned that the previous attempt failed because tokens were guessable.
def some_code(): return 1
| col | col |
ok
"""


@pytest.fixture
def extractor() -> HeuristicMemoryExtractor:
    return HeuristicMemoryExtractor()


async def test_extracts_the_expected_types(extractor):
    memories = await extractor.extract(NOTES)
    types = {m.type for m in memories}
    assert {"decision", "constraint", "risk", "gotcha", "definition", "open_question", "lesson"} <= types


async def test_decision_wins_over_weaker_signals(extractor):
    memories = await extractor.extract("We decided the service must expire tokens after 14 days.")
    assert len(memories) == 1
    assert memories[0].type == "decision"


async def test_code_and_table_noise_is_not_stored(extractor):
    contents = [m.content for m in await extractor.extract(NOTES)]
    assert not any("def some_code" in c for c in contents)
    assert not any(c.startswith("| col") for c in contents)


async def test_short_lines_are_not_stored(extractor):
    assert await extractor.extract("ok\nyes\nfine") == []


async def test_every_memory_keeps_its_source_quote(extractor):
    memories = await extractor.extract(NOTES, metadata={"document": "kickoff.md"})
    assert memories
    for memory in memories:
        assert memory.metadata["source_quote"] == memory.content
        assert memory.metadata["document"] == "kickoff.md"


async def test_concrete_numbers_raise_confidence(extractor):
    vague = await extractor.extract("We decided to shorten the invite window considerably.")
    concrete = await extractor.extract("We decided to shorten the invite window to 14 days.")
    assert concrete[0].confidence > vague[0].confidence


async def test_repeated_sentences_are_deduplicated(extractor):
    text = "We decided invite links expire after 14 days. " * 5
    memories = await extractor.extract(text)
    assert len(memories) == 1


async def test_extraction_is_deterministic(extractor):
    first = await extractor.extract(NOTES)
    second = await extractor.extract(NOTES)
    assert [(m.type, m.content) for m in first] == [(m.type, m.content) for m in second]


async def test_extraction_is_selective(extractor):
    """Not every sentence becomes a memory - that is the whole point."""
    prose = "\n".join(f"This is ordinary narrative sentence number {i} with nothing durable in it." for i in range(20))
    memories = await extractor.extract(prose)
    assert len(memories) < 5


async def test_per_source_cap_is_enforced(extractor, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "max_memories_per_source", 3)
    text = "\n".join(f"We decided that rule number {i} applies to onboarding invites." for i in range(20))
    assert len(await extractor.extract(text)) == 3


def test_extractor_selected_by_config():
    assert get_memory_extractor("heuristic").name == "heuristic"
    with pytest.raises(ValueError, match="Unknown memory extractor"):
        get_memory_extractor("nope")
