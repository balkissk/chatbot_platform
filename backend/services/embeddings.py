import os

import requests


EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "ollama").strip().lower()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
AZURE_OPENAI_EMBEDDING_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")


class EmbeddingError(Exception):
    pass


def embedding_model_name() -> str:
    if EMBEDDING_PROVIDER == "azure_openai":
        return AZURE_OPENAI_EMBEDDING_DEPLOYMENT
    return EMBEDDING_MODEL


def generate_ollama_embedding(value: str) -> list[float]:
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


def generate_azure_openai_embedding(value: str) -> list[float]:
    if not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_API_KEY:
        raise EmbeddingError("Azure OpenAI endpoint and API key must be configured")

    try:
        from openai import AzureOpenAI
    except ImportError as exc:
        raise EmbeddingError("openai package is required for Azure OpenAI embeddings") from exc

    try:
        response = AzureOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_API_KEY,
            api_version=AZURE_OPENAI_API_VERSION
        ).embeddings.create(
            model=AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
            input=value
        )
    except Exception as exc:
        raise EmbeddingError(str(exc)) from exc

    embedding = response.data[0].embedding if response.data else None
    if not isinstance(embedding, list) or not embedding:
        raise EmbeddingError("Embedding provider returned no vector")

    return [float(item) for item in embedding]


def generate_embedding(text: str) -> list[float]:
    value = (text or "").strip()
    if not value:
        raise EmbeddingError("Cannot embed empty text")

    if EMBEDDING_PROVIDER == "ollama":
        return generate_ollama_embedding(value)

    if EMBEDDING_PROVIDER == "azure_openai":
        return generate_azure_openai_embedding(value)

    raise EmbeddingError(f"Unsupported embedding provider: {EMBEDDING_PROVIDER}")
