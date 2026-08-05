"""add version smoke tests

Revision ID: 7a2c4e8f9012
Revises: 6f1a9d2b3c45
Create Date: 2026-08-05 00:00:00.000000

"""
from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "7a2c4e8f9012"
down_revision: Union[str, None] = "6f1a9d2b3c45"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_table(
        "version_smoke_tests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version_id", sa.Integer(), sa.ForeignKey("versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chatbot_id", sa.Integer(), sa.ForeignKey("chatbots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tested_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("test_mode", sa.String(), nullable=False, server_default="auto"),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("failure_category", sa.String(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("trace", sa.JSON(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_version_smoke_tests_version_id", "version_smoke_tests", ["version_id"])
    op.create_index("ix_version_smoke_tests_chatbot_id", "version_smoke_tests", ["chatbot_id"])
    op.create_index("ix_version_smoke_tests_tested_by", "version_smoke_tests", ["tested_by"])
    op.create_index("ix_version_smoke_tests_status", "version_smoke_tests", ["status"])
    op.create_index("ix_version_smoke_tests_failure_category", "version_smoke_tests", ["failure_category"])
    op.create_index("ix_version_smoke_tests_created_at", "version_smoke_tests", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_version_smoke_tests_created_at", table_name="version_smoke_tests")
    op.drop_index("ix_version_smoke_tests_failure_category", table_name="version_smoke_tests")
    op.drop_index("ix_version_smoke_tests_status", table_name="version_smoke_tests")
    op.drop_index("ix_version_smoke_tests_tested_by", table_name="version_smoke_tests")
    op.drop_index("ix_version_smoke_tests_chatbot_id", table_name="version_smoke_tests")
    op.drop_index("ix_version_smoke_tests_version_id", table_name="version_smoke_tests")
    op.drop_table("version_smoke_tests")
