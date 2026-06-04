"""add document raw text

Revision ID: d5f7a9c2e601
Revises: c1e4f8a7b903
Create Date: 2026-05-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d5f7a9c2e601"
down_revision: Union[str, Sequence[str], None] = "c1e4f8a7b903"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("raw_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "raw_text")
