"""add password reset fields

Revision ID: b8e6a2f4c913
Revises: a4f2d8c7e105
Create Date: 2026-08-14 00:00:00.000000

"""
from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "b8e6a2f4c913"
down_revision: Union[str, None] = "a4f2d8c7e105"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_reset_token", sa.String(), nullable=True))
    op.add_column("users", sa.Column("password_reset_expires_at", sa.DateTime(), nullable=True))
    op.create_index(op.f("ix_users_password_reset_token"), "users", ["password_reset_token"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_password_reset_token"), table_name="users")
    op.drop_column("users", "password_reset_expires_at")
    op.drop_column("users", "password_reset_token")
