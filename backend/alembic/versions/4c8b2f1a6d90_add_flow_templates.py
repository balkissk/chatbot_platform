"""add flow templates

Revision ID: 4c8b2f1a6d90
Revises: f7b8c9d0e1f2
Create Date: 2026-08-04 00:00:00.000000

"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "4c8b2f1a6d90"
down_revision: Union[str, None] = "f7b8c9d0e1f2"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_table(
        "flow_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("purpose", sa.String(), nullable=True),
        sa.Column("is_exposed", sa.Boolean(), nullable=True, server_default=sa.false()),
        sa.Column("is_shared", sa.Boolean(), nullable=True, server_default=sa.false()),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("source_flow_id", sa.Integer(), sa.ForeignKey("flows.id"), nullable=True),
        sa.Column("nodes", sa.JSON(), nullable=True),
        sa.Column("transitions", sa.JSON(), nullable=True),
        sa.Column("test_scenarios", sa.JSON(), nullable=True),
        sa.Column("current_revision_number", sa.Integer(), nullable=True, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_flow_templates_key", "flow_templates", ["key"], unique=True)
    op.create_index("ix_flow_templates_owner_id", "flow_templates", ["owner_id"])
    op.create_index("ix_flow_templates_purpose", "flow_templates", ["purpose"])
    op.create_table(
        "flow_template_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("flow_templates.id"), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("purpose", sa.String(), nullable=True),
        sa.Column("nodes", sa.JSON(), nullable=True),
        sa.Column("transitions", sa.JSON(), nullable=True),
        sa.Column("test_scenarios", sa.JSON(), nullable=True),
        sa.Column("change_note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_flow_template_revisions_template_id", "flow_template_revisions", ["template_id"])
    op.create_unique_constraint(
        "uq_flow_template_revision_number",
        "flow_template_revisions",
        ["template_id", "revision_number"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_flow_template_revision_number", "flow_template_revisions", type_="unique")
    op.drop_index("ix_flow_template_revisions_template_id", table_name="flow_template_revisions")
    op.drop_table("flow_template_revisions")
    op.drop_index("ix_flow_templates_purpose", table_name="flow_templates")
    op.drop_index("ix_flow_templates_owner_id", table_name="flow_templates")
    op.drop_index("ix_flow_templates_key", table_name="flow_templates")
    op.drop_table("flow_templates")
