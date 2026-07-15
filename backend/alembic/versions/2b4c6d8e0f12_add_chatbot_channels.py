"""add chatbot channels

Revision ID: 2b4c6d8e0f12
Revises: 1a2b3c4d5e6f
Create Date: 2026-06-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2b4c6d8e0f12"
down_revision: Union[str, Sequence[str], None] = "1a2b3c4d5e6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chatbot_channels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chatbot_id", sa.Integer(), nullable=False),
        sa.Column("channel_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="not_configured"),
        sa.Column("config_json", sa.JSON(), nullable=True, server_default=sa.text("'{}'::json")),
        sa.Column("deployed_version_id", sa.Integer(), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(), nullable=True),
        sa.Column("last_verification_at", sa.DateTime(), nullable=True),
        sa.Column("last_incoming_message_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["chatbot_id"], ["chatbots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["deployed_version_id"], ["versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chatbot_id", "channel_type", name="uq_chatbot_channels_chatbot_type"),
    )
    op.create_index("ix_chatbot_channels_chatbot_id", "chatbot_channels", ["chatbot_id"])
    op.create_index("ix_chatbot_channels_channel_type", "chatbot_channels", ["channel_type"])


def downgrade() -> None:
    op.drop_index("ix_chatbot_channels_channel_type", table_name="chatbot_channels")
    op.drop_index("ix_chatbot_channels_chatbot_id", table_name="chatbot_channels")
    op.drop_table("chatbot_channels")
