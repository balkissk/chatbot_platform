"""add evaluation case turns

Revision ID: a4f2d8c7e105
Revises: 9e3b6c1d2045
Create Date: 2026-08-05 00:00:00.000000

"""
from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "a4f2d8c7e105"
down_revision: Union[str, None] = "9e3b6c1d2045"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column("evaluation_cases", sa.Column("turns", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("evaluation_cases", "turns")
