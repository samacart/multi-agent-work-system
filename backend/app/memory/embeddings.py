"""Embedding provider adapters.

Same pattern as the agent runtime: one interface, a deterministic offline
default, and a real provider behind a config switch. Nothing else in the system
knows which one is in use.
"""

from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod

from app.config import get_settings

_TOKEN_RE = re.compile(r"[a-z0-9']+")


class EmbeddingProvider(ABC):
    name: str = "base"

    def __init__(self, dim: int) -> None:
        self.dim = dim

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_one(self, text: str) -> list[float]:
        return (await self.embed([text]))[0]


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class HashEmbeddingProvider(EmbeddingProvider):
    """Hashing-trick bag-of-words embeddings.

    Offline, deterministic, and free. Unlike random vectors these carry real
    lexical signal: documents sharing words land close together, so memory
    search is genuinely useful in local development. It does not capture
    synonymy or paraphrase - switch EMBEDDING_PROVIDER to a real model for that.
    """

    name = "hash"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        tokens = tokenize(text)
        if not tokens:
            return vector

        # Unigrams plus bigrams: bigrams give a little word-order sensitivity.
        grams = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
        for gram in grams:
            digest = hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dim
            # Signed buckets keep unrelated collisions from always adding up.
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign

        # Sublinear scaling then L2 normalisation, so cosine similarity is not
        # dominated by document length.
        vector = [math.copysign(math.log1p(abs(v)), v) for v in vector]
        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0:
            return vector
        return [v / norm for v in vector]


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """Real embeddings via the OpenAI API. Requires OPENAI_API_KEY."""

    name = "openai"
    _BATCH = 64

    def __init__(self, dim: int, model: str, api_key: str) -> None:
        super().__init__(dim)
        self.model = model
        self._api_key = api_key

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import httpx

        out: list[list[float]] = []
        async with httpx.AsyncClient(timeout=60) as client:
            for start in range(0, len(texts), self._BATCH):
                batch = texts[start : start + self._BATCH]
                response = await client.post(
                    "https://api.openai.com/v1/embeddings",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={"model": self.model, "input": batch},
                )
                response.raise_for_status()
                data = response.json()["data"]
                out.extend(item["embedding"] for item in sorted(data, key=lambda d: d["index"]))
        return out


def get_embedding_provider(name: str | None = None) -> EmbeddingProvider:
    settings = get_settings()
    key = (name or settings.embedding_provider).lower()

    if key == "hash":
        return HashEmbeddingProvider(settings.embedding_dim)
    if key == "openai":
        if not settings.openai_api_key:
            raise ValueError("EMBEDDING_PROVIDER=openai requires OPENAI_API_KEY to be set")
        return OpenAIEmbeddingProvider(settings.embedding_dim, settings.embedding_model, settings.openai_api_key)
    raise ValueError(f"Unknown embedding provider {key!r}. Available: hash, openai")


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
