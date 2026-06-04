"""add document metadata

Revision ID: b9d1e6f3a502
Revises: a8c2d4f6b901
Create Date: 2026-05-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b9d1e6f3a502"
down_revision: Union[str, Sequence[str], None] = "a8c2d4f6b901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("size_bytes", sa.Integer(), nullable=True))
    op.add_column("documents", sa.Column("status", sa.String(), nullable=True))
    op.add_column("documents", sa.Column("error_message", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("processed_at", sa.DateTime(), nullable=True))
    op.add_column("documents", sa.Column("chunks_count", sa.Integer(), nullable=True))
    op.execute("UPDATE documents SET size_bytes = 0 WHERE size_bytes IS NULL")
    op.execute("UPDATE documents SET status = 'processed' WHERE status IS NULL")
    op.execute("UPDATE documents SET processed_at = created_at WHERE processed_at IS NULL")
    op.execute(
        """
        UPDATE documents
        SET chunks_count = chunk_counts.count_value
        FROM (
            SELECT document_id, COUNT(*) AS count_value
            FROM chunks
            GROUP BY document_id
        ) AS chunk_counts
        WHERE documents.id = chunk_counts.document_id
        """
    )
    op.execute("UPDATE documents SET chunks_count = 0 WHERE chunks_count IS NULL")


def downgrade() -> None:
    op.drop_column("documents", "chunks_count")
    op.drop_column("documents", "processed_at")
    op.drop_column("documents", "error_message")
    op.drop_column("documents", "status")
    op.drop_column("documents", "size_bytes")
