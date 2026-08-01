import os
import logging
import time
from collections.abc import Generator
from dataclasses import dataclass
from http import HTTPStatus
from urllib.parse import urlparse

import requests

from config.settings import load_environment

load_environment()
AI_PROVIDER = os.getenv("AI_PROVIDER", "ollama").strip().lower()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "")
AZURE_OPENAI_TIMEOUT_SECONDS = float(os.getenv("AZURE_OPENAI_TIMEOUT_SECONDS", "60"))
AZURE_OPENAI_MAX_RETRIES = int(os.getenv("AZURE_OPENAI_MAX_RETRIES", "2"))
AZURE_OPENAI_REASONING_EFFORT = os.getenv("AZURE_OPENAI_REASONING_EFFORT", "").strip().lower()
AI_RESPONSE_CACHE_ENABLED = os.getenv("AI_RESPONSE_CACHE_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
AI_RESPONSE_CACHE_TTL_SECONDS = int(os.getenv("AI_RESPONSE_CACHE_TTL_SECONDS", "120"))
logger = logging.getLogger(__name__)
_response_cache: dict[tuple[str, str, float, int], tuple[float, str]] = {}
_azure_client_cache: dict[tuple[str, str, str, bool], object] = {}


class AIProviderError(Exception):
    pass


@dataclass(frozen=True)
class AzureOpenAIConfig:
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


def ai_provider_name() -> str:
    return AI_PROVIDER


def configured_chat_model(requested_model: str | None = None) -> str:
    if AI_PROVIDER == "azure_openai":
        return azure_openai_config().deployment
    return requested_model or OLLAMA_MODEL


def _cache_key(prompt: str, model: str | None, temperature: float, max_tokens: int) -> tuple[str, str, float, int]:
    return (prompt, model or "", float(temperature or 0), int(max_tokens or 0))


def _cached_response(key: tuple[str, str, float, int]) -> str | None:
    if not AI_RESPONSE_CACHE_ENABLED:
        return None

    cached = _response_cache.get(key)
    if not cached:
        return None

    created_at, value = cached
    if time.time() - created_at > AI_RESPONSE_CACHE_TTL_SECONDS:
        _response_cache.pop(key, None)
        return None
    return value


def _store_cached_response(key: tuple[str, str, float, int], value: str) -> None:
    if not AI_RESPONSE_CACHE_ENABLED or not value:
        return

    _response_cache[key] = (time.time(), value)
    if len(_response_cache) > 256:
        oldest_key = min(_response_cache, key=lambda item: _response_cache[item][0])
        _response_cache.pop(oldest_key, None)


def azure_openai_config() -> AzureOpenAIConfig:
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", AZURE_OPENAI_ENDPOINT).strip().rstrip("/")
    api_key = os.getenv("AZURE_OPENAI_API_KEY", AZURE_OPENAI_API_KEY).strip()
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", AZURE_OPENAI_DEPLOYMENT).strip()
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", AZURE_OPENAI_API_VERSION).strip()

    missing = [
        name
        for name, value in {
            "AZURE_OPENAI_ENDPOINT": endpoint,
            "AZURE_OPENAI_API_KEY": api_key,
            "AZURE_OPENAI_DEPLOYMENT": deployment,
            "AZURE_OPENAI_API_VERSION": api_version,
        }.items()
        if not value
    ]
    if missing:
        raise AIProviderError(f"Azure OpenAI configuration is incomplete. Missing: {', '.join(missing)}")

    return AzureOpenAIConfig(
        endpoint=endpoint,
        api_key=api_key,
        deployment=deployment,
        api_version=api_version,
    )


def is_reasoning_chat_deployment(deployment: str) -> bool:
    value = (deployment or "").lower()
    return value.startswith(("gpt-5", "o1", "o3", "o4"))


def reasoning_completion_token_budget(max_tokens: int) -> int:
    return max(int(max_tokens or 0), 512)


def configured_reasoning_effort(deployment: str) -> str | None:
    configured = AZURE_OPENAI_REASONING_EFFORT or os.getenv("AZURE_OPENAI_REASONING_EFFORT", "").strip().lower()
    allowed = {"none", "minimal", "low", "medium", "high"}
    if configured in allowed:
        return configured
    if deployment.lower().startswith("gpt-5"):
        return "minimal"
    return None


def azure_openai_configuration_warnings() -> list[str]:
    if AI_PROVIDER != "azure_openai":
        return []

    try:
        config = azure_openai_config()
    except AIProviderError as exc:
        return [str(exc)]

    warnings = []
    if (
        is_reasoning_chat_deployment(config.deployment)
        and not config.is_v1_endpoint
        and config.api_version < "2024-10-21"
    ):
        warnings.append(
            "GPT-5/reasoning deployments require a recent Azure OpenAI API version. "
            "Configure AZURE_OPENAI_API_VERSION=2024-10-21 or a newer version supported by the deployed resource."
        )
    return warnings


def validate_ai_configuration() -> None:
    if AI_PROVIDER == "azure_openai":
        azure_openai_config()
        return
    if AI_PROVIDER != "ollama":
        raise AIProviderError(f"Unsupported AI provider: {AI_PROVIDER}")


def warm_ai_client() -> None:
    if AI_PROVIDER != "azure_openai":
        return
    _azure_client(azure_openai_config())


def _redact_secret(value: str, secret: str | None) -> str:
    if secret:
        value = value.replace(secret, "[redacted]")
    return value


def _safe_openai_error(
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
        reason = "resource or deployment was not found. Check AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_DEPLOYMENT."
    elif status_code == 429:
        reason = "rate limit or quota exceeded for the Azure OpenAI deployment."
    elif "max_tokens" in message and "max_completion_tokens" in message:
        reason = "model parameter incompatibility: this deployment requires max_completion_tokens."
    elif "temperature" in message and "unsupported" in message.lower():
        reason = "model parameter incompatibility: this deployment does not support temperature."
    elif "api-version" in message.lower() or "api version" in message.lower():
        reason = "API version incompatibility. Check AZURE_OPENAI_API_VERSION for this deployment."
    else:
        reason = "Azure OpenAI request failed."

    status_label = f"{status_code} {HTTPStatus(status_code).phrase}" if isinstance(status_code, int) and status_code in HTTPStatus._value2member_map_ else status_code
    details = [
        f"Azure OpenAI service error: {reason}",
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


def _azure_client(config: AzureOpenAIConfig):

    try:
        from openai import AzureOpenAI, OpenAI
    except ImportError as exc:
        raise AIProviderError("openai package is required for Azure OpenAI provider") from exc

    cache_key = (config.endpoint, config.api_key, config.api_version, config.is_v1_endpoint)
    if cache_key in _azure_client_cache:
        return _azure_client_cache[cache_key]

    if config.is_v1_endpoint:
        client = OpenAI(
            api_key=config.api_key,
            base_url=config.endpoint.rstrip("/") + "/",
            timeout=AZURE_OPENAI_TIMEOUT_SECONDS,
            max_retries=AZURE_OPENAI_MAX_RETRIES,
        )
        _azure_client_cache[cache_key] = client
        return client

    client = AzureOpenAI(
        azure_endpoint=config.endpoint,
        api_key=config.api_key,
        api_version=config.api_version,
        timeout=AZURE_OPENAI_TIMEOUT_SECONDS,
        max_retries=AZURE_OPENAI_MAX_RETRIES,
    )
    _azure_client_cache[cache_key] = client
    return client


def _log_azure_failure(service: str, path: str, exc: Exception, config: AzureOpenAIConfig) -> None:
    message = _redact_secret(str(exc), config.api_key)
    logger.warning(
        "Azure OpenAI %s request failed path=%s status=%s code=%s deployment=%s api_version=%s endpoint_host=%s message=%s",
        service,
        path,
        getattr(exc, "status_code", None),
        getattr(exc, "code", None),
        config.deployment,
        config.api_version if not config.is_v1_endpoint else "v1",
        config.endpoint_host,
        message[:500],
    )


def _ollama_generate(prompt: str, model: str, temperature: float, max_tokens: int, stream: bool):
    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": model or OLLAMA_MODEL,
                "prompt": prompt,
                "stream": stream,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens
                },
                "keep_alive": "10m"
            },
            timeout=120,
            stream=stream
        )
        response.raise_for_status()
        return response
    except requests.RequestException as exc:
        raise AIProviderError(str(exc)) from exc


def generate_chat_completion(prompt: str, model: str | None, temperature: float, max_tokens: int) -> str:
    key = _cache_key(prompt, model, temperature, max_tokens)
    cached = _cached_response(key)
    if cached is not None:
        logger.info("AI response cache hit provider=%s model=%s", AI_PROVIDER, model or configured_chat_model(model))
        return cached

    if AI_PROVIDER == "ollama":
        response = _ollama_generate(
            prompt=prompt,
            model=model or OLLAMA_MODEL,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False
        )
        body = response.json()
        if "error" in body:
            raise AIProviderError(body["error"])
        answer = body.get("response", "")
        _store_cached_response(key, answer)
        return answer

    if AI_PROVIDER == "azure_openai":
        config = azure_openai_config()
        request = {
            "model": config.deployment,
            "messages": [{"role": "user", "content": prompt}],
        }
        if is_reasoning_chat_deployment(config.deployment):
            request["max_completion_tokens"] = reasoning_completion_token_budget(max_tokens)
            effort = configured_reasoning_effort(config.deployment)
            if effort:
                request["reasoning_effort"] = effort
        else:
            request["temperature"] = temperature
            request["max_tokens"] = max_tokens

        try:
            response = _azure_client(config).chat.completions.create(**request)
        except Exception as exc:
            _log_azure_failure("chat", "/chat/completions", exc, config)
            raise AIProviderError(_safe_openai_error(
                exc,
                config.deployment,
                config.endpoint_host,
                config.api_version if not config.is_v1_endpoint else "v1",
                config.api_key,
            )) from exc

        answer = response.choices[0].message.content or ""
        if not answer.strip():
            raise AIProviderError(
                "Azure OpenAI service error: empty assistant response; "
                f"deployment={config.deployment}; "
                f"api_version={config.api_version if not config.is_v1_endpoint else 'v1'}; "
                "increase max_completion_tokens or verify the deployment supports Chat Completions."
            )
        _store_cached_response(key, answer)
        return answer

    raise AIProviderError(f"Unsupported AI provider: {AI_PROVIDER}")


def _ms(started_at: float) -> int:
    return max(0, round((time.perf_counter() - started_at) * 1000))


def stream_chat_completion(
    prompt: str,
    model: str | None,
    temperature: float,
    max_tokens: int,
    metrics: dict | None = None,
) -> Generator[str, None, None]:
    if AI_PROVIDER == "ollama":
        import json

        request_started_at = time.perf_counter()
        if metrics is not None:
            metrics["azure_request_started_epoch_ms"] = round(time.time() * 1000)
        response = _ollama_generate(
            prompt=prompt,
            model=model or OLLAMA_MODEL,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True
        )
        if metrics is not None:
            metrics["azure_request_ms"] = _ms(request_started_at)
        with response:
            try:
                for line in response.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    data = json.loads(line)
                    if "error" in data:
                        raise AIProviderError(data["error"])
                    token = data.get("response", "")
                    if token:
                        if metrics is not None and "azure_first_token_from_request_ms" not in metrics:
                            metrics["azure_first_token_from_request_ms"] = _ms(request_started_at)
                            metrics["azure_first_chunk_epoch_ms"] = round(time.time() * 1000)
                        yield token
                    if data.get("done"):
                        break
            except json.JSONDecodeError as exc:
                raise AIProviderError(str(exc)) from exc
        return

    if AI_PROVIDER == "azure_openai":
        config = azure_openai_config()
        request = {
            "model": config.deployment,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
        }
        if is_reasoning_chat_deployment(config.deployment):
            request["max_completion_tokens"] = reasoning_completion_token_budget(max_tokens)
            effort = configured_reasoning_effort(config.deployment)
            if effort:
                request["reasoning_effort"] = effort
        else:
            request["temperature"] = temperature
            request["max_tokens"] = max_tokens

        try:
            request_started_at = time.perf_counter()
            if metrics is not None:
                metrics["azure_request_started_epoch_ms"] = round(time.time() * 1000)
            stream = _azure_client(config).chat.completions.create(**request)
            if metrics is not None:
                metrics["azure_request_ms"] = _ms(request_started_at)
                metrics["reasoning_effort"] = request.get("reasoning_effort")
            for chunk in stream:
                if not chunk.choices:
                    continue
                token = chunk.choices[0].delta.content
                if token:
                    if metrics is not None and "azure_first_token_from_request_ms" not in metrics:
                        metrics["azure_first_token_from_request_ms"] = _ms(request_started_at)
                        metrics["azure_first_chunk_epoch_ms"] = round(time.time() * 1000)
                    yield token
        except Exception as exc:
            _log_azure_failure("chat_stream", "/chat/completions", exc, config)
            raise AIProviderError(_safe_openai_error(
                exc,
                config.deployment,
                config.endpoint_host,
                config.api_version if not config.is_v1_endpoint else "v1",
                config.api_key,
            )) from exc
        return

    raise AIProviderError(f"Unsupported AI provider: {AI_PROVIDER}")
