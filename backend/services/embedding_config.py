import os
from collections.abc import Sequence


DEFAULT_EMBEDDING_DIMENSIONS = 1536
EMBEDDING_DIMENSIONS_ENV = "EMBEDDING_DIMENSIONS"

EMBEDDING_MODEL_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-ada-002": 1536,
    "text-embedding-3-large": 3072,
}


def expected_embedding_dimensions() -> int:
    configured = os.getenv(EMBEDDING_DIMENSIONS_ENV) or os.getenv("AZURE_OPENAI_EMBEDDING_DIMENSIONS")
    if configured:
        try:
            value = int(configured)
        except ValueError as exc:
            raise ValueError(f"{EMBEDDING_DIMENSIONS_ENV} must be an integer") from exc
        if value <= 0:
            raise ValueError(f"{EMBEDDING_DIMENSIONS_ENV} must be positive")
        return value

    deployment = (
        os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
        or os.getenv("EMBEDDING_MODEL")
        or "text-embedding-3-small"
    ).strip()
    return EMBEDDING_MODEL_DIMENSIONS.get(deployment, DEFAULT_EMBEDDING_DIMENSIONS)


def validate_embedding_vector(vector: Sequence[float] | None) -> int:
    if vector is None:
        raise ValueError("Embedding vector is missing")

    expected = expected_embedding_dimensions()
    actual = len(vector)
    if actual != expected:
        raise ValueError(f"Embedding dimension mismatch: expected {expected}, got {actual}")
    return expected


def pgvector_literal(vector: Sequence[float] | None) -> str:
    validate_embedding_vector(vector)
    values = []
    for value in vector or []:
        values.append(format(float(value), ".10g"))
    return f"[{','.join(values)}]"
