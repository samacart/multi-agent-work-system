"""Embedding providers."""

from __future__ import annotations

import pytest

from app.memory.embeddings import (
    HashEmbeddingProvider,
    cosine_similarity,
    get_embedding_provider,
)


async def test_hash_embeddings_are_deterministic():
    provider = HashEmbeddingProvider(256)
    a = await provider.embed_one("invite links expire after 14 days")
    b = await provider.embed_one("invite links expire after 14 days")
    assert a == b
    assert len(a) == 256


async def test_hash_embeddings_are_normalised():
    provider = HashEmbeddingProvider(256)
    vector = await provider.embed_one("some reasonably long piece of onboarding text")
    assert cosine_similarity(vector, vector) == pytest.approx(1.0, abs=1e-6)


async def test_similar_text_scores_higher_than_unrelated_text():
    """The offline provider must carry real lexical signal, otherwise memory
    search would be meaningless without an API key."""
    provider = HashEmbeddingProvider(1536)
    query = await provider.embed_one("how long do invite links stay valid")
    related = await provider.embed_one("invite links stay valid for 14 days after they are sent")
    unrelated = await provider.embed_one("the billing cron job runs nightly to reconcile ledgers")

    assert cosine_similarity(query, related) > cosine_similarity(query, unrelated)


async def test_empty_text_embeds_to_a_zero_vector():
    provider = HashEmbeddingProvider(64)
    assert await provider.embed_one("") == [0.0] * 64


def test_cosine_similarity_edge_cases():
    assert cosine_similarity([], [1.0]) == 0.0
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


def test_provider_selected_by_config():
    provider = get_embedding_provider("hash")
    assert provider.name == "hash"


def test_openai_provider_requires_a_key(monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "openai_api_key", None)
    with pytest.raises(ValueError, match="requires OPENAI_API_KEY"):
        get_embedding_provider("openai")


def test_unknown_provider_fails_loudly():
    with pytest.raises(ValueError, match="Unknown embedding provider"):
        get_embedding_provider("nope")
