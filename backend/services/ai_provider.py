import os
from collections.abc import Generator

import requests


AI_PROVIDER = os.getenv("AI_PROVIDER", "ollama").strip().lower()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")


class AIProviderError(Exception):
    pass


def ai_provider_name() -> str:
    return AI_PROVIDER


def configured_chat_model(requested_model: str | None = None) -> str:
    if AI_PROVIDER == "azure_openai":
        return AZURE_OPENAI_DEPLOYMENT
    return requested_model or OLLAMA_MODEL


def _azure_client():
    if not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_API_KEY:
        raise AIProviderError("Azure OpenAI endpoint and API key must be configured")

    try:
        from openai import AzureOpenAI
    except ImportError as exc:
        raise AIProviderError("openai package is required for Azure OpenAI provider") from exc

    return AzureOpenAI(
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_key=AZURE_OPENAI_API_KEY,
        api_version=AZURE_OPENAI_API_VERSION
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
        return body.get("response", "")

    if AI_PROVIDER == "azure_openai":
        try:
            response = _azure_client().chat.completions.create(
                model=AZURE_OPENAI_DEPLOYMENT,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens
            )
        except Exception as exc:
            raise AIProviderError(str(exc)) from exc

        return response.choices[0].message.content or ""

    raise AIProviderError(f"Unsupported AI provider: {AI_PROVIDER}")


def stream_chat_completion(prompt: str, model: str | None, temperature: float, max_tokens: int) -> Generator[str, None, None]:
    if AI_PROVIDER == "ollama":
        import json

        response = _ollama_generate(
            prompt=prompt,
            model=model or OLLAMA_MODEL,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True
        )
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
                        yield token
                    if data.get("done"):
                        break
            except json.JSONDecodeError as exc:
                raise AIProviderError(str(exc)) from exc
        return

    if AI_PROVIDER == "azure_openai":
        try:
            stream = _azure_client().chat.completions.create(
                model=AZURE_OPENAI_DEPLOYMENT,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True
            )
            for chunk in stream:
                if not chunk.choices:
                    continue
                token = chunk.choices[0].delta.content
                if token:
                    yield token
        except Exception as exc:
            raise AIProviderError(str(exc)) from exc
        return

    raise AIProviderError(f"Unsupported AI provider: {AI_PROVIDER}")
