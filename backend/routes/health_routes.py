import os
import time
from datetime import datetime
from urllib.parse import urlparse

from fastapi import APIRouter
from sqlalchemy import func, text

from database.db import SessionLocal
from models.chunk import Chunk
from models.document import Document
from services.ai_provider import (
    AZURE_OPENAI_DEPLOYMENT,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_API_VERSION,
    AIProviderError,
    ai_provider_name,
    generate_chat_completion,
)
from services.embeddings import (
    EMBEDDING_PROVIDER,
    EmbeddingError,
    embedding_model_name,
    generate_embedding,
)
from services.rag import embedding_text, keyword_relevance_score, vector_cosine_score


router = APIRouter(prefix="/health", tags=["System"])


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _duration_ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)


def _safe_endpoint_host(endpoint: str) -> str | None:
    if not endpoint:
        return None
    parsed = urlparse(endpoint)
    return parsed.netloc or None


@router.get("/database")
def database_health():
    start = time.perf_counter()
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1")).scalar_one()
        return {
            "status": "ok",
            "service": "database",
            "database": "postgresql",
            "checks": {
                "connectivity": "ok",
                "query": "SELECT 1",
            },
            "duration_ms": _duration_ms(start),
            "checked_at": _now_iso(),
        }
    except Exception as exc:
        return {
            "status": "error",
            "service": "database",
            "database": "postgresql",
            "checks": {
                "connectivity": "error",
            },
            "error": str(exc),
            "duration_ms": _duration_ms(start),
            "checked_at": _now_iso(),
        }
    finally:
        db.close()


@router.get("/ai")
def ai_health():
    start = time.perf_counter()
    provider = ai_provider_name()
    details = {
        "provider": provider,
        "deployment": AZURE_OPENAI_DEPLOYMENT if provider == "azure_openai" else os.getenv("OLLAMA_MODEL", "llama3"),
        "api_version": AZURE_OPENAI_API_VERSION if provider == "azure_openai" else None,
        "endpoint_host": _safe_endpoint_host(AZURE_OPENAI_ENDPOINT) if provider == "azure_openai" else None,
    }

    try:
        response = generate_chat_completion(
            prompt="Health check. Reply with only: ok",
            model=None,
            temperature=0,
            max_tokens=5,
        )
        return {
            "status": "ok",
            "service": "ai",
            "checks": {
                "provider_configured": "ok",
                "completion": "ok",
                "response_received": bool((response or "").strip()),
            },
            "details": details,
            "duration_ms": _duration_ms(start),
            "checked_at": _now_iso(),
        }
    except AIProviderError as exc:
        return {
            "status": "error",
            "service": "ai",
            "checks": {
                "provider_configured": "error",
                "completion": "error",
            },
            "details": details,
            "error": str(exc),
            "duration_ms": _duration_ms(start),
            "checked_at": _now_iso(),
        }


@router.get("/rag")
def rag_health():
    start = time.perf_counter()
    db = SessionLocal()
    query = "health check retrieval"
    checks = {}

    try:
        total_chunks = db.query(func.count(Chunk.id)).scalar() or 0
        ready_chunks = db.query(func.count(Chunk.id)).filter(
            Chunk.embedding_status == "ready",
            Chunk.embedding.isnot(None),
        ).scalar() or 0
        failed_chunks = db.query(func.count(Chunk.id)).filter(
            Chunk.embedding_status == "failed"
        ).scalar() or 0

        checks["chunk_store"] = "ok"
        checks["indexed_chunks_available"] = "ok" if ready_chunks else "warning"

        query_embedding = generate_embedding(query)
        checks["embedding_provider"] = "ok"

        rows = db.query(Chunk, Document).join(
            Document,
            Chunk.document_id == Document.id,
        ).filter(
            Chunk.embedding_status == "ready",
            Chunk.embedding.isnot(None),
        ).limit(25).all()

        best_score = 0.0
        best_chunk_id = None
        for chunk, _document in rows:
            semantic_score = vector_cosine_score(query_embedding, chunk.embedding or [])
            keyword_score = keyword_relevance_score(query, embedding_text(chunk))
            score = (semantic_score * 0.35) + (keyword_score * 0.65)
            if score > best_score:
                best_score = score
                best_chunk_id = chunk.id

        retrieval_checked = bool(rows)
        checks["retrieval_pipeline"] = "ok" if retrieval_checked else "warning"
        status = "ok" if retrieval_checked else "degraded"

        return {
            "status": status,
            "service": "rag",
            "checks": checks,
            "details": {
                "vector_store": "postgresql.chunks.embedding",
                "embedding_provider": EMBEDDING_PROVIDER,
                "embedding_model": embedding_model_name(),
                "query_embedding_dimensions": len(query_embedding),
                "total_chunks": total_chunks,
                "ready_chunks": ready_chunks,
                "failed_chunks": failed_chunks,
                "sampled_ready_chunks": len(rows),
                "best_sample_chunk_id": best_chunk_id,
                "best_sample_score": round(best_score, 4),
            },
            "duration_ms": _duration_ms(start),
            "checked_at": _now_iso(),
        }
    except EmbeddingError as exc:
        checks["embedding_provider"] = "error"
        return {
            "status": "error",
            "service": "rag",
            "checks": checks,
            "details": {
                "vector_store": "postgresql.chunks.embedding",
                "embedding_provider": EMBEDDING_PROVIDER,
                "embedding_model": embedding_model_name(),
            },
            "error": str(exc),
            "duration_ms": _duration_ms(start),
            "checked_at": _now_iso(),
        }
    except Exception as exc:
        return {
            "status": "error",
            "service": "rag",
            "checks": checks,
            "error": str(exc),
            "duration_ms": _duration_ms(start),
            "checked_at": _now_iso(),
        }
    finally:
        db.close()
