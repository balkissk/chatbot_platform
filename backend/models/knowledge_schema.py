from datetime import datetime

from pydantic import BaseModel


class DocumentIngest(BaseModel):
    filename: str
    content: str
    content_type: str | None = "text/plain"
    content_encoding: str | None = None


class DocumentUpdate(BaseModel):
    filename: str
    content_type: str | None = None


class DocumentResponse(BaseModel):
    id: int
    filename: str
    content_type: str | None
    size_bytes: int = 0
    status: str | None = "processed"
    error_message: str | None = None
    processed_at: datetime | None = None
    created_at: datetime | None = None
    chunks_count: int = 0
    pages_count: int | None = None

    class Config:
        from_attributes = True


class ChunkResponse(BaseModel):
    id: int
    document_id: int
    order: int
    title: str | None = None
    section_type: str | None = None
    text: str
    embedding_status: str | None = None
    embedding_model: str | None = None
    embedding_error: str | None = None

    class Config:
        from_attributes = True


class RagTestRequest(BaseModel):
    question: str
    limit: int = 4


class EmbeddingReprocessResponse(BaseModel):
    document_id: int
    total_chunks: int
    ready_chunks: int
    failed_chunks: int


class ChunkReprocessResponse(BaseModel):
    document_id: int
    total_chunks: int
    ready_chunks: int
    failed_chunks: int
