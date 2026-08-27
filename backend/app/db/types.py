"""Portable column types.

The production database is Postgres + pgvector. The default test suite runs on
SQLite so it needs no services, so embedding columns fall back to JSON there.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator

# JSON everywhere, JSONB on Postgres.
JSONType = sa.JSON().with_variant(JSONB, "postgresql")


class Embedding(TypeDecorator):
    """Vector(dim) on Postgres, JSON list elsewhere."""

    impl = sa.JSON
    cache_ok = True

    def __init__(self, dim: int = 1536) -> None:
        self.dim = dim
        super().__init__()

    def load_dialect_impl(self, dialect):  # noqa: ANN001, ANN201
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector

            return dialect.type_descriptor(Vector(self.dim))
        return dialect.type_descriptor(sa.JSON())

    def process_bind_param(self, value, dialect):  # noqa: ANN001, ANN201
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        return list(value)

    def process_result_value(self, value, dialect):  # noqa: ANN001, ANN201
        if value is None:
            return None
        return list(value)
