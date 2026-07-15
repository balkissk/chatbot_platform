"""add channel logs

Revision ID: 3c5d7e9f1021
Revises: 2b4c6d8e0f12
Create Date: 2026-06-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3c5d7e9f1021"
down_revision: Union[str, Sequence[str], None] = "2b4c6d8e0f12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "channel_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chatbot_id", sa.Integer(), nullable=False),
        sa.Column("channel_type", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("message", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="info"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["chatbot_id"], ["chatbots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_channel_logs_chatbot_id", "channel_logs", ["chatbot_id"])
    op.create_index("ix_channel_logs_channel_type", "channel_logs", ["channel_type"])
    op.create_index("ix_channel_logs_event_type", "channel_logs", ["event_type"])
    op.create_index("ix_channel_logs_created_at", "channel_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_channel_logs_created_at", table_name="channel_logs")
    op.drop_index("ix_channel_logs_event_type", table_name="channel_logs")
    op.drop_index("ix_channel_logs_channel_type", table_name="channel_logs")
    op.drop_index("ix_channel_logs_chatbot_id", table_name="channel_logs")
    op.drop_table("channel_logs")
