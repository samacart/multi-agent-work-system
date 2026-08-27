"""Add tasks.metadata_json

Task dependencies (and later, the run that produced a task) need somewhere to
live that is not `evidence` - that column belongs to QA verification.

Revision ID: 0003_task_metadata
Revises: 0002_vector_indexes
Create Date: 2026-08-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003_task_metadata"
down_revision: Union[str, None] = "0002_vector_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("metadata_json", JSON_TYPE, nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    op.drop_column("tasks", "metadata_json")
