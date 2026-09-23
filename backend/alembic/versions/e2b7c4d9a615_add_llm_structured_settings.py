"""add llm structured settings

Revision ID: e2b7c4d9a615
Revises: d4f6a8b2c901
Create Date: 2026-09-22 21:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2b7c4d9a615"
down_revision: Union[str, Sequence[str], None] = "d4f6a8b2c901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("llm_configs", sa.Column("tone", sa.String(), nullable=True))
    op.add_column("llm_configs", sa.Column("language", sa.String(), nullable=True))
    op.add_column("llm_configs", sa.Column("response_style", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("llm_configs", "response_style")
    op.drop_column("llm_configs", "language")
    op.drop_column("llm_configs", "tone")
