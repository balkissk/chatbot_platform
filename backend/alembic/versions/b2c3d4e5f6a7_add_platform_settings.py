"""add platform settings

Revision ID: b2c3d4e5f6a7
Revises: a1f2c3d4e5b6
Create Date: 2026-07-15 00:00:00.000000

"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1f2c3d4e5b6"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_table(
        "platform_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("platform_name", sa.String(length=80), nullable=False),
        sa.Column("support_email", sa.String(length=255), nullable=False),
        sa.Column("default_page_size", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_platform_settings_updated_by"), "platform_settings", ["updated_by"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_platform_settings_updated_by"), table_name="platform_settings")
    op.drop_table("platform_settings")
