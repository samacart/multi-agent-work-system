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


# --- ollama: real semantic embeddings with no credentials ---


def test_ollama_pads_short_vectors_to_the_column_width():
    """nomic-embed-text returns 768 dims into a 1536-wide column. Appending
    zeros to both sides leaves cosine similarity exactly unchanged, which beats
    forcing a schema migration on a deployment-time choice."""
    from app.memory.embeddings import OllamaEmbeddingProvider

    provider = OllamaEmbeddingProvider(1536, "nomic-embed-text", "http://localhost:11434")
    vector = provider._fit([0.5] * 768)  # noqa: SLF001

    assert len(vector) == 1536
    assert vector[:768] == [0.5] * 768
    assert vector[768:] == [0.0] * 768
    # An exact-width vector passes through untouched.
    assert provider._fit([0.1] * 1536) == [0.1] * 1536  # noqa: SLF001


def test_zero_padding_preserves_cosine_similarity_exactly():
    a, b = [0.3, 0.9, -0.2], [0.5, 0.1, 0.4]
    padded_a, padded_b = a + [0.0] * 500, b + [0.0] * 500
    assert cosine_similarity(padded_a, padded_b) == pytest.approx(cosine_similarity(a, b))


def test_ollama_refuses_a_model_wider_than_the_column():
    from app.memory.embeddings import OllamaEmbeddingProvider

    provider = OllamaEmbeddingProvider(768, "some-big-model", "http://localhost:11434")
    with pytest.raises(ValueError, match="Set EMBEDDING_DIM to 1536"):
        provider._fit([0.1] * 1536)  # noqa: SLF001


def test_ollama_is_a_registered_provider():
    provider = get_embedding_provider("ollama")
    assert provider.name == "ollama"


def test_unknown_provider_lists_ollama():
    with pytest.raises(ValueError, match="hash, ollama, openai"):
        get_embedding_provider("nope")
