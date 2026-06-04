"""add chunk metadata

Revision ID: e7a3c9d4b802
Revises: d5f7a9c2e601
Create Date: 2026-05-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7a3c9d4b802"
down_revision: Union[str, Sequence[str], None] = "d5f7a9c2e601"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("chunks", sa.Column("title", sa.String(), nullable=True))
    op.add_column("chunks", sa.Column("section_type", sa.String(), nullable=True))
    op.add_column("chunks", sa.Column("metadata_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("chunks", "metadata_json")
    op.drop_column("chunks", "section_type")
    op.drop_column("chunks", "title")
