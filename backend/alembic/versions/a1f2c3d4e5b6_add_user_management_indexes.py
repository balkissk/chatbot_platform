"""add user management indexes

Revision ID: a1f2c3d4e5b6
Revises: 9c2d4e6f8a10
Create Date: 2026-07-14 00:00:00.000000

"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1f2c3d4e5b6"
down_revision: Union[str, None] = "9c2d4e6f8a10"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(), nullable=True))
    op.create_index(op.f("ix_users_role"), "users", ["role"], unique=False)
    op.create_index(op.f("ix_users_status"), "users", ["status"], unique=False)
    op.create_index(op.f("ix_users_created_at"), "users", ["created_at"], unique=False)
    op.create_index(op.f("ix_users_last_login_at"), "users", ["last_login_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_last_login_at"), table_name="users")
    op.drop_index(op.f("ix_users_created_at"), table_name="users")
    op.drop_index(op.f("ix_users_status"), table_name="users")
    op.drop_index(op.f("ix_users_role"), table_name="users")
    op.drop_column("users", "last_login_at")
