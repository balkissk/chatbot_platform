from sqlalchemy.types import UserDefinedType

from services.embedding_config import expected_embedding_dimensions, pgvector_literal


class PgVector(UserDefinedType):
    cache_ok = True

    def __init__(self, dimensions: int | None = None):
        self.dimensions = dimensions or expected_embedding_dimensions()

    def get_col_spec(self, **kw) -> str:
        return f"VECTOR({self.dimensions})"

    def bind_processor(self, dialect):
        def process(value):
            if value is None or isinstance(value, str):
                return value
            return pgvector_literal(value)

        return process
