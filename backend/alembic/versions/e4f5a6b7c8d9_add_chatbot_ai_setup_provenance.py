"""add chatbot ai setup provenance

Revision ID: e4f5a6b7c8d9
Revises: d7e8f9a0b1c2
Create Date: 2026-07-28 00:00:00.000000

"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, None] = "d7e8f9a0b1c2"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column("chatbots", sa.Column("ai_assistant_goal", sa.String(), nullable=True))
    op.add_column("chatbots", sa.Column("ai_business_context", sa.String(), nullable=True))
    op.add_column("chatbots", sa.Column("ai_knowledge_base_description", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("chatbots", "ai_knowledge_base_description")
    op.drop_column("chatbots", "ai_business_context")
    op.drop_column("chatbots", "ai_assistant_goal")
