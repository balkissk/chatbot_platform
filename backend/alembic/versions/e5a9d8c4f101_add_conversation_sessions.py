"""add conversation sessions

Revision ID: e5a9d8c4f101
Revises: e3f1a2b4c6d8
Create Date: 2026-05-14 21:05:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e5a9d8c4f101"
down_revision: Union[str, None] = "e3f1a2b4c6d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversation_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chatbot_id", sa.Integer(), nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("current_node_key", sa.String(), nullable=True),
        sa.Column("variables", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["chatbot_id"], ["chatbots.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["version_id"], ["versions.id"]),
        sa.PrimaryKeyConstraint("id")
    )
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("sources", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["conversation_sessions.id"]),
        sa.PrimaryKeyConstraint("id")
    )


def downgrade() -> None:
    op.drop_table("conversation_messages")
    op.drop_table("conversation_sessions")
