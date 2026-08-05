"""repair flow template schema drift

Revision ID: 5d7e2c9a1b44
Revises: 4c8b2f1a6d90
Create Date: 2026-08-04 00:00:00.000000

"""
from typing import Union

from alembic import op


revision: str = "5d7e2c9a1b44"
down_revision: Union[str, None] = "4c8b2f1a6d90"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS flow_templates ADD COLUMN IF NOT EXISTS test_scenarios JSON")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS flow_template_revisions (
            id SERIAL PRIMARY KEY,
            template_id INTEGER NOT NULL REFERENCES flow_templates(id),
            revision_number INTEGER NOT NULL,
            name VARCHAR NOT NULL,
            description TEXT,
            purpose VARCHAR,
            nodes JSON,
            transitions JSON,
            test_scenarios JSON,
            change_note TEXT,
            created_by INTEGER REFERENCES users(id),
            created_at TIMESTAMP WITHOUT TIME ZONE
        )
        """
    )
    op.execute("ALTER TABLE IF EXISTS flow_template_revisions ADD COLUMN IF NOT EXISTS test_scenarios JSON")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_flow_template_revisions_template_id "
        "ON flow_template_revisions (template_id)"
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'uq_flow_template_revision_number'
                  AND conrelid = 'flow_template_revisions'::regclass
            ) THEN
                ALTER TABLE flow_template_revisions
                ADD CONSTRAINT uq_flow_template_revision_number
                UNIQUE (template_id, revision_number);
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    pass
