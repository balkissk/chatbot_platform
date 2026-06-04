"""add chunk embeddings

Revision ID: c1e4f8a7b903
Revises: b9d1e6f3a502
Create Date: 2026-05-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c1e4f8a7b903"
down_revision: Union[str, Sequence[str], None] = "b9d1e6f3a502"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("chunks", sa.Column("embedding", sa.JSON(), nullable=True))
    op.add_column("chunks", sa.Column("embedding_model", sa.String(), nullable=True))
    op.add_column("chunks", sa.Column("embedding_status", sa.String(), nullable=True))
    op.add_column("chunks", sa.Column("embedding_error", sa.Text(), nullable=True))
    op.add_column("chunks", sa.Column("embedding_dimensions", sa.Integer(), nullable=True))
    op.add_column("chunks", sa.Column("retrieval_score", sa.Float(), nullable=True))
    op.execute("UPDATE chunks SET embedding_status = 'pending' WHERE embedding_status IS NULL")


def downgrade() -> None:
    op.drop_column("chunks", "retrieval_score")
    op.drop_column("chunks", "embedding_dimensions")
    op.drop_column("chunks", "embedding_error")
    op.drop_column("chunks", "embedding_status")
    op.drop_column("chunks", "embedding_model")
    op.drop_column("chunks", "embedding")
