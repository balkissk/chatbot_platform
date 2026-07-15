"""remove whatsapp and messenger channels

Revision ID: 9c2d4e6f8a10
Revises: 8b7e2c4d9a31
Create Date: 2026-07-14 00:00:00.000000

"""
from typing import Union

from alembic import op


revision: str = "9c2d4e6f8a10"
down_revision: Union[str, None] = "8b7e2c4d9a31"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.execute("DELETE FROM channel_logs WHERE channel_type IN ('whatsapp', 'messenger')")
    op.execute("DELETE FROM chatbot_channels WHERE channel_type IN ('whatsapp', 'messenger')")


def downgrade() -> None:
    # Removed product-scope integrations are not recreated on downgrade.
    pass
