"""fix llm config types

Revision ID: efa0166ae968
Revises: f2c8a1b6d904
Create Date: 2026-04-01 03:47:28.081592

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = 'efa0166ae968'
down_revision: Union[str, Sequence[str], None] = 'f2c8a1b6d904'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
