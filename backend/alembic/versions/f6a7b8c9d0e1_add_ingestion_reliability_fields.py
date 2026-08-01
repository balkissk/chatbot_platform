"""add ingestion reliability fields

Revision ID: f6a7b8c9d0e1
Revises: e4f5a6b7c8d9
Create Date: 2026-07-29 00:00:00.000000

"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e4f5a6b7c8d9"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("content_hash", sa.String(), nullable=True))
    op.create_index("ix_documents_content_hash", "documents", ["content_hash"], unique=False)
    op.create_index(
        "ix_documents_knowledge_base_content_hash",
        "documents",
        ["knowledge_base_id", "content_hash"],
        unique=False,
    )

    op.add_column("chunks", sa.Column("retry_count", sa.Integer(), nullable=True))
    op.add_column("chunks", sa.Column("last_error", sa.Text(), nullable=True))
    op.add_column("chunks", sa.Column("last_attempt_at", sa.DateTime(), nullable=True))
    op.add_column("chunks", sa.Column("embedded_at", sa.DateTime(), nullable=True))
    op.execute("UPDATE chunks SET retry_count = 0 WHERE retry_count IS NULL")
    op.alter_column("chunks", "retry_count", existing_type=sa.Integer(), nullable=False)
    op.execute("UPDATE chunks SET last_error = embedding_error WHERE last_error IS NULL AND embedding_error IS NOT NULL")
    op.execute("UPDATE chunks SET embedded_at = CURRENT_TIMESTAMP WHERE embedded_at IS NULL AND embedding_status = 'ready' AND embedding IS NOT NULL")
    op.create_index("ix_chunks_embedding_status", "chunks", ["embedding_status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_chunks_embedding_status", table_name="chunks")
    op.drop_column("chunks", "embedded_at")
    op.drop_column("chunks", "last_attempt_at")
    op.drop_column("chunks", "last_error")
    op.drop_column("chunks", "retry_count")
    op.drop_index("ix_documents_knowledge_base_content_hash", table_name="documents")
    op.drop_index("ix_documents_content_hash", table_name="documents")
    op.drop_column("documents", "content_hash")
