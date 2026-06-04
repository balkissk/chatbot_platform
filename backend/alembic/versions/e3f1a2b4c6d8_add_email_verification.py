"""add email verification

Revision ID: e3f1a2b4c6d8
Revises: d2a7a8c53301
Create Date: 2026-05-14 19:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e3f1a2b4c6d8'
down_revision: Union[str, Sequence[str], None] = 'd2a7a8c53301'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('email_verified_at', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('email_verification_token', sa.String(), nullable=True))
    op.add_column('users', sa.Column('email_verification_expires_at', sa.DateTime(), nullable=True))
    op.create_index(
        op.f('ix_users_email_verification_token'),
        'users',
        ['email_verification_token'],
        unique=False
    )
    op.execute("UPDATE users SET email_verified_at = NOW() WHERE email_verified_at IS NULL")


def downgrade() -> None:
    op.drop_index(op.f('ix_users_email_verification_token'), table_name='users')
    op.drop_column('users', 'email_verification_expires_at')
    op.drop_column('users', 'email_verification_token')
    op.drop_column('users', 'email_verified_at')
