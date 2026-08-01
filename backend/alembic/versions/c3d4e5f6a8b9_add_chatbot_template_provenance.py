"""add chatbot template provenance

Revision ID: c3d4e5f6a8b9
Revises: b2c3d4e5f6a7
Create Date: 2026-07-15 00:00:00.000000

"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6a8b9"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column("chatbots", sa.Column("source_template_key", sa.String(), nullable=True))
    op.add_column("chatbots", sa.Column("source_template_version", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("chatbots", "source_template_version")
    op.drop_column("chatbots", "source_template_key")
