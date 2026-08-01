from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from database.db import Base
from models.vector_type import PgVector


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"))
    order = Column(Integer)
    title = Column(String, nullable=True)
    section_type = Column(String, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    text = Column(Text)
    embedding_id = Column(String)
    embedding = Column(JSON, nullable=True)
    embedding_vector = Column(PgVector(), nullable=True)
    embedding_model = Column(String, nullable=True)
    embedding_status = Column(String, default="pending")
    embedding_error = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)
    last_attempt_at = Column(DateTime, nullable=True)
    embedded_at = Column(DateTime, nullable=True)
    embedding_dimensions = Column(Integer, nullable=True)
    retrieval_score = Column(Float, nullable=True)

    document = relationship("Document", back_populates="chunks")
