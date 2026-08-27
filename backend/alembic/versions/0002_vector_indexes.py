"""pgvector HNSW indexes for cosine search

Without these, every memory search is a sequential scan. HNSW is the right
default here: better recall/latency than IVFFlat and no training step, which
matters because these tables start empty.

Revision ID: 0002_vector_indexes
Revises: 4d521d518ee2
Create Date: 2026-08-27
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002_vector_indexes"
down_revision: Union[str, None] = "4d521d518ee2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_memories_embedding_hnsw "
        "ON memories USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_source_chunks_embedding_hnsw "
        "ON source_chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_source_chunks_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_memories_embedding_hnsw")
