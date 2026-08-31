"""Add projects.workspace_path

The repository a project's agents work in was global configuration, so pointing
them at a different directory meant editing .env and restarting the server, and
two projects could never target two repositories at once.

Revision ID: 0005_project_workspace
Revises: 0004_decision_approval_metadata
Create Date: 2026-08-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_project_workspace"
down_revision: Union[str, None] = "0004_decision_approval_metadata"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("workspace_path", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "workspace_path")
