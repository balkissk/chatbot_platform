import hashlib
import logging
import time
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from database.db import SessionLocal
from models.chatbot import Chatbot
from models.chunk import Chunk
from models.document import Document
from models.knowledge_base import KnowledgeBase
from models.knowledge_schema import ChunkReprocessResponse, ChunkResponse, DocumentIngest, DocumentResponse, DocumentUpdate, EmbeddingReprocessResponse, RagTestRequest
from models.project import Project
from models.user import User
from models.version import VersionChatbot
from services.auth import require_roles
from services.audit import record_audit_log
from services.document_ingestion import DocumentExtractionError, decode_content_bytes, extract_document_text
from services.rag import chunk_document, embed_chunks, get_or_create_knowledge_base, retrieve_relevant_chunks_with_mode
from services.rag_settings import normalize_rag_settings

router = APIRouter()
logger = logging.getLogger(__name__)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_version_access(db: Session, version_id: int, current_user: User) -> VersionChatbot:
    version = db.query(VersionChatbot).filter(VersionChatbot.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    chatbot = db.query(Chatbot).filter(Chatbot.id == version.chatbot_id).first()
    if not chatbot:
        raise HTTPException(status_code=404, detail="Chatbot not found")

    if current_user.role == "manager":
        project = db.query(Project).filter(
            Project.id == chatbot.project_id,
            Project.user_id == current_user.id
        ).first()
        if not project:
            raise HTTPException(status_code=404, detail="Version not found")

    return version


def ensure_document_access(db: Session, document_id: int, current_user: User) -> Document:
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    knowledge_base = db.query(KnowledgeBase).filter(
        KnowledgeBase.id == document.knowledge_base_id
    ).first()
    if not knowledge_base:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    ensure_version_access(db, knowledge_base.version_id, current_user)
    return document


def document_content_hash(content: str, content_encoding: str | None = None) -> str:
    return hashlib.sha256(decode_content_bytes(content or "", content_encoding)).hexdigest()


def uses_pgvector(db: Session) -> bool:
    bind = db.get_bind()
    return bool(bind and bind.dialect.name == "postgresql")


def chunk_has_searchable_embedding(db: Session, chunk: Chunk) -> bool:
    if chunk.embedding_status != "ready":
        return False
    if uses_pgvector(db):
        return bool(getattr(chunk, "embedding_vector", None))
    return bool(chunk.embedding)


def chunk_state_counts(db: Session, document_id: int) -> dict[str, int]:
    chunks_count = db.query(Chunk).filter(Chunk.document_id == document_id).count()
    ready_query = db.query(Chunk).filter(
        Chunk.document_id == document_id,
        Chunk.embedding_status == "ready",
    )
    if uses_pgvector(db):
        ready_query = ready_query.filter(Chunk.embedding_vector.isnot(None))
    else:
        ready_query = ready_query.filter(Chunk.embedding.isnot(None))
    ready_embeddings_count = ready_query.count()
    failed_embeddings_count = db.query(Chunk).filter(
        Chunk.document_id == document_id,
        Chunk.embedding_status == "failed",
    ).count()
    pending_embeddings_count = db.query(Chunk).filter(
        Chunk.document_id == document_id,
        Chunk.embedding_status.in_(("pending", "processing")),
    ).count()
    return {
        "total": chunks_count,
        "ready": ready_embeddings_count,
        "failed": failed_embeddings_count,
        "pending": pending_embeddings_count,
    }


def status_from_counts(counts: dict[str, int], fallback_status: str | None = None) -> str:
    total = counts["total"]
    ready = counts["ready"]
    failed = counts["failed"]
    pending = counts["pending"]
    if fallback_status in {"uploaded", "processing"} and total == 0:
        return fallback_status
    if total == 0:
        return "failed" if fallback_status == "failed" else (fallback_status or "uploaded")
    if ready == total:
        return "ready"
    if ready > 0 and failed > 0 and pending == 0:
        return "partially_ready"
    if ready == 0 and failed == total:
        return "failed"
    return "processing"


def sync_document_status(db: Session, document: Document, commit: bool = False) -> dict[str, int]:
    counts = chunk_state_counts(db, document.id)
    document.chunks_count = counts["total"]
    document.status = status_from_counts(counts, document.status)
    if document.status in {"ready", "partially_ready", "failed"}:
        document.processed_at = datetime.utcnow()
    if document.status == "ready":
        document.error_message = None
    elif document.status == "partially_ready":
        document.error_message = "Some chunks failed embedding generation"
    elif document.status == "failed" and counts["failed"]:
        document.error_message = "All chunks failed embedding generation"
    if commit:
        db.commit()
        db.refresh(document)
    return counts


def document_response(db: Session, document: Document) -> DocumentResponse:
    counts = sync_document_status(db, document)
    chunks_count = counts["total"]
    ready_embeddings_count = counts["ready"]
    failed_embeddings_count = db.query(Chunk).filter(
        Chunk.document_id == document.id,
        Chunk.embedding_status == "failed",
    ).count()
    pending_embeddings_count = counts["pending"]
    response_status = status_from_counts(counts, document.status)

    return DocumentResponse(
        id=document.id,
        filename=document.filename,
        content_type=document.content_type,
        size_bytes=document.size_bytes or 0,
        status=response_status,
        error_message=document.error_message,
        processed_at=document.processed_at,
        created_at=document.created_at,
        chunks_count=chunks_count,
        embeddings_count=ready_embeddings_count,
        failed_embeddings_count=failed_embeddings_count,
        pending_embeddings_count=pending_embeddings_count,
        pages_count=(document.raw_text or "").count("\n\nPage ") + 1
        if (document.content_type or "").split(";")[0].strip().lower() == "application/pdf" and document.raw_text
        else None
    )


def process_document_background(
    document_id: int,
    filename: str,
    content_type: str | None,
    content: str,
    content_encoding: str | None
) -> None:
    db = SessionLocal()
    started_at = time.perf_counter()
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            return
        if document.status == "processing" and document.chunks_count:
            return
        document.status = "processing"
        document.error_message = None
        db.commit()

        try:
            extracted_text, size_bytes = extract_document_text(
                filename=filename,
                content_type=content_type,
                content=content or "",
                content_encoding=content_encoding
            )
            chunks = chunk_document(extracted_text)
            if not chunks:
                raise DocumentExtractionError("Document has no readable text")
        except DocumentExtractionError as exc:
            document.status = "failed"
            document.error_message = str(exc)
            document.processed_at = datetime.utcnow()
            document.chunks_count = 0
            db.commit()
            return

        document.raw_text = extracted_text
        document.size_bytes = size_bytes
        document.error_message = None

        db.query(Chunk).filter(Chunk.document_id == document.id).delete()
        db.flush()

        new_chunks = []
        for index, chunk_data in enumerate(chunks):
            chunk = Chunk(
                document_id=document.id,
                order=index,
                title=chunk_data.title,
                section_type=chunk_data.section_type,
                metadata_json=chunk_data.metadata or {},
                text=chunk_data.text,
                embedding_id=f"local-embedding-{document.id}-{index}",
                embedding_status="pending"
            )
            db.add(chunk)
            new_chunks.append(chunk)

        embed_chunks(new_chunks)
        db.flush()
        counts = sync_document_status(db, document)
        db.commit()
        logger.info(
            "knowledge_ingestion document_id=%s knowledge_base_id=%s operation=process status=%s total_chunks=%s ready=%s failed=%s pending=%s latency_ms=%s",
            document.id,
            document.knowledge_base_id,
            document.status,
            counts["total"],
            counts["ready"],
            counts["failed"],
            counts["pending"],
            round((time.perf_counter() - started_at) * 1000),
        )
    finally:
        db.close()


@router.post("/versions/{version_id}/documents", response_model=DocumentResponse)
def ingest_document(
    version_id: int,
    payload: DocumentIngest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    ensure_version_access(db, version_id, current_user)

    knowledge_base = get_or_create_knowledge_base(db, version_id)
    filename = payload.filename.strip()
    if not filename:
        raise HTTPException(status_code=400, detail="Document filename is required")
    try:
        content_hash = document_content_hash(payload.content or "", payload.content_encoding)
    except DocumentExtractionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    duplicate = db.query(Document).filter(
        Document.knowledge_base_id == knowledge_base.id,
        Document.content_hash == content_hash,
    ).first()
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail="This exact document has already been uploaded to this knowledge base.",
        )

    document = Document(
        knowledge_base_id=knowledge_base.id,
        filename=filename,
        content_type=payload.content_type,
        storage_url=f"local://version-{version_id}/{filename}",
        raw_text=None,
        content_hash=content_hash,
        size_bytes=len(payload.content or ""),
        status="uploaded",
        error_message=None,
        processed_at=None,
        chunks_count=0
    )

    db.add(document)
    db.commit()
    db.refresh(document)
    background_tasks.add_task(
        process_document_background,
        document.id,
        filename,
        payload.content_type,
        payload.content or "",
        payload.content_encoding
    )

    record_audit_log(
        db,
        actor=current_user,
        action="DOCUMENT_UPLOADED",
        resource_type="document",
        resource_id=document.id,
        resource_name=document.filename,
        metadata={"version_id": version_id, "content_type": document.content_type, "size_bytes": document.size_bytes},
    )

    return document_response(db, document)


@router.get("/versions/{version_id}/documents", response_model=list[DocumentResponse])
def get_documents(
    version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    ensure_version_access(db, version_id, current_user)
    knowledge_base = get_or_create_knowledge_base(db, version_id)
    documents = db.query(Document).filter(
        Document.knowledge_base_id == knowledge_base.id
    ).order_by(Document.created_at.desc()).all()

    return [document_response(db, document) for document in documents]


@router.get("/documents/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    document = ensure_document_access(db, document_id, current_user)
    return document_response(db, document)


@router.put("/documents/{document_id}", response_model=DocumentResponse)
def update_document(
    document_id: int,
    payload: DocumentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    document = ensure_document_access(db, document_id, current_user)
    filename = payload.filename.strip()
    if not filename:
        raise HTTPException(status_code=400, detail="Document filename is required")

    document.filename = filename
    if payload.content_type is not None:
        document.content_type = payload.content_type.strip() or None
    db.commit()
    db.refresh(document)
    record_audit_log(
        db,
        actor=current_user,
        action="KNOWLEDGE_BASE_UPDATED",
        resource_type="document",
        resource_id=document.id,
        resource_name=document.filename,
    )
    return document_response(db, document)


@router.get("/documents/{document_id}/chunks", response_model=list[ChunkResponse])
def get_chunks(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    ensure_document_access(db, document_id, current_user)
    return db.query(Chunk).filter(
        Chunk.document_id == document_id
    ).order_by(Chunk.order.asc()).all()


@router.post("/documents/{document_id}/embeddings/reprocess", response_model=EmbeddingReprocessResponse)
def reprocess_document_embeddings(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    document = ensure_document_access(db, document_id, current_user)
    if document.status == "processing":
        return {
            "document_id": document.id,
            "total_chunks": chunk_state_counts(db, document.id)["total"],
            "ready_chunks": chunk_state_counts(db, document.id)["ready"],
            "failed_chunks": chunk_state_counts(db, document.id)["failed"],
        }
    document.status = "processing"
    document.error_message = None
    db.commit()

    all_chunks = db.query(Chunk).filter(
        Chunk.document_id == document.id
    ).order_by(Chunk.order.asc()).all()
    chunks = [
        chunk
        for chunk in all_chunks
        if not chunk_has_searchable_embedding(db, chunk)
    ]

    embed_chunks(chunks)
    counts = sync_document_status(db, document)
    db.commit()

    return {
        "document_id": document.id,
        "total_chunks": counts["total"],
        "ready_chunks": counts["ready"],
        "failed_chunks": counts["failed"]
    }


@router.post("/documents/{document_id}/chunks/reprocess", response_model=ChunkReprocessResponse)
def reprocess_document_chunks(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    document = ensure_document_access(db, document_id, current_user)
    if not document.raw_text:
        raise HTTPException(
            status_code=400,
            detail="This document was uploaded before raw text storage. Re-upload it once to enable chunk reprocessing."
        )

    if document.status == "processing":
        counts = chunk_state_counts(db, document.id)
        return {
            "document_id": document.id,
            "total_chunks": counts["total"],
            "ready_chunks": counts["ready"],
            "failed_chunks": counts["failed"]
        }

    chunks = chunk_document(document.raw_text)
    if not chunks:
        raise HTTPException(status_code=400, detail="Document has no readable text")

    replacement_chunks = []
    for index, chunk_data in enumerate(chunks):
        chunk = Chunk(
            document_id=document.id,
            order=index,
            title=chunk_data.title,
            section_type=chunk_data.section_type,
            metadata_json=chunk_data.metadata or {},
            text=chunk_data.text,
            embedding_id=f"local-embedding-{document.id}-{index}",
            embedding_status="pending"
        )
        replacement_chunks.append(chunk)

    embed_chunks(replacement_chunks)
    ready_chunks = sum(1 for chunk in replacement_chunks if chunk_has_searchable_embedding(db, chunk))
    failed_chunks = len(replacement_chunks) - ready_chunks

    if failed_chunks:
        counts = sync_document_status(db, document)
        db.commit()
        return {
            "document_id": document.id,
            "total_chunks": counts["total"],
            "ready_chunks": counts["ready"],
            "failed_chunks": counts["failed"]
        }

    document.status = "processing"
    document.error_message = None
    db.commit()
    db.query(Chunk).filter(Chunk.document_id == document.id).delete()
    db.flush()
    for chunk in replacement_chunks:
        db.add(chunk)
    db.flush()
    counts = sync_document_status(db, document)
    db.commit()

    return {
        "document_id": document.id,
        "total_chunks": counts["total"],
        "ready_chunks": counts["ready"],
        "failed_chunks": counts["failed"]
    }


@router.post("/versions/{version_id}/rag-test")
def test_rag_retrieval(
    version_id: int,
    payload: RagTestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    version = ensure_version_access(db, version_id, current_user)
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required")

    chatbot = db.query(Chatbot).filter(Chatbot.id == version.chatbot_id).first()
    rag_settings = normalize_rag_settings(chatbot.rag_settings if chatbot else None)
    result = retrieve_relevant_chunks_with_mode(
        db=db,
        version_id=version_id,
        query=question,
        limit=max(min(payload.limit or rag_settings["max_chunks"], 10), 1),
        retrieval_mode=rag_settings["retrieval_mode"],
        min_score=rag_settings["min_score"]
    )
    results = result["chunks"]

    return {
        "question": question,
        "retrieval_mode": result["mode"],
        "rag_settings": rag_settings,
        "chunks": [
            {
                "chunk_id": chunk.id,
                "document_id": document.id,
                "filename": document.filename,
                "order": chunk.order,
                "title": chunk.title,
                "section_type": chunk.section_type,
                "score": score,
                "embedding_status": chunk.embedding_status,
                "embedding_model": chunk.embedding_model,
                "text": chunk.text
            }
            for chunk, document, score in results
        ]
    }


@router.delete("/documents/{document_id}")
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    document = ensure_document_access(db, document_id, current_user)
    deleted_document_id = document.id
    deleted_filename = document.filename

    db.query(Chunk).filter(Chunk.document_id == document.id).delete()
    db.delete(document)
    db.commit()

    record_audit_log(
        db,
        actor=current_user,
        action="DOCUMENT_DELETED",
        resource_type="document",
        resource_id=deleted_document_id,
        resource_name=deleted_filename,
    )

    return {"message": "Document deleted"}
