"""repair flow template current revision column

Revision ID: 6f1a9d2b3c45
Revises: 5d7e2c9a1b44
Create Date: 2026-08-04 00:00:00.000000

"""
from typing import Union

from alembic import op


revision: str = "6f1a9d2b3c45"
down_revision: Union[str, None] = "5d7e2c9a1b44"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE IF EXISTS flow_templates "
        "ADD COLUMN IF NOT EXISTS current_revision_number INTEGER DEFAULT 1"
    )


def downgrade() -> None:
    pass
