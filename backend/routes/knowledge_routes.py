from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
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
    if document.chunks_count != chunks_count:
        document.chunks_count = chunks_count
        db.commit()
        db.refresh(document)

    return DocumentResponse(
        id=document.id,
        filename=document.filename,
        content_type=document.content_type,
        size_bytes=document.size_bytes or 0,
        status=document.status or "processed",
        error_message=document.error_message,
        processed_at=document.processed_at,
        created_at=document.created_at,
        chunks_count=chunks_count
    )


@router.post("/versions/{version_id}/documents", response_model=DocumentResponse)
def ingest_document(
    version_id: int,
    payload: DocumentIngest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager"))
):
    ensure_version_access(db, version_id, current_user)

    content = payload.content or ""
    chunks = chunk_document(content)
    if not chunks:
        raise HTTPException(status_code=400, detail="Document has no readable text")

    knowledge_base = get_or_create_knowledge_base(db, version_id)
    now = datetime.utcnow()

    document = Document(
        knowledge_base_id=knowledge_base.id,
        filename=payload.filename.strip(),
        content_type=payload.content_type,
        storage_url=f"local://version-{version_id}/{payload.filename}",
        raw_text=content,
        size_bytes=len(content.encode("utf-8")),
        status="processed",
        error_message=None,
        processed_at=now,
        chunks_count=len(chunks)
    )

    db.add(document)
    db.commit()
    db.refresh(document)

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
        db.add(chunk)

    db.commit()
    db.refresh(document)

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

    db.query(Chunk).filter(Chunk.document_id == document.id).delete()
    db.delete(document)
    db.commit()

    return {"message": "Document deleted"}
