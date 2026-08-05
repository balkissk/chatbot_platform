"""add runtime observability fields

Revision ID: 8d1e5f7a9034
Revises: 7a2c4e8f9012
Create Date: 2026-08-05 00:00:00.000000

"""
from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "8d1e5f7a9034"
down_revision: Union[str, None] = "7a2c4e8f9012"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column("runtime_logs", sa.Column("execution_id", sa.String(), nullable=True))
    op.add_column("runtime_logs", sa.Column("execution_mode", sa.String(), nullable=True))
    op.add_column("runtime_logs", sa.Column("failure_category", sa.String(), nullable=True))
    op.add_column("runtime_logs", sa.Column("current_block", sa.String(), nullable=True))
    op.add_column("runtime_logs", sa.Column("retrieval_count", sa.Integer(), nullable=True))
    op.add_column("runtime_logs", sa.Column("provider", sa.String(), nullable=True))
    op.create_index("ix_runtime_logs_execution_id", "runtime_logs", ["execution_id"])
    op.create_index("ix_runtime_logs_execution_mode", "runtime_logs", ["execution_mode"])
    op.create_index("ix_runtime_logs_failure_category", "runtime_logs", ["failure_category"])


def downgrade() -> None:
    op.drop_index("ix_runtime_logs_failure_category", table_name="runtime_logs")
    op.drop_index("ix_runtime_logs_execution_mode", table_name="runtime_logs")
    op.drop_index("ix_runtime_logs_execution_id", table_name="runtime_logs")
    op.drop_column("runtime_logs", "provider")
    op.drop_column("runtime_logs", "retrieval_count")
    op.drop_column("runtime_logs", "current_block")
    op.drop_column("runtime_logs", "failure_category")
    op.drop_column("runtime_logs", "execution_mode")
    op.drop_column("runtime_logs", "execution_id")
