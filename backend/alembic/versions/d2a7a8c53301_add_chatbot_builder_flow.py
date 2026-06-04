"""add chatbot builder flow

Revision ID: d2a7a8c53301
Revises: c7a98a4e63d2
Create Date: 2026-05-04 15:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd2a7a8c53301'
down_revision: Union[str, Sequence[str], None] = 'c7a98a4e63d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('chatbots', sa.Column('description', sa.String(), nullable=True))
    op.add_column('chatbots', sa.Column('purpose', sa.String(), nullable=True))
    op.add_column('chatbots', sa.Column('mode', sa.String(), nullable=True))
    op.add_column('chatbots', sa.Column('channel', sa.String(), nullable=True))
    op.add_column('chatbots', sa.Column('build_method', sa.String(), nullable=True))
    op.add_column('chatbots', sa.Column('template_key', sa.String(), nullable=True))

    op.create_table(
        'flows',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('version_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['version_id'], ['versions.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('version_id')
    )
    op.create_table(
        'flow_nodes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('flow_id', sa.Integer(), nullable=True),
        sa.Column('node_key', sa.String(), nullable=True),
        sa.Column('type', sa.String(), nullable=True),
        sa.Column('label', sa.String(), nullable=True),
        sa.Column('config', sa.JSON(), nullable=True),
        sa.Column('position_x', sa.Integer(), nullable=True),
        sa.Column('position_y', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['flow_id'], ['flows.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table(
        'flow_transitions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('flow_id', sa.Integer(), nullable=True),
        sa.Column('source_node_key', sa.String(), nullable=True),
        sa.Column('target_node_key', sa.String(), nullable=True),
        sa.Column('label', sa.String(), nullable=True),
        sa.Column('condition', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['flow_id'], ['flows.id']),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('flow_transitions')
    op.drop_table('flow_nodes')
    op.drop_table('flows')
    op.drop_column('chatbots', 'template_key')
    op.drop_column('chatbots', 'build_method')
    op.drop_column('chatbots', 'channel')
    op.drop_column('chatbots', 'mode')
    op.drop_column('chatbots', 'purpose')
    op.drop_column('chatbots', 'description')
