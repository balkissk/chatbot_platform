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
from services.document_ingestion import DocumentExtractionError, extract_document_text
from services.rag import chunk_document, embed_chunk, get_or_create_knowledge_base, retrieve_relevant_chunks_with_mode
from services.rag_settings import normalize_rag_settings

router = APIRouter()


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


def document_response(db: Session, document: Document) -> DocumentResponse:
    chunks_count = db.query(Chunk).filter(Chunk.document_id == document.id).count()
    ready_embeddings_count = db.query(Chunk).filter(
        Chunk.document_id == document.id,
        Chunk.embedding_status == "ready",
        Chunk.embedding.isnot(None),
    ).count()
    failed_embeddings_count = db.query(Chunk).filter(
        Chunk.document_id == document.id,
        Chunk.embedding_status == "failed",
    ).count()
    pending_embeddings_count = db.query(Chunk).filter(
        Chunk.document_id == document.id,
        Chunk.embedding_status == "pending",
    ).count()
    if document.chunks_count != chunks_count:
        document.chunks_count = chunks_count
        db.commit()
        db.refresh(document)

    response_status = document.status or "processed"
    if chunks_count and ready_embeddings_count == chunks_count:
        response_status = "processed"
    elif failed_embeddings_count:
        response_status = "embedding_failed"
    elif chunks_count and ready_embeddings_count < chunks_count:
        response_status = "processing"

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
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            return

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

        ready_chunks = 0
        failed_chunks = 0
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
            embed_chunk(chunk)
            if chunk.embedding_status == "ready":
                ready_chunks += 1
            else:
                failed_chunks += 1
            db.add(chunk)

        document.status = "embedding_failed" if failed_chunks else "processed"
        document.error_message = "Some chunks failed embedding generation" if failed_chunks else None
        document.processed_at = datetime.utcnow()
        document.chunks_count = len(chunks)
        db.commit()
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

    document = Document(
        knowledge_base_id=knowledge_base.id,
        filename=filename,
        content_type=payload.content_type,
        storage_url=f"local://version-{version_id}/{filename}",
        raw_text=None,
        size_bytes=len(payload.content or ""),
        status="processing",
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
    chunks = db.query(Chunk).filter(
        Chunk.document_id == document.id
    ).order_by(Chunk.order.asc()).all()

    ready_chunks = 0
    failed_chunks = 0
    for chunk in chunks:
        chunk.embedding_status = "pending"
        chunk.embedding_error = None
        embed_chunk(chunk)
        if chunk.embedding_status == "ready":
            ready_chunks += 1
        else:
            failed_chunks += 1

    document.status = "processed" if failed_chunks == 0 else "embedding_failed"
    document.error_message = None if failed_chunks == 0 else "Some chunks failed embedding generation"
    document.processed_at = datetime.utcnow()
    document.chunks_count = len(chunks)
    db.commit()

    return {
        "document_id": document.id,
        "total_chunks": len(chunks),
        "ready_chunks": ready_chunks,
        "failed_chunks": failed_chunks
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

    chunks = chunk_document(document.raw_text)
    if not chunks:
        raise HTTPException(status_code=400, detail="Document has no readable text")

    db.query(Chunk).filter(Chunk.document_id == document.id).delete()
    db.flush()

    ready_chunks = 0
    failed_chunks = 0
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
        embed_chunk(chunk)
        if chunk.embedding_status == "ready":
            ready_chunks += 1
        else:
            failed_chunks += 1
        db.add(chunk)

    document.status = "processed" if failed_chunks == 0 else "embedding_failed"
    document.error_message = None if failed_chunks == 0 else "Some chunks failed embedding generation"
    document.processed_at = datetime.utcnow()
    document.chunks_count = len(chunks)
    db.commit()

    return {
        "document_id": document.id,
        "total_chunks": len(chunks),
        "ready_chunks": ready_chunks,
        "failed_chunks": failed_chunks
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
