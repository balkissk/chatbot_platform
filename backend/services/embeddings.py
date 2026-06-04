import os

import requests


EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "ollama")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")


class EmbeddingError(Exception):
    pass


def embedding_model_name() -> str:
    return EMBEDDING_MODEL


def generate_embedding(text: str) -> list[float]:
    value = (text or "").strip()
    if not value:
        raise EmbeddingError("Cannot embed empty text")

    if EMBEDDING_PROVIDER != "ollama":
        raise EmbeddingError(f"Unsupported embedding provider: {EMBEDDING_PROVIDER}")

    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/embeddings",
            json={
                "model": EMBEDDING_MODEL,
                "prompt": value
            },
            timeout=30
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise EmbeddingError(str(exc)) from exc

    body = response.json()
    embedding = body.get("embedding")
    if not isinstance(embedding, list) or not embedding:
        raise EmbeddingError("Embedding provider returned no vector")

    return [float(item) for item in embedding]
