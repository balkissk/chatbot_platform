"""add chatbot rag settings

Revision ID: f2c8a1b6d904
Revises: e7a3c9d4b802
Create Date: 2026-05-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2c8a1b6d904"
down_revision: Union[str, Sequence[str], None] = "e7a3c9d4b802"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("chatbots", sa.Column("rag_settings", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("chatbots", "rag_settings")
