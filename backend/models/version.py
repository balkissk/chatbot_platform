from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from datetime import datetime
from database.db import Base
from sqlalchemy.orm import relationship

class VersionChatbot(Base):
    __tablename__ = "versions"

    id = Column(Integer, primary_key=True)
    version_number = Column(Integer)
    status = Column(String)  # draft / published / archived
    created_at = Column(DateTime, default=datetime.utcnow)
    published_at = Column(DateTime, nullable=True)
    archived_at = Column(DateTime, nullable=True)
    chatbot_id = Column(Integer, ForeignKey("chatbots.id"))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    published_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    archived_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    duplicated_from_version_id = Column(Integer, ForeignKey("versions.id"), nullable=True)
    llm_config = relationship("LLMConfig", back_populates="version", uselist=False)
