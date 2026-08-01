import os
import logging
from dataclasses import dataclass
from http import HTTPStatus
from urllib.parse import urlparse

import requests

from config.settings import load_environment

load_environment()
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "ollama").strip().lower()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "")
AZURE_OPENAI_EMBEDDING_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "")
AZURE_OPENAI_TIMEOUT_SECONDS = float(os.getenv("AZURE_OPENAI_TIMEOUT_SECONDS", "60"))
AZURE_OPENAI_MAX_RETRIES = int(os.getenv("AZURE_OPENAI_MAX_RETRIES", "2"))
logger = logging.getLogger(__name__)
_azure_embedding_client_cache: dict[tuple[str, str, str, bool], object] = {}


class EmbeddingError(Exception):
    pass


@dataclass(frozen=True)
class AzureEmbeddingConfig:
    endpoint: str
    api_key: str
    deployment: str
    api_version: str

    @property
    def endpoint_host(self) -> str | None:
        return urlparse(self.endpoint).netloc or None

    @property
    def is_v1_endpoint(self) -> bool:
        return urlparse(self.endpoint).path.rstrip("/") == "/openai/v1"


def embedding_model_name() -> str:
    if EMBEDDING_PROVIDER == "azure_openai":
        try:
            return azure_embedding_config().deployment
        except EmbeddingError:
            return AZURE_OPENAI_EMBEDDING_DEPLOYMENT or "unconfigured"
    return EMBEDDING_MODEL


def azure_embedding_config() -> AzureEmbeddingConfig:
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", AZURE_OPENAI_ENDPOINT).strip().rstrip("/")
    api_key = os.getenv("AZURE_OPENAI_API_KEY", AZURE_OPENAI_API_KEY).strip()
    deployment = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", AZURE_OPENAI_EMBEDDING_DEPLOYMENT).strip()
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", AZURE_OPENAI_API_VERSION).strip()

    missing = [
        name
        for name, value in {
            "AZURE_OPENAI_ENDPOINT": endpoint,
            "AZURE_OPENAI_API_KEY": api_key,
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": deployment,
            "AZURE_OPENAI_API_VERSION": api_version,
        }.items()
        if not value
    ]
    if missing:
        raise EmbeddingError(f"Azure OpenAI embedding configuration is incomplete. Missing: {', '.join(missing)}")

    return AzureEmbeddingConfig(
        endpoint=endpoint,
        api_key=api_key,
        deployment=deployment,
        api_version=api_version,
    )


def validate_embedding_configuration() -> None:
    if EMBEDDING_PROVIDER == "azure_openai":
        azure_embedding_config()
        return
    if EMBEDDING_PROVIDER != "ollama":
        raise EmbeddingError(f"Unsupported embedding provider: {EMBEDDING_PROVIDER}")


def _redact_secret(value: str, secret: str | None) -> str:
    if secret:
        value = value.replace(secret, "[redacted]")
    return value


def _safe_embedding_error(
    exc: Exception,
    deployment: str,
    endpoint_host: str | None,
    api_version: str,
    api_key: str | None = None,
) -> str:
    status_code = getattr(exc, "status_code", None)
    code = getattr(exc, "code", None)
    message = _redact_secret(str(exc), api_key)

    if status_code == 401:
        reason = "authentication failed. Check AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT."
    elif status_code == 403:
        reason = "authorization failed. Check Azure OpenAI access, quota, and role/resource permissions."
    elif status_code == 404:
        reason = "embedding deployment was not found. Check AZURE_OPENAI_EMBEDDING_DEPLOYMENT."
    elif status_code == 429:
        reason = "rate limit or quota exceeded for the Azure OpenAI embedding deployment."
    elif "api-version" in message.lower() or "api version" in message.lower():
        reason = "API version incompatibility. Check AZURE_OPENAI_API_VERSION for embeddings."
    else:
        reason = "Azure OpenAI embedding request failed."

    status_label = f"{status_code} {HTTPStatus(status_code).phrase}" if isinstance(status_code, int) and status_code in HTTPStatus._value2member_map_ else status_code
    details = [
        f"Azure OpenAI embedding service error: {reason}",
        f"deployment={deployment}",
        f"api_version={api_version or 'v1'}",
    ]
    if endpoint_host:
        details.append(f"endpoint_host={endpoint_host}")
    if status_label:
        details.append(f"status={status_label}")
    if code:
        details.append(f"code={code}")
    if message:
        details.append(f"message={message[:500]}")
    return "; ".join(details)


def _azure_embedding_client(config: AzureEmbeddingConfig):
    try:
        from openai import AzureOpenAI, OpenAI
    except ImportError as exc:
        raise EmbeddingError("openai package is required for Azure OpenAI embeddings") from exc

    cache_key = (config.endpoint, config.api_key, config.api_version, config.is_v1_endpoint)
    if cache_key in _azure_embedding_client_cache:
        return _azure_embedding_client_cache[cache_key]

    if config.is_v1_endpoint:
        client = OpenAI(
            api_key=config.api_key,
            base_url=config.endpoint.rstrip("/") + "/",
            timeout=AZURE_OPENAI_TIMEOUT_SECONDS,
            max_retries=AZURE_OPENAI_MAX_RETRIES,
        )
        _azure_embedding_client_cache[cache_key] = client
        return client

    client = AzureOpenAI(
        azure_endpoint=config.endpoint,
        api_key=config.api_key,
        api_version=config.api_version,
        timeout=AZURE_OPENAI_TIMEOUT_SECONDS,
        max_retries=AZURE_OPENAI_MAX_RETRIES,
    )
    _azure_embedding_client_cache[cache_key] = client
    return client


def _log_embedding_failure(path: str, exc: Exception, config: AzureEmbeddingConfig) -> None:
    message = _redact_secret(str(exc), config.api_key)
    logger.warning(
        "Azure OpenAI embedding request failed path=%s status=%s code=%s deployment=%s api_version=%s endpoint_host=%s message=%s",
        path,
        getattr(exc, "status_code", None),
        getattr(exc, "code", None),
        config.deployment,
        config.api_version if not config.is_v1_endpoint else "v1",
        config.endpoint_host,
        message[:500],
    )


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
    config = azure_embedding_config()

    try:
        response = _azure_embedding_client(config).embeddings.create(
            model=config.deployment,
            input=value
        )
    except Exception as exc:
        _log_embedding_failure("/embeddings", exc, config)
        raise EmbeddingError(_safe_embedding_error(
            exc,
            config.deployment,
            config.endpoint_host,
            config.api_version if not config.is_v1_endpoint else "v1",
            config.api_key,
        )) from exc

    embedding = response.data[0].embedding if response.data else None
    if not isinstance(embedding, list) or not embedding:
        raise EmbeddingError("Embedding provider returned no vector")

    return [float(item) for item in embedding]


def generate_azure_openai_embeddings(values: list[str]) -> list[list[float]]:
    config = azure_embedding_config()
    clean_values = [(value or "").strip() for value in values]
    if any(not value for value in clean_values):
        raise EmbeddingError("Cannot embed empty text")

    try:
        response = _azure_embedding_client(config).embeddings.create(
            model=config.deployment,
            input=clean_values,
        )
    except Exception as exc:
        _log_embedding_failure("/embeddings", exc, config)
        raise EmbeddingError(_safe_embedding_error(
            exc,
            config.deployment,
            config.endpoint_host,
            config.api_version if not config.is_v1_endpoint else "v1",
            config.api_key,
        )) from exc

    embeddings = [item.embedding for item in sorted(response.data, key=lambda item: item.index)]
    if len(embeddings) != len(clean_values) or any(not isinstance(item, list) or not item for item in embeddings):
        raise EmbeddingError("Embedding provider returned an incomplete vector batch")
    return [[float(value) for value in item] for item in embeddings]


def generate_embedding(text: str) -> list[float]:
    value = (text or "").strip()
    if not value:
        raise EmbeddingError("Cannot embed empty text")

    if EMBEDDING_PROVIDER == "ollama":
        return generate_ollama_embedding(value)

    if EMBEDDING_PROVIDER == "azure_openai":
        return generate_azure_openai_embedding(value)

    raise EmbeddingError(f"Unsupported embedding provider: {EMBEDDING_PROVIDER}")


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    values = [(text or "").strip() for text in texts]
    if any(not value for value in values):
        raise EmbeddingError("Cannot embed empty text")

    if EMBEDDING_PROVIDER == "azure_openai":
        return generate_azure_openai_embeddings(values)

    return [generate_embedding(value) for value in values]
