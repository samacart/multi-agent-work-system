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

Retrieval (Phase 2) combines:

- semantic similarity (pgvector cosine distance on `embedding`)
- recency (`created_at` / `updated_at`)
- importance (`importance`)
- source reliability (`sources.metadata_json`)
- topic/project match

Embeddings are `VECTOR(1536)` — `text-embedding-3-small`, set by
`EMBEDDING_MODEL` / `EMBEDDING_DIM`. The dimension is pinned in migration
`0001`; changing it needs a new migration that alters both embedding columns.

## Learning loop

At the end of a project the Release Manager pass writes `lesson` and `gotcha`
memories back to the topic (Phase 4). That is what makes the second project on a
topic cheaper than the first.
