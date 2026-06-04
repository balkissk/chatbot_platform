"""add versioning metadata

Revision ID: f4b7d9e2a104
Revises: e5a9d8c4f101
Create Date: 2026-05-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4b7d9e2a104"
down_revision: Union[str, Sequence[str], None] = "e5a9d8c4f101"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("versions", sa.Column("published_at", sa.DateTime(), nullable=True))
    op.add_column("versions", sa.Column("archived_at", sa.DateTime(), nullable=True))
    op.add_column("versions", sa.Column("created_by", sa.Integer(), nullable=True))
    op.add_column("versions", sa.Column("published_by", sa.Integer(), nullable=True))
    op.add_column("versions", sa.Column("archived_by", sa.Integer(), nullable=True))
    op.add_column("versions", sa.Column("duplicated_from_version_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_versions_created_by_users", "versions", "users", ["created_by"], ["id"])
    op.create_foreign_key("fk_versions_published_by_users", "versions", "users", ["published_by"], ["id"])
    op.create_foreign_key("fk_versions_archived_by_users", "versions", "users", ["archived_by"], ["id"])
    op.create_foreign_key(
        "fk_versions_duplicated_from_versions",
        "versions",
        "versions",
        ["duplicated_from_version_id"],
        ["id"],
    )

    op.add_column("chatbots", sa.Column("active_version_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_chatbots_active_version", "chatbots", "versions", ["active_version_id"], ["id"])

    op.execute(
        """
        UPDATE chatbots
        SET active_version_id = published_versions.id
        FROM (
            SELECT DISTINCT ON (chatbot_id) id, chatbot_id
            FROM versions
            WHERE status = 'published'
            ORDER BY chatbot_id, version_number DESC
        ) AS published_versions
        WHERE chatbots.id = published_versions.chatbot_id
        """
    )


def downgrade() -> None:
    op.drop_constraint("fk_chatbots_active_version", "chatbots", type_="foreignkey")
    op.drop_column("chatbots", "active_version_id")

    op.drop_constraint("fk_versions_duplicated_from_versions", "versions", type_="foreignkey")
    op.drop_constraint("fk_versions_archived_by_users", "versions", type_="foreignkey")
    op.drop_constraint("fk_versions_published_by_users", "versions", type_="foreignkey")
    op.drop_constraint("fk_versions_created_by_users", "versions", type_="foreignkey")
    op.drop_column("versions", "duplicated_from_version_id")
    op.drop_column("versions", "archived_by")
    op.drop_column("versions", "published_by")
    op.drop_column("versions", "created_by")
    op.drop_column("versions", "archived_at")
    op.drop_column("versions", "published_at")
