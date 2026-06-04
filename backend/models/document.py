from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from database.db import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id"))
    filename = Column(String)
    content_type = Column(String)
    storage_url = Column(String)
    raw_text = Column(Text, nullable=True)
    size_bytes = Column(Integer, default=0)
    status = Column(String, default="processed")
    error_message = Column(Text, nullable=True)
    processed_at = Column(DateTime, nullable=True)
    chunks_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    knowledge_base = relationship("KnowledgeBase", back_populates="documents")
    chunks = relationship("Chunk", back_populates="document")
