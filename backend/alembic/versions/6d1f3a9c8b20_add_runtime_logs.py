"""add runtime logs

Revision ID: 6d1f3a9c8b20
Revises: 3c5d7e9f1021
Create Date: 2026-07-11 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6d1f3a9c8b20"
down_revision: Union[str, None] = "3c5d7e9f1021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "runtime_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chatbot_id", sa.Integer(), nullable=True),
        sa.Column("version_id", sa.Integer(), nullable=True),
        sa.Column("conversation_id", sa.Integer(), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("rag_used", sa.Boolean(), nullable=False),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column("error_type", sa.String(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["chatbot_id"], ["chatbots.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversation_sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["version_id"], ["versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_runtime_logs_channel"), "runtime_logs", ["channel"], unique=False)
    op.create_index(op.f("ix_runtime_logs_chatbot_id"), "runtime_logs", ["chatbot_id"], unique=False)
    op.create_index(op.f("ix_runtime_logs_created_at"), "runtime_logs", ["created_at"], unique=False)
    op.create_index(op.f("ix_runtime_logs_project_id"), "runtime_logs", ["project_id"], unique=False)
    op.create_index(op.f("ix_runtime_logs_status"), "runtime_logs", ["status"], unique=False)
    op.create_index(op.f("ix_runtime_logs_user_id"), "runtime_logs", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_runtime_logs_user_id"), table_name="runtime_logs")
    op.drop_index(op.f("ix_runtime_logs_status"), table_name="runtime_logs")
    op.drop_index(op.f("ix_runtime_logs_project_id"), table_name="runtime_logs")
    op.drop_index(op.f("ix_runtime_logs_created_at"), table_name="runtime_logs")
    op.drop_index(op.f("ix_runtime_logs_chatbot_id"), table_name="runtime_logs")
    op.drop_index(op.f("ix_runtime_logs_channel"), table_name="runtime_logs")
    op.drop_table("runtime_logs")
