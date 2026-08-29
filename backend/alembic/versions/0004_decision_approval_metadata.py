"""Add metadata_json to decisions and approval_requests

Somewhere to keep the agent's own view of a decision it is handing over: the
options it considered and which it recommends, and for an approval gate, a
briefing on what is actually being approved.

Revision ID: 0004_decision_approval_metadata
Revises: 0003_task_metadata
Create Date: 2026-08-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004_decision_approval_metadata"
down_revision: Union[str, None] = "0003_task_metadata"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    for table in ("decisions", "approval_requests"):
        op.add_column(
            table,
            sa.Column("metadata_json", JSON_TYPE, nullable=False, server_default=sa.text("'{}'")),
        )


def downgrade() -> None:
    for table in ("decisions", "approval_requests"):
        op.drop_column(table, "metadata_json")
