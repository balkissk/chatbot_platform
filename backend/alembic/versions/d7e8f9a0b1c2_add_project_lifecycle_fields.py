"""add project lifecycle fields

Revision ID: d7e8f9a0b1c2
Revises: c3d4e5f6a8b9
Create Date: 2026-07-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d7e8f9a0b1c2"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("status", sa.String(), nullable=True))
    op.add_column("projects", sa.Column("archived_at", sa.DateTime(), nullable=True))
    op.add_column("projects", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.execute("UPDATE projects SET status = 'active' WHERE status IS NULL")
    op.alter_column("projects", "status", existing_type=sa.String(), nullable=False)
    op.create_index("ix_projects_status", "projects", ["status"], unique=False)
    op.create_index("ix_projects_deleted_at", "projects", ["deleted_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_projects_deleted_at", table_name="projects")
    op.drop_index("ix_projects_status", table_name="projects")
    op.drop_column("projects", "deleted_at")
    op.drop_column("projects", "archived_at")
    op.drop_column("projects", "status")
