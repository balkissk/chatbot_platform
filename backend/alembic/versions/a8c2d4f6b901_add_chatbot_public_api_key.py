"""add chatbot public api key

Revision ID: a8c2d4f6b901
Revises: f4b7d9e2a104
Create Date: 2026-05-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a8c2d4f6b901"
down_revision: Union[str, Sequence[str], None] = "f4b7d9e2a104"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("chatbots", sa.Column("public_api_key", sa.String(), nullable=True))
    op.add_column("chatbots", sa.Column("public_api_enabled", sa.Boolean(), nullable=True))
    op.create_index(op.f("ix_chatbots_public_api_key"), "chatbots", ["public_api_key"], unique=False)
    op.execute("UPDATE chatbots SET public_api_enabled = TRUE WHERE public_api_enabled IS NULL")


def downgrade() -> None:
    op.drop_index(op.f("ix_chatbots_public_api_key"), table_name="chatbots")
    op.drop_column("chatbots", "public_api_enabled")
    op.drop_column("chatbots", "public_api_key")
