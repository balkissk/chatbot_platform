from enum import StrEnum


class RuntimeFailureCategory(StrEnum):
    NO_ANSWER = "NO_ANSWER"
    LOW_RETRIEVAL_CONFIDENCE = "LOW_RETRIEVAL_CONFIDENCE"
    INVALID_FLOW = "INVALID_FLOW"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    API_BLOCK_FAILURE = "API_BLOCK_FAILURE"
    INGESTION_NOT_READY = "INGESTION_NOT_READY"
    LOOP_LIMIT_EXCEEDED = "LOOP_LIMIT_EXCEEDED"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"


def sanitized_category_from_error(exc: Exception) -> RuntimeFailureCategory:
    text = str(getattr(exc, "detail", None) or exc).lower()
    if "timeout" in text or "timed out" in text:
        return RuntimeFailureCategory.PROVIDER_TIMEOUT
    if "llm service" in text or "openai" in text or "ollama" in text or "provider" in text:
        return RuntimeFailureCategory.PROVIDER_FAILURE
    if "configuration" in text or "config" in text:
        return RuntimeFailureCategory.CONFIGURATION_ERROR
    if "flow" in text or "validation" in text:
        return RuntimeFailureCategory.INVALID_FLOW
    if "loop" in text or "runtime steps" in text:
        return RuntimeFailureCategory.LOOP_LIMIT_EXCEEDED
    if "api" in text or "webhook" in text:
        return RuntimeFailureCategory.API_BLOCK_FAILURE
    return RuntimeFailureCategory.CONFIGURATION_ERROR
