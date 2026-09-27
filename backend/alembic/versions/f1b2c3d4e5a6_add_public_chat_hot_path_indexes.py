"""add public chat hot path indexes

Revision ID: f1b2c3d4e5a6
Revises: e2b7c4d9a615
Create Date: 2026-09-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "f1b2c3d4e5a6"
down_revision: Union[str, Sequence[str], None] = "e2b7c4d9a615"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_flow_nodes_flow_node_key",
        "flow_nodes",
        ["flow_id", "node_key"],
    )
    op.create_index(
        "ix_flow_transitions_flow_source",
        "flow_transitions",
        ["flow_id", "source_node_key"],
    )
    op.create_index(
        "ix_conversation_sessions_public_lookup",
        "conversation_sessions",
        ["id", "chatbot_id", "user_id"],
    )
    op.create_index(
        "ix_conversation_messages_session_id_id",
        "conversation_messages",
        ["session_id", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_conversation_messages_session_id_id", table_name="conversation_messages")
    op.drop_index("ix_conversation_sessions_public_lookup", table_name="conversation_sessions")
    op.drop_index("ix_flow_transitions_flow_source", table_name="flow_transitions")
    op.drop_index("ix_flow_nodes_flow_node_key", table_name="flow_nodes")
