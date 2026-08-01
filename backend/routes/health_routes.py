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
    AIProviderError,
    azure_openai_config,
    azure_openai_configuration_warnings,
    ai_provider_name,
    generate_chat_completion,
)
from services.embeddings import (
    EMBEDDING_PROVIDER,
    EmbeddingError,
    embedding_model_name,
    generate_embedding,
)
from services.embedding_config import expected_embedding_dimensions, pgvector_literal, validate_embedding_vector


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
    azure_config = None
    warnings = []
    if provider == "azure_openai":
        try:
            azure_config = azure_openai_config()
            warnings = azure_openai_configuration_warnings()
        except AIProviderError as exc:
            return {
                "status": "error",
                "service": "ai",
                "checks": {
                    "provider_configured": "error",
                    "completion": "not_checked",
                },
                "details": {
                    "provider": provider,
                },
                "error": str(exc),
                "duration_ms": _duration_ms(start),
                "checked_at": _now_iso(),
            }

    details = {
        "provider": provider,
        "deployment": azure_config.deployment if azure_config else os.getenv("OLLAMA_MODEL", "llama3"),
        "api_version": azure_config.api_version if azure_config else None,
        "endpoint_host": azure_config.endpoint_host if azure_config else None,
        "configuration_warnings": warnings,
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
        ready_vector_chunks = db.query(func.count(Chunk.id)).filter(
            Chunk.embedding_status == "ready",
            Chunk.embedding_vector.isnot(None),
        ).scalar() or 0
        failed_chunks = db.query(func.count(Chunk.id)).filter(
            Chunk.embedding_status == "failed"
        ).scalar() or 0

        checks["chunk_store"] = "ok"
        checks["indexed_chunks_available"] = "ok" if ready_vector_chunks else "warning"

        query_embedding = generate_embedding(query)
        validate_embedding_vector(query_embedding)
        checks["embedding_provider"] = "ok"

        bind = db.get_bind()
        is_postgresql = bool(bind and bind.dialect.name == "postgresql")
        pgvector_extension = "not_checked"
        pgvector_schema = "not_checked"
        best_score = None
        best_chunk_id = None
        retrieval_checked = False

        if is_postgresql:
            pgvector_extension = "ok" if db.execute(text(
                "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')"
            )).scalar() else "error"
            pgvector_schema = "ok" if db.execute(text("""
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'chunks'
                      AND column_name = 'embedding_vector'
                )
            """)).scalar() else "error"
            checks["pgvector_extension"] = pgvector_extension
            checks["pgvector_schema"] = pgvector_schema

            row = db.execute(text("""
                SELECT c.id AS chunk_id,
                       1 - (c.embedding_vector <=> CAST(:query_vector AS vector)) AS similarity
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE c.embedding_status = 'ready'
                  AND c.embedding_vector IS NOT NULL
                  AND d.status IN ('ready', 'partially_ready', 'processed')
                ORDER BY c.embedding_vector <=> CAST(:query_vector AS vector)
                LIMIT 1
            """), {"query_vector": pgvector_literal(query_embedding)}).first()
            if row:
                retrieval_checked = True
                best_chunk_id = row.chunk_id
                best_score = round(float(row.similarity or 0), 4)
        else:
            checks["pgvector_extension"] = "not_available"
            checks["pgvector_schema"] = "not_available"

        checks["retrieval_pipeline"] = "ok" if retrieval_checked else "warning"
        status = "ok" if retrieval_checked else "degraded"

        return {
            "status": status,
            "service": "rag",
            "checks": checks,
            "details": {
                "vector_store": "postgresql.pgvector.chunks.embedding_vector",
                "embedding_provider": EMBEDDING_PROVIDER,
                "embedding_model": embedding_model_name(),
                "expected_embedding_dimensions": expected_embedding_dimensions(),
                "query_embedding_dimensions": len(query_embedding),
                "total_chunks": total_chunks,
                "ready_chunks": ready_chunks,
                "ready_vector_chunks": ready_vector_chunks,
                "failed_chunks": failed_chunks,
                "best_sample_chunk_id": best_chunk_id,
                "best_sample_score": best_score,
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
                "vector_store": "postgresql.pgvector.chunks.embedding_vector",
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
