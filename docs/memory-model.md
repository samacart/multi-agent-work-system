# Memory model

## Layers

```text
Global memory        user preferences, operating rules, default approval rules
Organization memory  company-wide terms, systems, teams, policies
Topic memory         facts, decisions, risks, architecture notes, history
Project memory       project scope, decisions, assumptions, status
Agent memory         role-specific lessons and successful patterns
```

v1 implements **topic** and **project** memory. Both live in the `memories`
table, distinguished by `project_id` being null or set.

## Two tiers of storage

**`source_chunks`** — the raw substrate. Every chunk of every ingested source,
with an embedding, for retrieval and citation. Deduplicated per source by
`content_hash` (unique constraint on `source_id, content_hash`).

**`memories`** — durable, reusable knowledge extracted *from* chunks. Not every
chunk becomes a memory; extraction should keep what is still true and still
useful next month.

Memory types: `fact`, `decision`, `constraint`, `risk`, `architecture`,
`definition`, `person`, `system`, `open_question`, `lesson`, `gotcha`.

Each memory carries `confidence` and `importance` (0–1), and `metadata_json`
holding at minimum the `source_quote` it came from, so any claim is traceable
back to a source.

## Retrieval

`search_memories()` in `backend/app/memory/search.py` blends six signals with
fixed weights that sum to 1.0:

| Signal | Weight | Source |
|---|---|---|
| similarity | 0.55 | cosine distance on `embedding`, mapped from -1..1 to 0..1 |
| importance | 0.15 | `memories.importance` |
| confidence | 0.10 | `memories.confidence` |
| recency | 0.10 | exponential decay, 45-day half-life |
| reliability | 0.05 | per-source-type default, or `sources.metadata_json["reliability"]` |
| scope | 0.05 | topic and project match |

Similarity alone surfaces things that merely *sound* relevant; the other five
are what let a recent explicit decision beat an old low-confidence aside.

On Postgres the candidate set comes from a pgvector nearest-neighbour query
(`embedding <=> :query`, backed by the HNSW indexes in migration `0002`), then
gets re-ranked in Python with the full formula. Elsewhere - the SQLite test
suite - candidates are loaded and scored directly.

Every hit returns its component breakdown, so a surprising ranking can be
explained rather than guessed at.

## Extraction

`MemoryExtractor` (`backend/app/memory/extraction.py`) is an adapter, same shape
as the agent runtime. The default `heuristic` extractor is deterministic and
offline: it splits text into sentences, drops code and table noise, and matches
ordered phrasing rules - most specific first, so "we decided the service must
..." is recorded as a `decision` rather than a `constraint`. Sentences carrying
a number, date, or version get a confidence and importance bump, because they
are concrete and checkable.

It is tuned for precision. A memory store full of restated prose is worse than
a small one, since every later retrieval pays for the noise.

Embeddings are `VECTOR(1536)` — `text-embedding-3-small`, set by
`EMBEDDING_MODEL` / `EMBEDDING_DIM`. The dimension is pinned in migration
`0001`; changing it needs a new migration that alters both embedding columns.

## Learning loop

At the end of a project the Release Manager pass writes `lesson` and `gotcha`
memories back to the topic (Phase 4). That is what makes the second project on a
topic cheaper than the first.
