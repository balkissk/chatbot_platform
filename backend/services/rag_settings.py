DEFAULT_RAG_SETTINGS = {
    "retrieval_mode": "auto",
    "max_chunks": 3,
    "min_score": 0.2,
    "show_sources": True,
    "strict_context": True,
    "response_length": "short"
}


def normalize_rag_settings(settings: dict | None) -> dict:
    values = {**DEFAULT_RAG_SETTINGS, **(settings or {})}
    if values["retrieval_mode"] not in {"auto", "semantic", "keyword"}:
        values["retrieval_mode"] = DEFAULT_RAG_SETTINGS["retrieval_mode"]

    values["max_chunks"] = max(1, min(int(values.get("max_chunks") or 3), 8))
    values["min_score"] = max(0.0, min(float(values.get("min_score") or 0), 1.0))
    values["show_sources"] = bool(values.get("show_sources"))
    values["strict_context"] = bool(values.get("strict_context"))
    if values["response_length"] not in {"short", "normal", "detailed"}:
        values["response_length"] = DEFAULT_RAG_SETTINGS["response_length"]
    return values
