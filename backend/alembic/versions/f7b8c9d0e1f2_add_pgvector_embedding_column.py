"""add pgvector embedding column

Revision ID: f7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-29 00:00:00.000000

"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "f7b8c9d0e1f2"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

EMBEDDING_DIMENSIONS = 1536


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        op.add_column("chunks", sa.Column("embedding_vector", sa.Text(), nullable=True))
        return

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(f"ALTER TABLE chunks ADD COLUMN IF NOT EXISTS embedding_vector vector({EMBEDDING_DIMENSIONS})")

    op.execute(f"""
        UPDATE chunks
        SET embedding_vector = (
            '[' || (
                SELECT string_agg(value::text, ',' ORDER BY ord)
                FROM jsonb_array_elements_text(embedding::jsonb) WITH ORDINALITY AS item(value, ord)
            ) || ']'
        )::vector
        WHERE embedding IS NOT NULL
          AND jsonb_typeof(embedding::jsonb) = 'array'
          AND jsonb_array_length(embedding::jsonb) = {EMBEDDING_DIMENSIONS}
    """)

    op.execute(f"""
        UPDATE chunks
        SET embedding_status = 'failed',
            last_error = COALESCE(
                last_error,
                'Embedding dimension is incompatible with the configured vector index. Reprocess this chunk.'
            ),
            embedding_error = COALESCE(
                embedding_error,
                'Embedding dimension is incompatible with the configured vector index. Reprocess this chunk.'
            )
        WHERE embedding IS NOT NULL
          AND embedding_status = 'ready'
          AND (
              embedding_dimensions IS DISTINCT FROM {EMBEDDING_DIMENSIONS}
              OR jsonb_typeof(embedding::jsonb) <> 'array'
              OR jsonb_array_length(embedding::jsonb) <> {EMBEDDING_DIMENSIONS}
          )
    """)

    op.execute("""
        DO $$
        BEGIN
            CREATE INDEX IF NOT EXISTS ix_chunks_embedding_vector_hnsw
            ON chunks
            USING hnsw (embedding_vector vector_cosine_ops)
            WHERE embedding_vector IS NOT NULL AND embedding_status = 'ready';
        EXCEPTION
            WHEN undefined_object OR feature_not_supported THEN
                CREATE INDEX IF NOT EXISTS ix_chunks_embedding_vector_hnsw
                ON chunks
                USING ivfflat (embedding_vector vector_cosine_ops)
                WITH (lists = 100)
                WHERE embedding_vector IS NOT NULL AND embedding_status = 'ready';
        END
        $$;
    """)
    op.create_index(
        "ix_chunks_document_embedding_status",
        "chunks",
        ["document_id", "embedding_status"],
        unique=False,
    )
    op.create_index(
        "ix_documents_knowledge_base_status",
        "documents",
        ["knowledge_base_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_index("ix_documents_knowledge_base_status", table_name="documents")
        op.drop_index("ix_chunks_document_embedding_status", table_name="chunks")
        op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_vector_hnsw")
        op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS embedding_vector")
    else:
        op.drop_column("chunks", "embedding_vector")
