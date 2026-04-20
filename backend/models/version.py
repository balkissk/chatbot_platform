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
    chatbot_id = Column(Integer, ForeignKey("chatbots.id"))
    llm_config = relationship("LLMConfig", back_populates="version", uselist=False)